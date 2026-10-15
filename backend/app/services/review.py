"""Human review of AI-extracted items. Nothing becomes an active task/decision without approval."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Decision, Meeting, Task, User
from app.services.audit import audit
from app.services.tasks import RuleError, incomplete_prereqs, log_event, reevaluate_blocking


def approve_task(db: Session, task: Task, user: User) -> None:
    if task.review_state != "pending":
        raise RuleError(f"This task was already {task.review_state}")
    task.review_state, task.status = "approved", "open"
    log_event(db, task, user.name, "approved", "review_state", "pending", "approved")
    db.flush()
    if incomplete_prereqs(db, task.id):
        reevaluate_blocking(db, task.workspace_id, [task.id], user.name)
    elif task.blocker_reason.strip():  # stated blocker with no linked task
        task.status, task.auto_blocked = "blocked", False
    audit(db, task.workspace_id, user.name, "task.approved", "task", task.id)


def reject_task(db: Session, task: Task, user: User) -> None:
    if task.review_state != "pending":
        raise RuleError(f"This task was already {task.review_state}")
    task.review_state, task.status = "rejected", "rejected"
    log_event(db, task, user.name, "rejected", "review_state", "pending", "rejected")
    from app.services.tasks import dependents_of

    deps = dependents_of(db, task.id)
    db.flush()
    if deps:
        reevaluate_blocking(db, task.workspace_id, deps, user.name)
    audit(db, task.workspace_id, user.name, "task.rejected", "task", task.id)


def review_decision(db: Session, d: Decision, user: User, approve: bool) -> None:
    if d.review_state != "pending":
        raise RuleError(f"This item was already {d.review_state}")
    d.review_state = "approved" if approve else "rejected"
    if not approve:
        d.status = "dismissed"
    audit(db, d.workspace_id, user.name, f"decision.{d.review_state}", "decision", d.id)


def refresh_meeting_status(db: Session, m: Meeting) -> None:
    db.flush()
    if m.status not in ("review", "completed"):
        return
    pending_t = db.scalar(select(Task.id).where(Task.meeting_id == m.id, Task.review_state == "pending").limit(1))
    pending_d = db.scalar(select(Decision.id).where(Decision.meeting_id == m.id, Decision.review_state == "pending").limit(1))
    m.status = "review" if (pending_t or pending_d) else "completed"
