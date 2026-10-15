"""Workspace administration: settings, members/roles, contacts, reminder rules, integrations, notifications, audit."""

import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import func, select

from app.config import get_settings
from app.deps import Ctx, get_owned, workspace_ctx
from app.models import ROLE_RANK, ROLES, AuditLog, Contact, IntegrationConfig, Job, Membership, Notification, ReminderRule, User
from app.providers.messaging import channel_status
from app.security import hash_password
from app.serializers import contact_out, iso
from app.services.audit import audit

router = APIRouter(prefix="/api/w/{wid}", tags=["workspace"])
HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class WorkspacePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    timezone: str | None = None
    quiet_start: str | None = None
    quiet_end: str | None = None
    approval_ttl_hours: int | None = Field(default=None, ge=1, le=168)

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v):
        if v is not None:
            try:
                ZoneInfo(v)
            except (ZoneInfoNotFoundError, ValueError, OSError) as e:
                raise ValueError("Unknown timezone") from e
        return v

    @field_validator("quiet_start", "quiet_end")
    @classmethod
    def _hhmm(cls, v):
        if v not in (None, "") and not HHMM.match(v):
            raise ValueError("Use HH:MM (24h)")
        return v


@router.get("/workspace")
def get_workspace(ctx: Ctx = Depends(workspace_ctx)):
    w = ctx.workspace
    return {"id": w.id, "name": w.name, "timezone": w.timezone, "is_demo": w.is_demo, "settings": w.settings or {}, "role": ctx.role}


@router.patch("/workspace")
def patch_workspace(body: WorkspacePatch, ctx: Ctx = Depends(workspace_ctx)):
    ctx.require("admin")
    w, data = ctx.workspace, body.model_dump(exclude_unset=True)
    if "name" in data and data["name"]:
        w.name = data["name"].strip()
    if data.get("timezone"):
        w.timezone = data["timezone"]
    s = dict(w.settings or {})
    for k in ("quiet_start", "quiet_end", "approval_ttl_hours"):
        if k in data:
            if data[k] in (None, ""):
                s.pop(k, None)
            else:
                s[k] = data[k]
    w.settings = s
    audit(ctx.db, ctx.wid, ctx.user.name, "workspace.updated", "workspace", ctx.wid, fields=list(data))
    ctx.db.commit()
    return get_workspace(ctx)


# ---- members -------------------------------------------------------------------------------
class MemberIn(BaseModel):
    email: EmailStr
    name: str = Field(default="", max_length=120)
    role: str = "member"
    team: str = Field(default="", max_length=80)
    initial_password: str | None = Field(default=None, min_length=10, max_length=200)
    weekly_capacity: int = Field(default=10, ge=1, le=200)


class MemberPatch(BaseModel):
    role: str | None = None
    team: str | None = Field(default=None, max_length=80)
    weekly_capacity: int | None = Field(default=None, ge=1, le=200)


def _member_out(m: Membership) -> dict:
    return {"user_id": m.user_id, "name": m.user.name, "email": m.user.email, "role": m.role, "team": m.team, "weekly_capacity": m.weekly_capacity}


@router.get("/members")
def list_members(ctx: Ctx = Depends(workspace_ctx)):
    rows = ctx.db.scalars(select(Membership).where(Membership.workspace_id == ctx.wid).order_by(Membership.id)).all()
    return [_member_out(m) for m in rows]


def _check_role_change(ctx: Ctx, new_role: str) -> None:
    if new_role not in ROLES:
        raise HTTPException(422, "Unknown role")
    if new_role == "owner" and ctx.role != "owner":
        raise HTTPException(403, "Only an owner can grant the owner role")
    if ROLE_RANK[new_role] > ROLE_RANK[ctx.role]:
        raise HTTPException(403, "You cannot grant a role above your own")


@router.post("/members", status_code=201)
def add_member(body: MemberIn, ctx: Ctx = Depends(workspace_ctx)):
    ctx.require("admin")
    _check_role_change(ctx, body.role)
    email = body.email.lower()
    user = ctx.db.scalar(select(User).where(User.email == email))
    if not user:
        if not body.initial_password or not body.name.strip():
            raise HTTPException(422, "New people need a name and an initial password")
        user = User(email=email, name=body.name.strip(), password_hash=hash_password(body.initial_password))
        ctx.db.add(user)
        ctx.db.flush()
    if ctx.db.scalar(select(Membership).where(Membership.user_id == user.id, Membership.workspace_id == ctx.wid)):
        raise HTTPException(409, "This person is already a member")
    m = Membership(user_id=user.id, workspace_id=ctx.wid, role=body.role, team=body.team, weekly_capacity=body.weekly_capacity)
    ctx.db.add(m)
    audit(ctx.db, ctx.wid, ctx.user.name, "member.added", "user", user.id, role=body.role)
    ctx.db.commit()
    ctx.db.refresh(m)
    return _member_out(m)


