"""Optional calendar integration: proposing an event requires approval; execution is provider-gated.

Only the mock provider exists. A real Google Calendar provider is NOT implemented (documented blocker).
"""

from sqlalchemy.orm import Session

from app.db import utcnow
from app.models import Agenda, Approval
from app.providers.messaging import get_channel
from app.services.audit import audit
from app.services.tasks import RuleError


def propose(db: Session, ag: Agenda, start_iso: str, user_id: int, ttl) -> Approval:
    if ag.status != "approved":
        raise RuleError("Approve the agenda before proposing a calendar event")
    ap = Approval(
        workspace_id=ag.workspace_id,
        kind="calendar_event",
        ref_id=ag.id,
        requested_by=user_id,
        expires_at=utcnow() + ttl,
        payload={"title": ag.title, "start": start_iso, "agenda_id": ag.id, "items": len(ag.items)},
    )
    db.add(ap)
    db.flush()
    return ap


def execute(db: Session, approval_id: int) -> str:
    ap = db.get(Approval, approval_id)
    if not ap or ap.status != "approved" or ap.expires_at <= utcnow():
        raise RuleError("No valid approval for this calendar event")
    provider = get_channel("calendar")
    res = provider.send("calendar", ap.payload.get("title", ""), subject=ap.payload.get("start", ""), idempotency_key=f"cal{ap.id}")
    ap.status = "executed"
    ap.payload = {**ap.payload, "event_id": res.message_id}
    audit(db, ap.workspace_id, "system", "calendar.created", "approval", ap.id)
    return "created"
