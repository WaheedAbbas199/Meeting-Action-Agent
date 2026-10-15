"""Follow-up drafting, human approval workflow and guarded execution.

Execution always revalidates approval, expiry, task state, recipient authorization, approver role,
integration toggle, rate limit and quiet hours immediately before sending.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import utcnow
from app.models import ROLE_RANK, Approval, Contact, FollowUp, IntegrationConfig, Meeting, Membership, Task, Workspace
from app.providers.base import ProviderError, TransientProviderError
from app.providers.messaging import get_channel
from app.services.audit import audit, notify, notify_managers
from app.services.tasks import RuleError


class Deferred(Exception):
    """Execution postponed (quiet hours / rate limit). Does not consume a retry attempt."""

    def __init__(self, until: datetime, why: str) -> None:
        super().__init__(why)
        self.until, self.why = until, why


def render_body(db: Session, task: Task, contact: Contact, channel: str) -> tuple[str, str]:
    mtg = db.get(Meeting, task.meeting_id) if task.meeting_id else None
    due = task.due_date.isoformat() if task.due_date else "no deadline set"
    src = f' (from "{mtg.title}" on {mtg.held_on})' if mtg else ""
    subject = f"Reminder: {task.title}"
    if channel == "whatsapp":
        return "", f'Hi {contact.name}, reminder about "{task.title}"{src}. Due: {due}. Reply here if you\'re blocked.'
    return subject, (
        f'Hi {contact.name},\n\nThis is a reminder about your commitment: "{task.title}"{src}.\n'
        f"Due: {due}. Status: {task.status}.\n\nIf you're blocked or the deadline needs to change, please reply.\n"
    )


def check_recipient(contact: Contact, channel: str) -> None:
    if channel == "email":
        if not contact.email:
            raise RuleError("This contact has no email address")
        if not contact.email_authorized:
            raise RuleError("This contact has not been authorized to receive email from this workspace")
    elif channel == "whatsapp":
        if not contact.phone:
            raise RuleError("This contact has no WhatsApp phone number")
        if not contact.whatsapp_opt_in:
            raise RuleError("This contact has not opted in to WhatsApp messages")
    else:
        raise RuleError("Channel must be email or whatsapp")


def create_draft(
    db: Session, wid: int, task: Task, contact: Contact, channel: str, user_id: int | None, reminder_key: str = ""
) -> tuple[FollowUp, bool]:
    check_recipient(contact, channel)
    key = f"task{task.id}:{channel}:c{contact.id}:{reminder_key or utcnow().date().isoformat()}"
    existing = db.scalar(select(FollowUp).where(FollowUp.workspace_id == wid, FollowUp.idempotency_key == key))
    if existing:
        return existing, False
    subject, body = render_body(db, task, contact, channel)
    fu = FollowUp(
        workspace_id=wid, task_id=task.id, contact_id=contact.id, channel=channel, subject=subject, body=body, idempotency_key=key, created_by=user_id
    )
    db.add(fu)
    db.flush()
    return fu, True


def _ttl(db: Session, wid: int) -> timedelta:
    ws = db.get(Workspace, wid)
    hours = (ws.settings or {}).get("approval_ttl_hours", get_settings().approval_ttl_hours) if ws else get_settings().approval_ttl_hours
    return timedelta(hours=int(hours))


def request_approval(db: Session, fu: FollowUp, user_id: int) -> Approval:
    if fu.status not in ("draft", "rejected", "expired", "revoked", "failed"):
        raise RuleError(f"A {fu.status} follow-up cannot be submitted for approval")
    contact, task = db.get(Contact, fu.contact_id) if fu.contact_id else None, db.get(Task, fu.task_id) if fu.task_id else None
    if not contact or not task:
        raise RuleError("The follow-up needs a task and a recipient")
    check_recipient(contact, fu.channel)
    to = contact.email if fu.channel == "email" else contact.phone
    ap = Approval(
        workspace_id=fu.workspace_id,
        kind="followup",
        ref_id=fu.id,
        requested_by=user_id,
        expires_at=utcnow() + _ttl(db, fu.workspace_id),
        payload={
            "channel": fu.channel,
            "to": to,
            "recipient": contact.name,
            "subject": fu.subject,
            "body": fu.body,
            "task_id": task.id,
            "task_title": task.title,
        },
    )
    db.add(ap)
    fu.status = "pending_approval"
    db.flush()
    notify_managers(db, fu.workspace_id, "approval", f"{fu.channel.title()} follow-up to {contact.name} needs approval", "#/approvals")
    return ap


def _sync_followup(db: Session, ap: Approval, status: str, err: str = "") -> None:
    if ap.kind == "followup":
        fu = db.get(FollowUp, ap.ref_id)
        if fu and fu.status not in ("sent",):
            fu.status = status
            if err:
                fu.last_error = err


def decide(db: Session, ap: Approval, user_id: int, approve: bool, note: str = "") -> None:
    from app.services import jobs

    if ap.status != "pending":
        raise RuleError(f"This approval is already {ap.status}")
    if ap.expires_at <= utcnow():
        ap.status = "expired"
        _sync_followup(db, ap, "expired")
        raise RuleError("This approval has expired. Submit the follow-up again")
    ap.decided_by, ap.decided_at, ap.decision_note = user_id, utcnow(), note
    if approve:
        ap.status = "approved"
        if ap.kind == "followup":
            _sync_followup(db, ap, "approved")
            jobs.enqueue(db, ap.workspace_id, "send_followup", ap.ref_id)
        else:
            jobs.enqueue(db, ap.workspace_id, "create_event", ap.id)
    else:
        ap.status = "rejected"
        _sync_followup(db, ap, "rejected")
    audit(db, ap.workspace_id, f"user:{user_id}", f"approval.{ap.status}", "approval", ap.id, kind=ap.kind)


def revoke(db: Session, ap: Approval, user_id: int) -> None:
    if ap.status not in ("approved", "pending"):
        raise RuleError(f"A {ap.status} approval cannot be revoked")
    if ap.kind == "followup":
        fu = db.get(FollowUp, ap.ref_id)
        if fu and fu.status == "sent":
            raise RuleError("This message was already sent")
    ap.status = "revoked"
    _sync_followup(db, ap, "revoked")
    audit(db, ap.workspace_id, f"user:{user_id}", "approval.revoked", "approval", ap.id)


def expire_stale(db: Session) -> int:
    now, n = utcnow(), 0
    for ap in db.scalars(select(Approval).where(Approval.status.in_(["pending", "approved"]), Approval.expires_at <= now)):
        if ap.kind == "followup":
            fu = db.get(FollowUp, ap.ref_id)
            if fu and fu.status == "sent":
                continue
        ap.status = "expired"
        _sync_followup(db, ap, "expired")
        n += 1
    return n


def _in_quiet_hours(ws: Workspace, now_utc: datetime) -> datetime | None:
    s = ws.settings or {}
    qs, qe = s.get("quiet_start"), s.get("quiet_end")
    if not qs or not qe:
        return None
    try:
        tz = ZoneInfo(ws.timezone or "UTC")
        local = now_utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)
        sh, sm = map(int, qs.split(":"))
        eh, em = map(int, qe.split(":"))
    except (ValueError, KeyError):
        return None
    cur, start, end = local.hour * 60 + local.minute, sh * 60 + sm, eh * 60 + em
    inside = (start <= cur < end) if start < end else (cur >= start or cur < end)
    if not inside:
        return None
    end_local = local.replace(hour=eh, minute=em, second=0, microsecond=0)
    if end_local <= local:
        end_local += timedelta(days=1)
    return end_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def _stop(db: Session, msg: str) -> RuleError:
    """Persist the terminal state set just before refusing (the job runner rolls back on errors)."""
    db.commit()
    return RuleError(msg)


def execute_followup(db: Session, followup_id: int) -> str:
    fu = db.get(FollowUp, followup_id)
    if not fu:
        return "missing"
    if fu.status == "sent":
        return "already_sent"  # idempotent no-op
    ap = db.scalar(select(Approval).where(Approval.kind == "followup", Approval.ref_id == fu.id).order_by(Approval.id.desc()))
    now = utcnow()
    if fu.status not in ("approved", "scheduled", "sending") or not ap or ap.status != "approved":
        raise RuleError("No valid approval for this follow-up")
    if ap.expires_at <= now:
        ap.status, fu.status = "expired", "expired"
        raise _stop(db, "The approval expired before sending")
    task, contact = db.get(Task, fu.task_id) if fu.task_id else None, db.get(Contact, fu.contact_id) if fu.contact_id else None
    if not task or task.status in ("done", "rejected"):
        ap.status, fu.status, fu.last_error = "revoked", "revoked", "Task is no longer open; follow-up cancelled"
        raise _stop(db, fu.last_error)
    if not contact:
        raise RuleError("Recipient no longer exists")
    try:
        check_recipient(contact, fu.channel)
    except RuleError as e:
        fu.status, fu.last_error, ap.status = "failed", str(e), "failed"
        db.commit()
        raise
    approver = db.scalar(select(Membership).where(Membership.user_id == ap.decided_by, Membership.workspace_id == fu.workspace_id))
    if not approver or ROLE_RANK[approver.role] < ROLE_RANK["manager"]:
        ap.status, fu.status, fu.last_error = "revoked", "revoked", "Approver no longer has permission"
        raise _stop(db, fu.last_error)
    cfg = db.scalar(select(IntegrationConfig).where(IntegrationConfig.workspace_id == fu.workspace_id, IntegrationConfig.kind == fu.channel))
    if not cfg or not cfg.enabled:
        raise RuleError(f"{fu.channel.title()} sending is not enabled for this workspace")
    ws = db.get(Workspace, fu.workspace_id)
    until = _in_quiet_hours(ws, now)
    if until:
        fu.status = "scheduled"
        raise Deferred(until, "Quiet hours")
    sent_last_hour = (
        db.scalar(
            select(func.count()).select_from(FollowUp).where(FollowUp.workspace_id == fu.workspace_id, FollowUp.sent_at > now - timedelta(hours=1))
        )
        or 0
    )
    if sent_last_hour >= get_settings().sends_per_hour:
        fu.status = "scheduled"
        raise Deferred(now + timedelta(minutes=10), "Hourly send limit reached")
    provider = get_channel(fu.channel)  # raises ProviderNotConfigured (permanent) if disabled
    fu.status, fu.attempts = "sending", fu.attempts + 1
    db.commit()
    to = contact.email if fu.channel == "email" else contact.phone
    try:
        res = provider.send(to, fu.body, fu.subject, idempotency_key=fu.idempotency_key)
    except TransientProviderError as e:
        fu.status, fu.last_error = "scheduled", str(e)
        db.commit()
        raise
    except ProviderError as e:
        fu.status, fu.last_error, ap.status = "failed", str(e), "failed"
        audit(db, fu.workspace_id, "system", "followup.failed", "followup", fu.id, error=str(e))
        db.commit()
        raise
    fu.status, fu.sent_at, fu.provider_message_id, fu.last_error = "sent", utcnow(), res.message_id, ""
    fu.delivery_status = ""  # only set from provider webhooks, never assumed
    ap.status = "executed"
    audit(db, fu.workspace_id, "system", "followup.sent", "followup", fu.id, channel=fu.channel)
    if fu.created_by:
        notify(db, fu.workspace_id, fu.created_by, "followup", f"{fu.channel.title()} sent to {contact.name}", "#/followups")
    return "sent"
