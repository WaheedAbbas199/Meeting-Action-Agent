"""Task rules: status transitions, dependency graph (cycle-safe), blocking re-evaluation, history."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PRIORITIES, Correction, Membership, Task, TaskDependency, TaskEvent, User, utcnow  # noqa: F401
from app.services.audit import audit

ACTIVE = ("open", "in_progress", "blocked")
FINAL = ("done", "rejected")
MANUAL_STATUSES = ("open", "in_progress", "blocked", "done")


class RuleError(ValueError):
    """A business rule was violated (mapped to HTTP 409/422 by the API layer)."""


def log_event(db: Session, task: Task, actor: str, kind: str, field: str = "", old="", new="") -> None:
    db.add(
        TaskEvent(
            workspace_id=task.workspace_id,
            task_id=task.id,
            actor=actor,
            kind=kind,
            field=field,
            old_value="" if old is None else str(old),
            new_value="" if new is None else str(new),
        )
    )


def prerequisites(db: Session, task_id: int) -> list[Task]:
    ids = db.scalars(select(TaskDependency.depends_on_id).where(TaskDependency.task_id == task_id)).all()
    return [db.get(Task, i) for i in ids] if ids else []


def dependents_of(db: Session, task_id: int) -> list[int]:
    return list(db.scalars(select(TaskDependency.task_id).where(TaskDependency.depends_on_id == task_id)))


def incomplete_prereqs(db: Session, task_id: int) -> list[Task]:
    # rejected prerequisites were cancelled, so they no longer block
    return [t for t in prerequisites(db, task_id) if t and t.status not in ("done", "rejected")]


def would_create_cycle(db: Session, task_id: int, depends_on_id: int) -> bool:
    if task_id == depends_on_id:
        return True
    seen: set[int] = set()
    stack = [depends_on_id]
    while stack:
        cur = stack.pop()
        if cur == task_id:
            return True
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(db.scalars(select(TaskDependency.depends_on_id).where(TaskDependency.task_id == cur)))
    return False


def add_dependency(db: Session, task: Task, prereq: Task, actor: str) -> None:
    if task.workspace_id != prereq.workspace_id:
        raise RuleError("Tasks must belong to the same workspace")
    if would_create_cycle(db, task.id, prereq.id):
        raise RuleError("This dependency would create a cycle")
    exists = db.scalar(select(TaskDependency).where(TaskDependency.task_id == task.id, TaskDependency.depends_on_id == prereq.id))
    if exists:
        return
    db.add(TaskDependency(workspace_id=task.workspace_id, task_id=task.id, depends_on_id=prereq.id))
    db.flush()
    log_event(db, task, actor, "dependency_added", "depends_on", "", f"#{prereq.id} {prereq.title}")
    reevaluate_blocking(db, task.workspace_id, [task.id], actor)


def remove_dependency(db: Session, task: Task, prereq_id: int, actor: str) -> None:
    row = db.scalar(select(TaskDependency).where(TaskDependency.task_id == task.id, TaskDependency.depends_on_id == prereq_id))
    if row:
        db.delete(row)
        db.flush()
        log_event(db, task, actor, "dependency_removed", "depends_on", f"#{prereq_id}", "")
        reevaluate_blocking(db, task.workspace_id, [task.id], actor)


def reevaluate_blocking(db: Session, workspace_id: int, task_ids: list[int] | None = None, actor: str = "system") -> list[int]:
    """Recompute automatic blocking. Returns ids whose status changed."""
    q = select(Task).where(Task.workspace_id == workspace_id, Task.status.in_(ACTIVE))
    if task_ids is not None:
        q = q.where(Task.id.in_(task_ids))
    changed: list[int] = []
    for t in db.scalars(q).all():
        pending = incomplete_prereqs(db, t.id)
        if pending and not (t.status == "blocked" and t.auto_blocked):
            reason = "Waiting on " + ", ".join(f"#{p.id} {p.title}" for p in pending)
            old = t.status
            t.status, t.auto_blocked, t.blocker_reason = "blocked", True, reason
            log_event(db, t, actor, "status_changed", "status", old, "blocked")
            changed.append(t.id)
        elif pending and t.auto_blocked:
            t.blocker_reason = "Waiting on " + ", ".join(f"#{p.id} {p.title}" for p in pending)
        elif not pending and t.status == "blocked" and t.auto_blocked:
            t.status, t.auto_blocked, t.blocker_reason = "open", False, ""
            log_event(db, t, actor, "status_changed", "status", "blocked", "open (prerequisites done)")
            changed.append(t.id)
    return changed


def set_status(db: Session, task: Task, new: str, actor: str, blocker_reason: str = "") -> None:
    if new not in MANUAL_STATUSES:
        raise RuleError(f"Status must be one of {', '.join(MANUAL_STATUSES)}")
    if task.review_state != "approved" or task.status in ("proposed", "rejected"):
        raise RuleError("Approve this item in the meeting review before changing its status")
    old = task.status
    if new == old:
        return
    pending = incomplete_prereqs(db, task.id)
    if new in ("in_progress", "done") and pending:
        raise RuleError("Blocked by incomplete prerequisites: " + ", ".join(f"#{p.id}" for p in pending))
    if new == "blocked":
        if not blocker_reason.strip():
            raise RuleError("A blocker reason is required")
        task.auto_blocked, task.blocker_reason = False, blocker_reason.strip()
    else:
        if old == "blocked" and not task.auto_blocked:
            task.blocker_reason = ""
    task.status = new
    task.completed_at = utcnow() if new == "done" else None
    log_event(db, task, actor, "status_changed", "status", old, new)
    db.flush()
    if new == "open" and pending:  # reopened but prerequisites remain
        reevaluate_blocking(db, task.workspace_id, [task.id], actor)
    # completing/reopening changes what depends on it
    deps = dependents_of(db, task.id)
    if deps:
        reevaluate_blocking(db, task.workspace_id, deps, actor)


def _remember_correction(db: Session, task: Task, field: str, old, new, user_id: int | None) -> None:
    if task.meeting_id is None or str(old) == str(new):
        return
    first = db.scalar(
        select(Correction).where(Correction.entity == "task", Correction.entity_id == task.id, Correction.field == field).order_by(Correction.id)
    )
    ai_value = first.ai_value if first else ("" if old is None else str(old))
    db.add(
        Correction(
            workspace_id=task.workspace_id,
            entity="task",
            entity_id=task.id,
            field=field,
            ai_value=ai_value,
            user_value="" if new is None else str(new),
            created_by=user_id,
        )
    )


def update_fields(db: Session, task: Task, changes: dict, user: User) -> None:
    actor = user.name
    for field, new in changes.items():
        if field == "priority" and new not in PRIORITIES:
            raise RuleError("Invalid priority")
        if field == "title" and not str(new).strip():
            raise RuleError("Title cannot be empty")
        old = getattr(task, field)
        if old == new:
            continue
        if field == "due_date":
            if task.due_date is not None and new is not None:
                task.deadline_changes += 1
            if task.original_due_date is None and task.due_date is not None:
                task.original_due_date = task.due_date
            task.due_inferred = False
            if "due_date" in (task.uncertain_fields or []):
                task.uncertain_fields = [f for f in task.uncertain_fields if f != "due_date"]
        if field == "owner_name" and "owner" in (task.uncertain_fields or []):
            task.uncertain_fields = [f for f in task.uncertain_fields if f != "owner"]
        setattr(task, field, new)
        log_event(db, task, actor, "field_changed", field, old, new)
        if field in ("title", "owner_name", "due_date", "priority"):
            _remember_correction(db, task, field, old, new, user.id)
    audit(db, task.workspace_id, actor, "task.update", "task", task.id, fields=list(changes))


def resolve_owner(db: Session, workspace_id: int, name: str) -> tuple[int | None, bool]:
    """Match a spoken name to a unique workspace member. Returns (user_id, ambiguous)."""
    name = (name or "").strip().lower()
    if not name:
        return None, False
    rows = db.execute(select(Membership, User).join(User, User.id == Membership.user_id).where(Membership.workspace_id == workspace_id)).all()
    exact = [u.id for _, u in rows if u.name.lower() == name]
    if len(exact) == 1:
        return exact[0], False
    first = [u.id for _, u in rows if u.name.lower().split()[0] == name.split()[0]]
    if len(first) == 1:
        return first[0], False
    return None, len(first) > 1 or len(exact) > 1


def days_until(due: date | None, today: date) -> int | None:
    return None if due is None else (due - today).days
