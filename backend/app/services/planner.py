"""Next-meeting agenda planner. Items come from data with an explicit reason; nothing is invented."""

import uuid
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Agenda, AgendaRevision, Decision, Task
from app.services.tasks import ACTIVE, incomplete_prereqs


def build_items(db: Session, workspace_id: int, today: date | None = None) -> list[dict]:
    today = today or date.today()
    items: list[dict] = []

    def add(kind, title, reason, ref_type, ref_id, minutes=5):
        items.append(
            {"id": uuid.uuid4().hex[:8], "kind": kind, "title": title, "reason": reason, "ref": {"type": ref_type, "id": ref_id}, "minutes": minutes}
        )

    tasks = db.scalars(
        select(Task)
        .where(Task.workspace_id == workspace_id, Task.status.in_(ACTIVE), Task.review_state == "approved")
        .order_by(Task.due_date.is_(None), Task.due_date)
    ).all()
    for t in tasks:
        if t.due_date and t.due_date < today:
            add(
                "overdue",
                f"Overdue: {t.title}",
                f"Due {t.due_date} ({(today - t.due_date).days} day(s) ago). Owner: {t.owner_name or 'unassigned'}.",
                "task",
                t.id,
            )
    for t in tasks:
        if t.status == "blocked":
            pending = incomplete_prereqs(db, t.id)
            why = ("Waiting on " + ", ".join(f"#{p.id}" for p in pending)) if pending else (t.blocker_reason or "No reason recorded")
            add("blocked", f"Unblock: {t.title}", why, "task", t.id)
    for t in tasks:
        if t.due_date and today <= t.due_date <= today + timedelta(days=7) and t.status != "blocked":
            add("due_soon", f"Check progress: {t.title}", f"Due {t.due_date}. Status: {t.status}.", "task", t.id, 3)
    for d in db.scalars(
        select(Decision).where(Decision.workspace_id == workspace_id, Decision.kind == "decision", Decision.conflict_state == "open")
    ):
        add("conflict", f"Resolve conflicting decisions: {d.topic or d.text[:50]}", d.conflict_reason, "decision", d.id, 10)
    for d in db.scalars(
        select(Decision).where(
            Decision.workspace_id == workspace_id, Decision.kind == "question", Decision.review_state == "approved", Decision.status.in_(["proposed"])
        )
    ):
        add("question", f"Open question: {d.text[:120]}", "Raised in an earlier meeting and not yet resolved.", "decision", d.id)
    return items


def create_agenda(db: Session, workspace_id: int, title: str, user_id: int | None) -> Agenda:
    ag = Agenda(workspace_id=workspace_id, title=title, items=build_items(db, workspace_id))
    db.add(ag)
    db.flush()
    db.add(AgendaRevision(agenda_id=ag.id, revision=1, title=ag.title, items=ag.items, edited_by=user_id))
    return ag


def edit_agenda(db: Session, ag: Agenda, title: str, items: list[dict], user_id: int) -> None:
    ag.title, ag.items, ag.revision, ag.status, ag.approved_by = title, items, ag.revision + 1, "draft", None
    db.add(AgendaRevision(agenda_id=ag.id, revision=ag.revision, title=title, items=items, edited_by=user_id))
