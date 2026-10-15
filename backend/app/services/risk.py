"""Deterministic risk and blocker detection. Every risk carries the exact rule that triggered it."""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Task, TaskDependency
from app.services.tasks import ACTIVE, incomplete_prereqs


def transitive_dependents(db: Session, workspace_id: int, task_id: int) -> list[int]:
    edges = db.execute(select(TaskDependency.task_id, TaskDependency.depends_on_id).where(TaskDependency.workspace_id == workspace_id)).all()
    rev: dict[int, list[int]] = {}
    for t, d in edges:
        rev.setdefault(d, []).append(t)
    out, stack, seen = [], list(rev.get(task_id, [])), set()
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        out.append(cur)
        stack.extend(rev.get(cur, []))
    return sorted(out)


def compute_risks(db: Session, workspace_id: int, today: date | None = None) -> list[dict]:
    today = today or date.today()
    tasks = db.scalars(select(Task).where(Task.workspace_id == workspace_id, Task.status.in_(ACTIVE), Task.review_state == "approved")).all()
    titles = {t.id: t.title for t in tasks}
    risks: list[dict] = []

    def add(t: Task, kind: str, severity: str, why: str) -> None:
        deps = transitive_dependents(db, workspace_id, t.id)
        risks.append(
            {
                "task_id": t.id,
                "title": t.title,
                "kind": kind,
                "severity": severity,
                "explanation": why,
                "due_date": t.due_date.isoformat() if t.due_date else None,
                "owner_name": t.owner_name,
                "dependents_impacted": [{"id": i, "title": titles.get(i) or (db.get(Task, i).title if db.get(Task, i) else "")} for i in deps],
            }
        )

    for t in tasks:
        d = t.due_date
        soon = d is not None and d <= today + timedelta(days=7)
        if d is not None and d < today:
            add(t, "overdue", "high", f"Rule: due date {d} is {(today - d).days} day(s) before today and status is {t.status}.")
        elif d is not None and d <= today + timedelta(days=2) and t.status == "open":
            add(t, "due_soon", "medium", f"Rule: due in {(d - today).days} day(s) and work has not started (status open).")
        if t.status == "blocked":
            pending = incomplete_prereqs(db, t.id)
            why = ("Waiting on " + ", ".join(f"#{p.id} {p.title}" for p in pending)) if pending else (t.blocker_reason or "Blocked")
            sev = "high" if (d is not None and (d < today or soon)) else "medium"
            add(t, "blocked", sev, f"Rule: status is blocked. {why}." + (" Deadline is within 7 days or passed." if sev == "high" else ""))
        if not t.owner_name.strip() and soon:
            add(t, "no_owner", "medium", "Rule: no owner assigned and due within 7 days.")
        if t.deadline_changes >= 2:
            add(t, "deadline_slipped", "medium", f"Rule: deadline changed {t.deadline_changes} times (originally {t.original_due_date}).")
    order = {"high": 0, "medium": 1, "low": 2}
    risks.sort(key=lambda r: (order[r["severity"]], r["due_date"] or "9999"))
    return risks
