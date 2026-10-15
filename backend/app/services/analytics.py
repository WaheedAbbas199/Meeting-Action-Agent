"""Metrics are computed from database records with the definitions returned in `definitions`."""

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Approval, Correction, Decision, FollowUp, Meeting, Task, TaskEvent
from app.services.tasks import ACTIVE

DEFINITIONS = {
    "open_tasks": "Approved tasks with status open, in_progress or blocked.",
    "overdue": "Open tasks whose due date is before today.",
    "due_soon": "Open tasks due within the next 3 days (including today) that are not blocked.",
    "blocked": "Open tasks with status blocked.",
    "pending_decisions": "Approved decisions not yet confirmed, plus decisions with an unresolved conflict.",
    "pending_approvals": "Approvals waiting for a decision and not yet expired.",
    "completion_rate": "done / (done + open) among approved tasks. Null when there are no tasks.",
    "on_time_completion_rate": "Share of done tasks with a due date that were completed on or before it. Null when none qualify.",
}


def _rate(n: int, d: int) -> float | None:
    return None if d == 0 else round(n / d, 3)


def summary(db: Session, wid: int, today: date | None = None) -> dict:
    today = today or date.today()
    approved = select(Task).where(Task.workspace_id == wid, Task.review_state == "approved")
    tasks = db.scalars(approved).all()
    active = [t for t in tasks if t.status in ACTIVE]
    done = [t for t in tasks if t.status == "done"]
    overdue = [t for t in active if t.due_date and t.due_date < today]
    due_soon = [t for t in active if t.due_date and today <= t.due_date <= today + timedelta(days=3) and t.status != "blocked"]
    dated_done = [t for t in done if t.due_date and t.completed_at]
    on_time = [t for t in dated_done if t.completed_at.date() <= t.due_date]
    pending_dec = (
        db.scalar(
            select(func.count())
            .select_from(Decision)
            .where(
                Decision.workspace_id == wid,
                Decision.kind == "decision",
                (((Decision.review_state == "approved") & (Decision.status == "proposed")) | (Decision.conflict_state == "open")),
            )
        )
        or 0
    )
    pending_appr = db.scalar(select(func.count()).select_from(Approval).where(Approval.workspace_id == wid, Approval.status == "pending")) or 0
    return {
        "open_tasks": len(active),
        "overdue": len(overdue),
        "due_soon": len(due_soon),
        "blocked": sum(1 for t in active if t.status == "blocked"),
        "pending_decisions": pending_dec,
        "pending_approvals": pending_appr,
        "completed": len(done),
        "completion_rate": _rate(len(done), len(done) + len(active)),
        "on_time_completion_rate": _rate(len(on_time), len(dated_done)),
        "definitions": DEFINITIONS,
    }


def full(db: Session, wid: int, today: date | None = None) -> dict:
    today = today or date.today()
    out = summary(db, wid, today)
    fus = db.scalars(select(FollowUp).where(FollowUp.workspace_id == wid)).all()
    by_status: dict[str, int] = defaultdict(int)
    for f in fus:
        by_status[f.status] += 1
    out["followups"] = {"total": len(fus), "attempts": sum(f.attempts for f in fus), "by_status": dict(by_status)}
    tasks = db.scalars(select(Task).where(Task.workspace_id == wid, Task.review_state == "approved")).all()
    out["deadline_changes"] = {"total": sum(t.deadline_changes for t in tasks), "tasks_affected": sum(1 for t in tasks if t.deadline_changes)}
    # weekly trends (ISO weeks, last 8)
    monday = today - timedelta(days=today.weekday())
    weeks = [monday - timedelta(weeks=i) for i in range(7, -1, -1)]
    created = {w: 0 for w in weeks}
    completed = {w: 0 for w in weeks}
    for t in tasks:
        cw = t.created_at.date() - timedelta(days=t.created_at.date().weekday())
        if cw in created:
            created[cw] += 1
        if t.completed_at:
            dw = t.completed_at.date() - timedelta(days=t.completed_at.date().weekday())
            if dw in completed:
                completed[dw] += 1
    active_weeks = sum(1 for w in weeks if created[w] or completed[w])
    out["trends"] = {
        "weeks": [w.isoformat() for w in weeks],
        "created": [created[w] for w in weeks],
        "completed": [completed[w] for w in weeks],
        "sufficient": active_weeks >= 2,
        "note": "" if active_weeks >= 2 else "Trends need task activity in at least two different weeks.",
    }
    ai_tasks = [t for t in db.scalars(select(Task).where(Task.workspace_id == wid, Task.meeting_id.is_not(None))).all()]
    corrected = (
        db.scalar(select(func.count(func.distinct(Correction.entity_id))).where(Correction.workspace_id == wid, Correction.entity == "task")) or 0
    )
    approved_n = sum(1 for t in ai_tasks if t.review_state == "approved")
    rejected_n = sum(1 for t in ai_tasks if t.review_state == "rejected")
    out["ai_quality"] = {
        "extracted": len(ai_tasks),
        "approved": approved_n,
        "rejected": rejected_n,
        "corrected": corrected,
        "correction_rate": _rate(corrected, approved_n),
        "acceptance_rate": _rate(approved_n, approved_n + rejected_n),
    }
    meetings = db.scalars(select(Meeting).where(Meeting.workspace_id == wid).order_by(Meeting.created_at.desc()).limit(10)).all()
    eff = []
    for m in meetings:
        mt = [t for t in tasks if t.meeting_id == m.id]
        eff.append(
            {
                "meeting_id": m.id,
                "title": m.title,
                "held_on": m.held_on.isoformat(),
                "tasks": len(mt),
                "with_owner": sum(1 for t in mt if t.owner_name),
                "with_deadline": sum(1 for t in mt if t.due_date),
                "completed": sum(1 for t in mt if t.status == "done"),
            }
        )
    out["meeting_effectiveness"] = eff
    return out


def recent_activity(db: Session, wid: int, limit: int = 10) -> list[dict]:
    rows = db.scalars(select(TaskEvent).where(TaskEvent.workspace_id == wid).order_by(TaskEvent.id.desc()).limit(limit)).all()
    titles = {t.id: t.title for t in db.scalars(select(Task).where(Task.id.in_([r.task_id for r in rows] or [0])))}
    return [
        {
            "at": r.at.isoformat() + "Z",
            "actor": r.actor,
            "kind": r.kind,
            "field": r.field,
            "old": r.old_value,
            "new": r.new_value,
            "task_id": r.task_id,
            "task_title": titles.get(r.task_id, ""),
        }
        for r in rows
    ]
