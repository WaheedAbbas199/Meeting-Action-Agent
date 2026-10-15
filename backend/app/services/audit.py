"""Audit trail and in-app notifications."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, Membership, Notification


def audit(db: Session, workspace_id: int | None, actor: str, action: str, entity: str = "", entity_id: int | None = None, **detail) -> None:
    db.add(AuditLog(workspace_id=workspace_id, actor=actor, action=action, entity=entity, entity_id=entity_id, detail=detail))


def notify(db: Session, workspace_id: int, user_id: int, kind: str, text: str, link: str = "") -> None:
    db.add(Notification(workspace_id=workspace_id, user_id=user_id, kind=kind, text=text[:400], link=link))


def notify_managers(db: Session, workspace_id: int, kind: str, text: str, link: str = "") -> None:
    rows = db.scalars(select(Membership).where(Membership.workspace_id == workspace_id, Membership.role.in_(["manager", "admin", "owner"])))
    for m in rows:
        notify(db, workspace_id, m.user_id, kind, text, link)
