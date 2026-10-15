"""Follow-ups, approvals and provider webhooks."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.config import get_settings
from app.db import get_db
from app.deps import Ctx, get_owned, workspace_ctx
from app.models import Approval, Contact, FollowUp, Job, ReminderRule, Task, User
from app.providers.messaging import verify_whatsapp_signature
from app.serializers import approval_out, followup_out
from app.services import followups as fsvc
from app.services import jobs
from app.services.audit import audit
from app.services.tasks import ACTIVE

router = APIRouter(prefix="/api", tags=["comms"])


class DraftIn(BaseModel):
    task_id: int
    contact_id: int
    channel: str


class DraftPatch(BaseModel):
    subject: str | None = Field(default=None, max_length=300)
    body: str | None = Field(default=None, min_length=1, max_length=4000)


def _out(ctx: Ctx, f: FollowUp) -> dict:
    return followup_out(f, ctx.db.get(Contact, f.contact_id) if f.contact_id else None, ctx.db.get(Task, f.task_id) if f.task_id else None)


@router.get("/w/{wid}/followups")
def list_followups(ctx: Ctx = Depends(workspace_ctx), status: str | None = None):
    stmt = select(FollowUp).where(FollowUp.workspace_id == ctx.wid)
    if status:
        stmt = stmt.where(FollowUp.status.in_(status.split(",")))
    return [_out(ctx, f) for f in ctx.db.scalars(stmt.order_by(FollowUp.id.desc()).limit(200))]


@router.post("/w/{wid}/followups", status_code=201)
def create_draft(body: DraftIn, ctx: Ctx = Depends(workspace_ctx), response: Response = None):
    ctx.require("member")
    task, contact = get_owned(ctx, Task, body.task_id), get_owned(ctx, Contact, body.contact_id)
    fu, created = fsvc.create_draft(ctx.db, ctx.wid, task, contact, body.channel, ctx.user.id)
    ctx.db.commit()
    if not created:
        response.status_code = 200
    return _out(ctx, fu)


@router.patch("/w/{wid}/followups/{fid}")
def edit_draft(fid: int, body: DraftPatch, ctx: Ctx = Depends(workspace_ctx)):
    ctx.require("member")
    f = get_owned(ctx, FollowUp, fid)
    if f.status != "draft":
        raise HTTPException(409, "Only drafts can be edited. Revoke or reject the approval first")
    if body.subject is not None:
        f.subject = body.subject
    if body.body is not None:
        f.body = body.body
    ctx.db.commit()
    return _out(ctx, f)


@router.post("/w/{wid}/followups/{fid}/submit", status_code=201)
def submit(fid: int, ctx: Ctx = Depends(workspace_ctx)):
    ctx.require("member")
    f = get_owned(ctx, FollowUp, fid)
    ap = fsvc.request_approval(ctx.db, f, ctx.user.id)
    audit(ctx.db, ctx.wid, ctx.user.name, "followup.submitted", "followup", f.id)
    ctx.db.commit()
    return approval_out(ap)


@router.post("/w/{wid}/followups/{fid}/retry")
def retry(fid: int, ctx: Ctx = Depends(workspace_ctx)):
    ctx.require("manager")
    f = get_owned(ctx, FollowUp, fid)
    if f.status != "failed":
        raise HTTPException(409, "Only failed follow-ups can be retried")
    ap = ctx.db.scalar(select(Approval).where(Approval.kind == "followup", Approval.ref_id == f.id).order_by(Approval.id.desc()))
    if not ap or ap.status != "approved" or ap.expires_at <= fsvc.utcnow():
        raise HTTPException(409, "The earlier approval is no longer valid. Submit the follow-up for approval again")
    f.status = "approved"
    jobs.enqueue(ctx.db, ctx.wid, "send_followup", f.id)
    ctx.db.commit()
    return _out(ctx, f)


@router.post("/w/{wid}/followups/run-reminders")
def run_reminders(ctx: Ctx = Depends(workspace_ctx)):
    """Apply enabled reminder rules and create DRAFTS only. Sending still requires approval."""
    ctx.require("manager")
    today, created, skipped = date.today(), 0, []
    rules = ctx.db.scalars(select(ReminderRule).where(ReminderRule.workspace_id == ctx.wid, ReminderRule.enabled.is_(True))).all()
    tasks = ctx.db.scalars(
        select(Task).where(Task.workspace_id == ctx.wid, Task.status.in_(ACTIVE), Task.review_state == "approved", Task.due_date.is_not(None))
    ).all()
    contacts = ctx.db.scalars(select(Contact).where(Contact.workspace_id == ctx.wid)).all()
    for r in rules:
        for t in tasks:
            due_hit = (r.trigger == "before_due" and t.due_date == today + timedelta(days=r.days)) or (
                r.trigger == "overdue" and (today - t.due_date).days == r.days
            )
            if not due_hit:
                continue
            c = next((c for c in contacts if (t.owner_user_id and c.user_id == t.owner_user_id) or c.name.lower() == t.owner_name.lower()), None)
            if not c:
                skipped.append({"task_id": t.id, "reason": "No contact matches the task owner"})
                continue
            try:
                _, new = fsvc.create_draft(ctx.db, ctx.wid, t, c, r.channel, ctx.user.id, reminder_key=f"rule{r.id}:{today}")
                created += int(new)
            except ValueError as e:
                skipped.append({"task_id": t.id, "reason": str(e)})
    ctx.db.commit()
    return {"drafts_created": created, "skipped": skipped}


# ---- approvals ---------------------------------------------------------------------------------
class DecideIn(BaseModel):
    approve: bool
    note: str = Field(default="", max_length=500)


@router.get("/w/{wid}/approvals")
def list_approvals(ctx: Ctx = Depends(workspace_ctx), status: str | None = None):
    fsvc.expire_stale(ctx.db)
    ctx.db.commit()
    stmt = select(Approval).where(Approval.workspace_id == ctx.wid)
    if status:
        stmt = stmt.where(Approval.status.in_(status.split(",")))
    names = {u.id: u.name for u in ctx.db.scalars(select(User))}
    return [approval_out(a, names) for a in ctx.db.scalars(stmt.order_by(Approval.id.desc()).limit(200))]


@router.post("/w/{wid}/approvals/{aid}/decide")
def decide(aid: int, body: DecideIn, ctx: Ctx = Depends(workspace_ctx)):
    ctx.require("manager")
    ap = get_owned(ctx, Approval, aid)
    try:
        fsvc.decide(ctx.db, ap, ctx.user.id, body.approve, body.note)
    finally:
        ctx.db.commit()  # persists an 'expired' transition even when the request is refused
    return approval_out(ap, {ctx.user.id: ctx.user.name})


@router.post("/w/{wid}/approvals/{aid}/revoke")
def revoke(aid: int, ctx: Ctx = Depends(workspace_ctx)):
    ctx.require("manager")
    ap = get_owned(ctx, Approval, aid)
    fsvc.revoke(ctx.db, ap, ctx.user.id)
    for j in ctx.db.scalars(select(Job).where(Job.ref_id == ap.ref_id, Job.kind == "send_followup", Job.status == "queued")):
        j.status, j.last_error = "dead", "Approval revoked"
    ctx.db.commit()
    return approval_out(ap, {})


# ---- WhatsApp webhooks (signature validated) --------------------------------------------------------
@router.get("/webhooks/whatsapp")
def whatsapp_verify(
    mode: str = Query("", alias="hub.mode"), token: str = Query("", alias="hub.verify_token"), challenge: str = Query("", alias="hub.challenge")
):
    s = get_settings()
    if mode == "subscribe" and s.whatsapp_verify_token and token == s.whatsapp_verify_token:
        return Response(challenge, media_type="text/plain")
    raise HTTPException(403, "Verification failed")


@router.post("/webhooks/whatsapp")
async def whatsapp_events(request: Request, db=Depends(get_db)):
    raw = await request.body()
    if not verify_whatsapp_signature(raw, request.headers.get("x-hub-signature-256"), get_settings().whatsapp_app_secret):
        raise HTTPException(401, "Invalid signature")
    try:
        data = await request.json()
    except ValueError:
        raise HTTPException(400, "Invalid JSON") from None
    updated = 0
    for entry in data.get("entry", []):
        for ch in entry.get("changes", []):
            for st in ch.get("value", {}).get("statuses", []):
                f = db.scalar(select(FollowUp).where(FollowUp.provider_message_id == st.get("id", "~"), FollowUp.channel == "whatsapp"))
                if f and st.get("status") in ("sent", "delivered", "read", "failed"):
                    f.delivery_status = st["status"]
                    updated += 1
    db.commit()
    return {"updated": updated}
