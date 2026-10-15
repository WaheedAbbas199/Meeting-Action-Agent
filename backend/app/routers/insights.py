from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import select, text

from app.db import get_db
from app.deps import Ctx, workspace_ctx
from app.models import Meeting, Task
from app.serializers import meeting_out, task_out
from app.services import analytics, risk

router = APIRouter(prefix="/api", tags=["insights"])


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/ready")
def ready(db=Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ready"}


@router.get("/w/{wid}/dashboard")
def dashboard(ctx: Ctx = Depends(workspace_ctx)):
    today = date.today()
    out = analytics.summary(ctx.db, ctx.wid, today)
    meetings = ctx.db.scalars(select(Meeting).where(Meeting.workspace_id == ctx.wid).order_by(Meeting.id.desc()).limit(5)).all()
    soon = ctx.db.scalars(
        select(Task)
        .where(Task.workspace_id == ctx.wid, Task.review_state == "approved", Task.status.in_(["open", "in_progress", "blocked"]))
        .order_by(Task.due_date.is_(None), Task.due_date)
        .limit(6)
    ).all()
    out["recent_meetings"] = [meeting_out(m) for m in meetings]
    out["upcoming_tasks"] = [task_out(t, today) for t in soon]
    out["recent_activity"] = analytics.recent_activity(ctx.db, ctx.wid)
    out["risks"] = risk.compute_risks(ctx.db, ctx.wid, today)[:5]
    out["is_demo"] = ctx.workspace.is_demo
    return out


@router.get("/w/{wid}/analytics")
def get_analytics(ctx: Ctx = Depends(workspace_ctx)):
    return analytics.full(ctx.db, ctx.wid)
