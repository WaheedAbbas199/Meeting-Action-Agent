"""Team workload using priority-weighted open tasks against each member's weekly capacity."""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PRIORITY_WEIGHT, Membership, Task, User
from app.services.tasks import ACTIVE


def compute(db: Session, workspace_id: int, today: date | None = None) -> dict:
    today = today or date.today()
    members = db.execute(select(Membership, User).join(User, User.id == Membership.user_id).where(Membership.workspace_id == workspace_id)).all()
    tasks = db.scalars(select(Task).where(Task.workspace_id == workspace_id, Task.status.in_(ACTIVE), Task.review_state == "approved")).all()
    by_user: dict[int, dict] = {}
    for m, u in members:
        by_user[u.id] = {
            "user_id": u.id,
            "name": u.name,
            "team": m.team,
            "capacity": m.weekly_capacity,
            "points": 0,
            "open_tasks": 0,
            "due_this_week": 0,
            "task_ids": [],
        }
    unassigned = []
    names = {u.name.lower(): u.id for _, u in members}
    for t in tasks:
        uid = t.owner_user_id or names.get(t.owner_name.strip().lower())
        if uid in by_user:
            row = by_user[uid]
            row["points"] += PRIORITY_WEIGHT[t.priority]
            row["open_tasks"] += 1
            row["task_ids"].append(t.id)
            if t.due_date and t.due_date <= today + timedelta(days=7):
                row["due_this_week"] += 1
        else:
            unassigned.append({"id": t.id, "title": t.title, "owner_name": t.owner_name})
    rows = list(by_user.values())
    for r in rows:
        r["overloaded"] = r["points"] > r["capacity"]
        r["headroom"] = r["capacity"] - r["points"]
    suggestions = []
    headroom = {r["user_id"]: r["headroom"] for r in rows}
    task_by_id = {t.id: t for t in tasks}
    for r in sorted((x for x in rows if x["overloaded"]), key=lambda x: x["headroom"]):
        movable = sorted(
            (task_by_id[i] for i in r["task_ids"]), key=lambda t: (PRIORITY_WEIGHT[t.priority], -(t.due_date.toordinal() if t.due_date else 0))
        )
        over = -r["headroom"]
        for t in movable:
            if over <= 0:
                break
            w = PRIORITY_WEIGHT[t.priority]
            targets = [(h, uid) for uid, h in headroom.items() if uid != r["user_id"] and h >= w]
            if not targets:
                continue
            h, uid = max(targets)
            headroom[uid] -= w
            over -= w
            suggestions.append(
                {
                    "task_id": t.id,
                    "title": t.title,
                    "from_user_id": r["user_id"],
                    "from_name": r["name"],
                    "to_user_id": uid,
                    "to_name": by_user[uid]["name"],
                    "reason": f"{r['name']} carries {r['points']} of {r['capacity']} capacity points; {by_user[uid]['name']} has {h} free.",
                }
            )
    return {
        "members": rows,
        "unassigned": unassigned,
        "suggestions": suggestions,
        "note": "Load = sum of priority weights (low 1, medium 2, high 3, urgent 5) of open tasks vs. configured weekly capacity. It is a planning aid, not a performance score.",
    }
