"""Decisions, next-meeting agendas, meeting memory (RAG) and workload."""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from app.config import get_settings
from app.deps import Ctx, get_owned, workspace_ctx
from app.models import Agenda, AgendaRevision, Decision, Meeting, Membership, Task, User, Workspace
from app.providers.base import ProviderError
from app.providers.llm import get_llm
from app.serializers import decision_out, iso, task_out
from app.services import calendar_events, memory, planner, workload
from app.services import decisions as dsvc
from app.services import tasks as tsvc
from app.services.audit import audit

router = APIRouter(prefix="/api/w/{wid}", tags=["planning"])


# ---- decisions -----------------------------------------------------------------------------
@router.get("/decisions")
def list_decisions(ctx: Ctx = Depends(workspace_ctx), kind: str | None = None, conflicts: bool = False):
    stmt = select(Decision).where(Decision.workspace_id == ctx.wid)
    if kind:
        stmt = stmt.where(Decision.kind == kind)
    if conflicts:
        stmt = stmt.where(Decision.conflict_state != "none")
    out = []
    titles = {m.id: m.title for m in ctx.db.scalars(select(Meeting).where(Meeting.workspace_id == ctx.wid))}
    for d in ctx.db.scalars(stmt.order_by(Decision.id.desc()).limit(200)):
        out.append({**decision_out(d), "meeting_title": titles.get(d.meeting_id, "")})
    return out


@router.get("/decisions/{did}")
def get_decision(did: int, ctx: Ctx = Depends(workspace_ctx)):
    d = get_owned(ctx, Decision, did)
    other = ctx.db.get(Decision, d.conflicts_with_id) if d.conflicts_with_id else None
    if other and other.workspace_id != ctx.wid:
        other = None
    titles = {m.id: m.title for m in ctx.db.scalars(select(Meeting).where(Meeting.workspace_id == ctx.wid))}
    return {
        **decision_out(d),
        "meeting_title": titles.get(d.meeting_id, ""),
        "conflicting": {**decision_out(other), "meeting_title": titles.get(other.meeting_id, "")} if other else None,
    }


class ResolveIn(BaseModel):
    action: str


@router.post("/decisions/{did}/resolve")
def resolve(did: int, body: ResolveIn, ctx: Ctx = Depends(workspace_ctx)):
    ctx.require("manager")
    d = get_owned(ctx, Decision, did)
    try:
        dsvc.resolve_conflict(ctx.db, d, body.action, ctx.user.name)
    except ValueError as e:
        raise HTTPException(409, str(e)) from None
    if body.action == "confirm":
        d.review_state = "approved"
    ctx.db.commit()
    return decision_out(d)


class DecisionStatusIn(BaseModel):
    status: str


@router.post("/decisions/{did}/status")
def decision_status(did: int, body: DecisionStatusIn, ctx: Ctx = Depends(workspace_ctx)):
    ctx.require("manager")
    d = get_owned(ctx, Decision, did)
    if body.status not in ("confirmed", "dismissed"):
        raise HTTPException(422, "Status must be confirmed or dismissed")
    if d.review_state != "approved":
        raise HTTPException(409, "Approve this item in the meeting review first")
    d.status = body.status
    audit(ctx.db, ctx.wid, ctx.user.name, f"decision.{body.status}", "decision", d.id)
    ctx.db.commit()
    return decision_out(d)


# ---- agendas -------------------------------------------------------------------------------
class AgendaNew(BaseModel):
    title: str = Field(default="Next meeting agenda", min_length=1, max_length=200)