@router.patch("/members/{user_id}")
def patch_member(user_id: int, body: MemberPatch, ctx: Ctx = Depends(workspace_ctx)):
    ctx.require("admin")
    m = ctx.db.scalar(select(Membership).where(Membership.user_id == user_id, Membership.workspace_id == ctx.wid))
    if not m:
        raise HTTPException(404, "Member not found")
    if body.role is not None:
        _check_role_change(ctx, body.role)
        if ROLE_RANK[m.role] > ROLE_RANK[ctx.role]:
            raise HTTPException(403, "You cannot change a role above your own")
        if m.role == "owner" and body.role != "owner":
            owners = ctx.db.scalar(select(func.count()).select_from(Membership).where(Membership.workspace_id == ctx.wid, Membership.role == "owner"))
            if owners <= 1:
                raise HTTPException(409, "A workspace needs at least one owner")
        audit(ctx.db, ctx.wid, ctx.user.name, "member.role_changed", "user", user_id, old=m.role, new=body.role)
        m.role = body.role
    if body.team is not None:
        m.team = body.team
    if body.weekly_capacity is not None:
        m.weekly_capacity = body.weekly_capacity
    ctx.db.commit()
    return _member_out(m)


# ---- contacts ------------------------------------------------------------------------------
class ContactIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(default="", max_length=255)
    phone: str = Field(default="", max_length=32)
    email_authorized: bool = False
    whatsapp_opt_in: bool = False
    user_id: int | None = None

    @field_validator("phone")
    @classmethod
    def _e164(cls, v):
        if v and not re.fullmatch(r"\+[1-9]\d{7,14}", v):
            raise ValueError("Phone must be in international format, e.g. +923001234567")
        return v

    @field_validator("email")
    @classmethod
    def _email(cls, v):
        if v and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v):
            raise ValueError("Enter a valid email address")
        return v


@router.get("/contacts")
def list_contacts(ctx: Ctx = Depends(workspace_ctx)):
    return [contact_out(c) for c in ctx.db.scalars(select(Contact).where(Contact.workspace_id == ctx.wid).order_by(Contact.name))]


@router.post("/contacts", status_code=201)
def create_contact(body: ContactIn, ctx: Ctx = Depends(workspace_ctx)):
    ctx.require("manager")
    c = Contact(workspace_id=ctx.wid, **body.model_dump())
    ctx.db.add(c)
    audit(
        ctx.db,
        ctx.wid,
        ctx.user.name,
        "contact.created",
        "contact",
        None,
        name=c.name,
        email_authorized=c.email_authorized,
        whatsapp_opt_in=c.whatsapp_opt_in,
    )
    ctx.db.commit()
    return contact_out(c)


@router.put("/contacts/{cid}")
def update_contact(cid: int, body: ContactIn, ctx: Ctx = Depends(workspace_ctx)):
    ctx.require("manager")
    c = get_owned(ctx, Contact, cid)
    for k, v in body.model_dump().items():
        setattr(c, k, v)
    audit(ctx.db, ctx.wid, ctx.user.name, "contact.updated", "contact", c.id, email_authorized=c.email_authorized, whatsapp_opt_in=c.whatsapp_opt_in)
    ctx.db.commit()
    return contact_out(c)


@router.delete("/contacts/{cid}", status_code=204)
def delete_contact(cid: int, ctx: Ctx = Depends(workspace_ctx)):
    ctx.require("manager")
    ctx.db.delete(get_owned(ctx, Contact, cid))
    ctx.db.commit()


# ---- reminder rules --------------------------------------------------------------------------
class RuleIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    trigger: str
    days: int = Field(ge=0, le=60)
    channel: str = "email"
    enabled: bool = True

    @field_validator("trigger")
    @classmethod
    def _t(cls, v):
        if v not in ("before_due", "overdue"):
            raise ValueError("Trigger must be before_due or overdue")
        return v

    @field_validator("channel")
    @classmethod
    def _c(cls, v):
        if v not in ("email", "whatsapp"):
            raise ValueError("Channel must be email or whatsapp")
        return v


def _rule_out(r: ReminderRule) -> dict:
    return {"id": r.id, "name": r.name, "trigger": r.trigger, "days": r.days, "channel": r.channel, "enabled": r.enabled}


@router.get("/reminder-rules")
def list_rules(ctx: Ctx = Depends(workspace_ctx)):
    return [_rule_out(r) for r in ctx.db.scalars(select(ReminderRule).where(ReminderRule.workspace_id == ctx.wid).order_by(ReminderRule.id))]


@router.post("/reminder-rules", status_code=201)
def create_rule(body: RuleIn, ctx: Ctx = Depends(workspace_ctx)):
    ctx.require("manager")
    r = ReminderRule(workspace_id=ctx.wid, **body.model_dump())
    ctx.db.add(r)
    ctx.db.commit()
    return _rule_out(r)


@router.put("/reminder-rules/{rid}")
def update_rule(rid: int, body: RuleIn, ctx: Ctx = Depends(workspace_ctx)):
    ctx.require("manager")
    r = get_owned(ctx, ReminderRule, rid)
    for k, v in body.model_dump().items():
        setattr(r, k, v)
    ctx.db.commit()
    return _rule_out(r)


