from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import case, func, or_, select

from app.deps import Ctx, get_owned, workspace_ctx
from app.models import PRIORITIES, Meeting, Segment, Task, TaskDependency, TaskEvent, User
from app.serializers import iso, task_out
from app.services import review, risk
from app.services import tasks as svc
from app.services.audit import audit
from app.services.tasks import ACTIVE

router = APIRouter(prefix="/api/w/{wid}", tags=["tasks"])
PRIORITY_ORDER = case(*[(Task.priority == p, i) for i, p in enumerate(["urgent", "high", "medium", "low"])], else_=9)


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=5000)
    owner_name: str = Field(default="", max_length=120)
    priority: str = "medium"
    due_date: date | None = None


class TaskPatch(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    owner_name: str | None = Field(default=None, max_length=120)
    owner_user_id: int | None = None
    priority: str | None = None
    due_date: date | None = None


class StatusIn(BaseModel):
    status: str
    blocker_reason: str = Field(default="", max_length=1000)


class DepIn(BaseModel):
    depends_on_id: int


class ReassignIn(BaseModel):
    user_id: int


def _can_edit(ctx: Ctx, t: Task) -> bool:
    return ctx.can("manager") or (ctx.can("member") and t.owner_user_id in (None, ctx.user.id))


@router.get("/tasks")
def list_tasks(
    ctx: Ctx = Depends(workspace_ctx),
    status: str | None = None,
    owner: str | None = None,
    priority: str | None = None,
    q: str | None = Query(default=None, max_length=100),
    due: str | None = None,
    review_state: str = "approved",
    sort: str = "due",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    stmt = select(Task).where(Task.workspace_id == ctx.wid)
    if review_state != "all":
        stmt = stmt.where(Task.review_state == review_state)
    if status:
        stmt = stmt.where(Task.status.in_([s for s in status.split(",") if s]))
    if priority:
        stmt = stmt.where(Task.priority.in_([p for p in priority.split(",") if p in PRIORITIES]))
    if owner == "me":
        stmt = stmt.where(Task.owner_user_id == ctx.user.id)
    elif owner == "unassigned":
        stmt = stmt.where(Task.owner_name == "")
    elif owner:
        stmt = stmt.where(Task.owner_name.ilike(f"%{owner}%"))
    if q:
        stmt = stmt.where(or_(Task.title.ilike(f"%{q}%"), Task.owner_name.ilike(f"%{q}%")))
    today = date.today()
    if due == "overdue":
        stmt = stmt.where(Task.due_date < today, Task.status.in_(ACTIVE))
    elif due == "soon":
        stmt = stmt.where(Task.due_date >= today, Task.due_date <= date.fromordinal(today.toordinal() + 7), Task.status.in_(ACTIVE))
    elif due == "none":
        stmt = stmt.where(Task.due_date.is_(None))
    total = ctx.db.scalar(select(func.count()).select_from(stmt.subquery()))
    order = {
        "due": [Task.due_date.is_(None), Task.due_date, Task.id],
        "priority": [PRIORITY_ORDER, Task.due_date, Task.id],
        "created": [Task.id.desc()],
        "title": [Task.title],
    }.get(sort, [Task.id])
    rows = ctx.db.scalars(stmt.order_by(*order).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [task_out(t) for t in rows], "total": total, "page": page, "page_size": page_size}


@router.post("/tasks", status_code=201)
def create_task(body: TaskIn, ctx: Ctx = Depends(workspace_ctx)):
    ctx.require("member")
    if body.priority not in PRIORITIES:
        raise HTTPException(422, "Invalid priority")
    uid, _ = svc.resolve_owner(ctx.db, ctx.wid, body.owner_name)
    t = Task(
        workspace_id=ctx.wid,
        title=body.title.strip(),
        description=body.description,
        owner_name=body.owner_name.strip(),
        owner_user_id=uid,
        priority=body.priority,
        due_date=body.due_date,
        status="open",
        review_state="approved",
        confidence=1.0,
    )
    ctx.db.add(t)
    ctx.db.flush()
    svc.log_event(ctx.db, t, ctx.user.name, "created")
    audit(ctx.db, ctx.wid, ctx.user.name, "task.created", "task", t.id)
    ctx.db.commit()
    return task_out(t)


@router.get("/tasks/{tid}")
def get_task(tid: int, ctx: Ctx = Depends(workspace_ctx)):
    t = get_owned(ctx, Task, tid)
    db = ctx.db
    prereqs = [{"id": p.id, "title": p.title, "status": p.status} for p in svc.prerequisites(db, t.id) if p]
    deps = [db.get(Task, i) for i in svc.dependents_of(db, t.id)]
    events = db.scalars(select(TaskEvent).where(TaskEvent.task_id == t.id).order_by(TaskEvent.id.desc()).limit(50)).all()
    mtg = db.get(Meeting, t.meeting_id) if t.meeting_id else None
    context = []
    if mtg and t.segment_idx is not None:
        for s in db.scalars(
            select(Segment).where(Segment.meeting_id == mtg.id, Segment.idx.between(t.segment_idx - 1, t.segment_idx + 1)).order_by(Segment.idx)
        ):
            context.append({"idx": s.idx, "speaker": s.speaker, "text": s.text, "is_evidence": s.idx == t.segment_idx})
    return {
        **task_out(t),
        "prerequisites": prereqs,
        "dependents": [{"id": d.id, "title": d.title, "status": d.status} for d in deps if d],
        "meeting": {"id": mtg.id, "title": mtg.title, "held_on": iso(mtg.held_on)} if mtg else None,
        "evidence_context": context,
        "events": [{"at": iso(e.at), "actor": e.actor, "kind": e.kind, "field": e.field, "old": e.old_value, "new": e.new_value} for e in events],
        "can_edit": _can_edit(ctx, t),
    }


@router.patch("/tasks/{tid}")
def patch_task(tid: int, body: TaskPatch, ctx: Ctx = Depends(workspace_ctx)):
    ctx.require("member")
    t = get_owned(ctx, Task, tid)
    if not _can_edit(ctx, t):
        raise HTTPException(403, "You can only edit tasks you own, unassigned tasks, or any task as a manager")
    changes = body.model_dump(exclude_unset=True)
    if "owner_user_id" in changes and changes["owner_user_id"] is not None:
        u = ctx.db.get(User, changes["owner_user_id"])
        member_ids = {m["user_id"] for m in []}  # validated below via workload helper
        from app.models import Membership

        if not u or not ctx.db.scalar(select(Membership).where(Membership.user_id == u.id, Membership.workspace_id == ctx.wid)):
            raise HTTPException(422, "That person is not a member of this workspace")
        changes["owner_name"] = u.name
        del member_ids
    elif "owner_name" in changes:
        changes["owner_user_id"], _ = svc.resolve_owner(ctx.db, ctx.wid, changes["owner_name"] or "")
    if "owner_name" in changes and not ctx.can("manager") and changes.get("owner_user_id") not in (None, ctx.user.id):
        raise HTTPException(403, "Only managers can assign tasks to other people")
    if "title" in changes and changes["title"] is not None:
        changes["title"] = changes["title"].strip()
    changes = {k: v for k, v in changes.items() if not (k in ("title", "priority") and v is None)}
    svc.update_fields(ctx.db, t, changes, ctx.user)
    ctx.db.commit()
    return task_out(t)


@router.post("/tasks/{tid}/status")
def set_status(tid: int, body: StatusIn, ctx: Ctx = Depends(workspace_ctx)):
    ctx.require("member")
    t = get_owned(ctx, Task, tid)
    if not _can_edit(ctx, t):
        raise HTTPException(403, "You can only change the status of tasks you own, unassigned tasks, or any task as a manager")
    svc.set_status(ctx.db, t, body.status, ctx.user.name, body.blocker_reason)
    audit(ctx.db, ctx.wid, ctx.user.name, "task.status", "task", t.id, status=body.status)
    ctx.db.commit()
    ctx.db.refresh(t)
    return task_out(t)


@router.post("/tasks/{tid}/approve")
def approve(tid: int, ctx: Ctx = Depends(workspace_ctx)):
    ctx.require("manager")
    t = get_owned(ctx, Task, tid)
    review.approve_task(ctx.db, t, ctx.user)
    if t.meeting_id:
        review.refresh_meeting_status(ctx.db, ctx.db.get(Meeting, t.meeting_id))
    ctx.db.commit()
    return task_out(t)


@router.post("/tasks/{tid}/reject")
def reject(tid: int, ctx: Ctx = Depends(workspace_ctx)):
    ctx.require("manager")
    t = get_owned(ctx, Task, tid)
    review.reject_task(ctx.db, t, ctx.user)
    if t.meeting_id:
        review.refresh_meeting_status(ctx.db, ctx.db.get(Meeting, t.meeting_id))
    ctx.db.commit()
    return task_out(t)


@router.post("/tasks/{tid}/dependencies", status_code=201)
def add_dep(tid: int, body: DepIn, ctx: Ctx = Depends(workspace_ctx)):
    ctx.require("member")
    t, p = get_owned(ctx, Task, tid), get_owned(ctx, Task, body.depends_on_id)
    if not _can_edit(ctx, t):
        raise HTTPException(403, "You cannot change dependencies of this task")
    svc.add_dependency(ctx.db, t, p, ctx.user.name)
    ctx.db.commit()
    ctx.db.refresh(t)
    return task_out(t)


@router.delete("/tasks/{tid}/dependencies/{pid}")
def remove_dep(tid: int, pid: int, ctx: Ctx = Depends(workspace_ctx)):
    ctx.require("member")
    t = get_owned(ctx, Task, tid)
    if not _can_edit(ctx, t):
        raise HTTPException(403, "You cannot change dependencies of this task")
    svc.remove_dependency(ctx.db, t, pid, ctx.user.name)
    ctx.db.commit()
    ctx.db.refresh(t)
    return task_out(t)


@router.get("/dependency-graph")
def graph(ctx: Ctx = Depends(workspace_ctx)):
    edges = ctx.db.execute(select(TaskDependency.task_id, TaskDependency.depends_on_id).where(TaskDependency.workspace_id == ctx.wid)).all()
    ids = {i for e in edges for i in e}
    nodes = ctx.db.scalars(select(Task).where(Task.id.in_(ids or {0}), Task.workspace_id == ctx.wid)).all()
    return {
        "nodes": [{"id": n.id, "title": n.title, "status": n.status, "due_date": iso(n.due_date)} for n in nodes],
        "edges": [{"task_id": a, "depends_on_id": b} for a, b in edges],
    }


@router.get("/risks")
def risks(ctx: Ctx = Depends(workspace_ctx)):
    return {
        "items": risk.compute_risks(ctx.db, ctx.wid),
        "note": "Each risk shows the deterministic rule that triggered it. No predictions are made.",
    }