class AgendaEdit(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    items: list[dict] = Field(max_length=100)


def _ag(a: Agenda) -> dict:
    return {"id": a.id, "title": a.title, "items": a.items, "status": a.status, "revision": a.revision, "created_at": iso(a.created_at)}


@router.get("/agendas")
def list_agendas(ctx: Ctx = Depends(workspace_ctx)):
    return [_ag(a) for a in ctx.db.scalars(select(Agenda).where(Agenda.workspace_id == ctx.wid).order_by(Agenda.id.desc()).limit(50))]


@router.post("/agendas", status_code=201)
def new_agenda(body: AgendaNew, ctx: Ctx = Depends(workspace_ctx)):
    ctx.require("member")
    ag = planner.create_agenda(ctx.db, ctx.wid, body.title.strip(), ctx.user.id)
    ctx.db.commit()
    return _ag(ag)


@router.get("/agendas/{aid}")
def get_agenda(aid: int, ctx: Ctx = Depends(workspace_ctx)):
    ag = get_owned(ctx, Agenda, aid)
    revs = ctx.db.scalars(select(AgendaRevision).where(AgendaRevision.agenda_id == ag.id).order_by(AgendaRevision.revision.desc())).all()
    return {**_ag(ag), "revisions": [{"revision": r.revision, "title": r.title, "items": len(r.items), "at": iso(r.at)} for r in revs]}


@router.put("/agendas/{aid}")
def edit_agenda(aid: int, body: AgendaEdit, ctx: Ctx = Depends(workspace_ctx)):
    ctx.require("member")
    ag = get_owned(ctx, Agenda, aid)
    items = []
    for it in body.items:
        if not str(it.get("title", "")).strip():
            raise HTTPException(422, "Every agenda item needs a title")
        items.append(
            {
                "id": str(it.get("id", ""))[:16] or "new",
                "kind": str(it.get("kind", "custom"))[:20],
                "title": str(it["title"])[:300],
                "reason": str(it.get("reason", ""))[:500],
                "ref": it.get("ref") or {},
                "minutes": max(1, min(int(it.get("minutes", 5)), 240)),
            }
        )
    planner.edit_agenda(ctx.db, ag, body.title.strip(), items, ctx.user.id)
    ctx.db.commit()
    return _ag(ag)


@router.post("/agendas/{aid}/approve")
def approve_agenda(aid: int, ctx: Ctx = Depends(workspace_ctx)):
    ctx.require("manager")
    ag = get_owned(ctx, Agenda, aid)
    ag.status, ag.approved_by = "approved", ctx.user.id
    audit(ctx.db, ctx.wid, ctx.user.name, "agenda.approved", "agenda", ag.id, revision=ag.revision)
    ctx.db.commit()
    return _ag(ag)


class CalendarIn(BaseModel):
    start: str = Field(min_length=10, max_length=40)


@router.post("/agendas/{aid}/calendar", status_code=201)
def propose_event(aid: int, body: CalendarIn, ctx: Ctx = Depends(workspace_ctx)):
    ctx.require("member")
    ag = get_owned(ctx, Agenda, aid)
    ws = ctx.db.get(Workspace, ctx.wid)
    ttl = timedelta(hours=int((ws.settings or {}).get("approval_ttl_hours", get_settings().approval_ttl_hours)))
    ap = calendar_events.propose(ctx.db, ag, body.start, ctx.user.id, ttl)
    ctx.db.commit()
    return {"approval_id": ap.id, "status": ap.status}


# ---- memory -----------------------------------------------------------------------------------
class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=500)


@router.post("/memory/ask")
def ask(body: AskIn, ctx: Ctx = Depends(workspace_ctx)):
    hits = memory.search(ctx.db, ctx.wid, body.question, k=5)
    if not hits:
        return {
            "evidence_found": False,
            "answer": "No supporting evidence was found in the meeting records you can access. Try different keywords or process more meetings.",
            "citations": [],
        }
    try:
        answer = get_llm().answer(body.question, hits)
    except ProviderError as e:
        answer = f"The AI provider is unavailable ({e}). Showing the matching transcript passages instead."
    return {"evidence_found": True, "answer": answer, "citations": hits}


@router.get("/search")
def global_search(q: str, ctx: Ctx = Depends(workspace_ctx)):
    q = q.strip()[:100]
    if len(q) < 2:
        return {"tasks": [], "meetings": [], "decisions": []}
    like = f"%{q}%"
    ts = ctx.db.scalars(
        select(Task)
        .where(Task.workspace_id == ctx.wid, Task.review_state != "rejected", or_(Task.title.ilike(like), Task.owner_name.ilike(like)))
        .limit(8)
    )
    ms = ctx.db.scalars(select(Meeting).where(Meeting.workspace_id == ctx.wid, Meeting.title.ilike(like)).limit(5))
    ds = ctx.db.scalars(select(Decision).where(Decision.workspace_id == ctx.wid, Decision.text.ilike(like)).limit(5))
    return {
        "tasks": [{"id": t.id, "title": t.title, "status": t.status} for t in ts],
        "meetings": [{"id": m.id, "title": m.title} for m in ms],
        "decisions": [{"id": d.id, "text": d.text[:120]} for d in ds],
    }


# ---- workload ---------------------------------------------------------------------------------
class ApplyIn(BaseModel):
    task_id: int
    to_user_id: int


@router.get("/workload")
def get_workload(ctx: Ctx = Depends(workspace_ctx)):
    return workload.compute(ctx.db, ctx.wid)


@router.post("/workload/apply")
def apply_reassignment(body: ApplyIn, ctx: Ctx = Depends(workspace_ctx)):
    ctx.require("manager")  # reassignment needs an authorized human decision
    t = get_owned(ctx, Task, body.task_id)
    target = ctx.db.scalar(select(Membership).where(Membership.user_id == body.to_user_id, Membership.workspace_id == ctx.wid))
    if not target:
        raise HTTPException(422, "That person is not a member of this workspace")
    u = ctx.db.get(User, body.to_user_id)
    tsvc.update_fields(ctx.db, t, {"owner_name": u.name, "owner_user_id": u.id}, ctx.user)
    audit(ctx.db, ctx.wid, ctx.user.name, "task.reassigned", "task", t.id, to=u.name)
    ctx.db.commit()
    return task_out(t)