@router.delete("/reminder-rules/{rid}", status_code=204)
def delete_rule(rid: int, ctx: Ctx = Depends(workspace_ctx)):
    ctx.require("manager")
    ctx.db.delete(get_owned(ctx, ReminderRule, rid))
    ctx.db.commit()


# ---- integrations ------------------------------------------------------------------------------
@router.get("/integrations")
def integrations(ctx: Ctx = Depends(workspace_ctx)):
    cfgs = {c.kind: c for c in ctx.db.scalars(select(IntegrationConfig).where(IntegrationConfig.workspace_id == ctx.wid))}
    s = get_settings()
    out = []
    for kind in ("email", "whatsapp", "calendar"):
        st = channel_status(kind)
        out.append({"kind": kind, "enabled": bool(cfgs.get(kind) and cfgs[kind].enabled), **st})
    llm_ready = s.llm_provider == "heuristic" or bool(s.gemini_api_key)
    out.append(
        {
            "kind": "ai",
            "enabled": True,
            "provider": "heuristic" if s.is_test else s.llm_provider,
            "ready": llm_ready,
            "message": "Rule-based extraction (no AI model). Set LLM_PROVIDER=gemini for model-based extraction."
            if s.llm_provider == "heuristic" or s.is_test
            else ("Ready" if llm_ready else "GEMINI_API_KEY is not set"),
        }
    )
    out.append(
        {
            "kind": "stt",
            "enabled": s.stt_provider != "none",
            "provider": s.stt_provider,
            "ready": s.stt_provider == "gemini" and bool(s.gemini_api_key),
            "message": "Ready"
            if s.stt_provider == "gemini" and s.gemini_api_key
            else "No speech-to-text provider configured. Transcript upload and paste still work.",
        }
    )
    return out


class IntegrationPatch(BaseModel):
    enabled: bool


@router.put("/integrations/{kind}")
def set_integration(kind: str, body: IntegrationPatch, ctx: Ctx = Depends(workspace_ctx)):
    ctx.require("admin")
    if kind not in ("email", "whatsapp", "calendar"):
        raise HTTPException(404, "Unknown integration")
    if body.enabled and not channel_status(kind)["ready"]:
        raise HTTPException(409, f"Cannot enable {kind}: {channel_status(kind)['message']}")
    cfg = ctx.db.scalar(select(IntegrationConfig).where(IntegrationConfig.workspace_id == ctx.wid, IntegrationConfig.kind == kind))
    if not cfg:
        cfg = IntegrationConfig(workspace_id=ctx.wid, kind=kind)
        ctx.db.add(cfg)
    cfg.enabled = body.enabled
    audit(ctx.db, ctx.wid, ctx.user.name, "integration.toggled", "integration", None, kind=kind, enabled=body.enabled)
    ctx.db.commit()
    return {"kind": kind, "enabled": cfg.enabled}


# ---- notifications / audit / jobs -----------------------------------------------------------------
@router.get("/notifications")
def notifications(ctx: Ctx = Depends(workspace_ctx)):
    rows = ctx.db.scalars(
        select(Notification)
        .where(Notification.workspace_id == ctx.wid, Notification.user_id == ctx.user.id)
        .order_by(Notification.id.desc())
        .limit(30)
    ).all()
    unread = ctx.db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.workspace_id == ctx.wid, Notification.user_id == ctx.user.id, Notification.read.is_(False))
    )
    return {
        "unread": unread,
        "items": [{"id": n.id, "kind": n.kind, "text": n.text, "link": n.link, "read": n.read, "created_at": iso(n.created_at)} for n in rows],
    }


@router.post("/notifications/read-all", status_code=204)
def read_all(ctx: Ctx = Depends(workspace_ctx)):
    for n in ctx.db.scalars(
        select(Notification).where(Notification.workspace_id == ctx.wid, Notification.user_id == ctx.user.id, Notification.read.is_(False))
    ):
        n.read = True
    ctx.db.commit()


@router.get("/audit")
def audit_log(ctx: Ctx = Depends(workspace_ctx)):
    ctx.require("admin")
    rows = ctx.db.scalars(select(AuditLog).where(AuditLog.workspace_id == ctx.wid).order_by(AuditLog.id.desc()).limit(100)).all()
    return [
        {"id": r.id, "at": iso(r.at), "actor": r.actor, "action": r.action, "entity": r.entity, "entity_id": r.entity_id, "detail": r.detail}
        for r in rows
    ]


@router.get("/jobs")
def jobs_health(ctx: Ctx = Depends(workspace_ctx)):
    ctx.require("admin")
    rows = ctx.db.execute(select(Job.status, func.count()).where(Job.workspace_id == ctx.wid).group_by(Job.status)).all()
    dead = ctx.db.scalars(select(Job).where(Job.workspace_id == ctx.wid, Job.status == "dead").order_by(Job.id.desc()).limit(10)).all()
    return {"counts": {s: n for s, n in rows}, "dead": [{"id": j.id, "kind": j.kind, "ref_id": j.ref_id, "error": j.last_error} for j in dead]}
