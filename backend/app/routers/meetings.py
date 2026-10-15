import uuid
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.config import get_settings
from app.deps import Ctx, get_owned, workspace_ctx
from app.models import Decision, Job, Meeting, Segment, Task
from app.providers.base import ProviderNotConfigured
from app.providers.stt import AUDIO_MIME, get_stt
from app.serializers import decision_out, meeting_out, task_out
from app.services import jobs, review
from app.services.audit import audit
from app.services.transcript import fmt_ts

router = APIRouter(prefix="/api/w/{wid}/meetings", tags=["meetings"])
TEXT_EXT = {".txt", ".vtt", ".srt", ".md"}


class MeetingIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    timezone: str = "UTC"
    held_on: date | None = None
    transcript_text: str = Field(min_length=10, max_length=500_000)


def _today(tz: str) -> date:
    try:
        return datetime.now(ZoneInfo(tz)).date()
    except Exception:  # noqa: BLE001
        raise HTTPException(422, "Unknown timezone") from None


def _detail(ctx: Ctx, m: Meeting) -> dict:
    db = ctx.db
    segs = db.scalars(select(Segment).where(Segment.meeting_id == m.id).order_by(Segment.idx)).all()
    tasks = db.scalars(select(Task).where(Task.meeting_id == m.id, Task.workspace_id == ctx.wid).order_by(Task.id)).all()
    decs = db.scalars(select(Decision).where(Decision.meeting_id == m.id, Decision.workspace_id == ctx.wid).order_by(Decision.id)).all()
    return {
        **meeting_out(m),
        "transcript_text": m.transcript_text,
        "segments": [{"idx": s.idx, "timestamp": fmt_ts(s.start_sec), "speaker": s.speaker, "text": s.text} for s in segs],
        "tasks": [task_out(t) for t in tasks],
        "decisions": [decision_out(d) for d in decs],
    }


@router.get("")
def list_meetings(ctx: Ctx = Depends(workspace_ctx)):
    rows = ctx.db.scalars(select(Meeting).where(Meeting.workspace_id == ctx.wid).order_by(Meeting.id.desc()).limit(100)).all()
    out = []
    for m in rows:
        pending = len(ctx.db.scalars(select(Task.id).where(Task.meeting_id == m.id, Task.review_state == "pending")).all())
        out.append({**meeting_out(m), "pending_review": pending})
    return out


@router.post("", status_code=201)
def create_meeting(body: MeetingIn, ctx: Ctx = Depends(workspace_ctx)):
    ctx.require("member")
    m = Meeting(
        workspace_id=ctx.wid,
        title=body.title.strip(),
        timezone=body.timezone,
        held_on=body.held_on or _today(body.timezone),
        transcript_text=body.transcript_text,
        created_by=ctx.user.id,
        status="queued",
        stage_log=[{"stage": "queued", "at": datetime.utcnow().isoformat(), "detail": ""}],
    )
    ctx.db.add(m)
    ctx.db.flush()
    jobs.enqueue(ctx.db, ctx.wid, "process_meeting", m.id)
    audit(ctx.db, ctx.wid, ctx.user.name, "meeting.created", "meeting", m.id)
    ctx.db.commit()
    return meeting_out(m)


@router.post("/upload", status_code=201)
async def upload_meeting(
    title: str = Form(..., min_length=1, max_length=200),
    timezone: str = Form("UTC"),
    held_on: date | None = Form(None),
    file: UploadFile = File(...),
    ctx: Ctx = Depends(workspace_ctx),
):
    ctx.require("member")
    s = get_settings()
    name = Path(file.filename or "upload").name
    ext = Path(name).suffix.lower()
    data = await file.read(s.max_upload_bytes + 1)
    if len(data) > s.max_upload_bytes:
        raise HTTPException(413, f"File is larger than {s.max_upload_bytes // (1024 * 1024)} MB")
    if not data:
        raise HTTPException(422, "The file is empty")
    payload: dict = {}
    text = ""
    if ext in TEXT_EXT:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise HTTPException(422, "Transcript files must be UTF-8 text") from None
        if len(text.strip()) < 10:
            raise HTTPException(422, "The transcript is too short")
        source = "transcript"
    elif ext in AUDIO_MIME:
        try:
            get_stt()
        except ProviderNotConfigured as e:
            raise HTTPException(409, str(e)) from None
        updir = Path(s.upload_dir) / str(ctx.wid)
        updir.mkdir(parents=True, exist_ok=True)
        path = updir / f"{uuid.uuid4().hex}{ext}"
        path.write_bytes(data)
        payload, source = {"audio_path": str(path)}, "audio"
    else:
        raise HTTPException(415, "Upload a .txt, .vtt, .srt or audio file (.mp3, .wav, .m4a, .ogg, .flac, .aac)")
    m = Meeting(
        workspace_id=ctx.wid,
        title=title.strip(),
        timezone=timezone,
        held_on=held_on or _today(timezone),
        source_type=source,
        filename=name,
        transcript_text=text,
        created_by=ctx.user.id,
        status="queued",
        stage_log=[{"stage": "queued", "at": datetime.utcnow().isoformat(), "detail": name}],
    )
    ctx.db.add(m)
    ctx.db.flush()
    jobs.enqueue(ctx.db, ctx.wid, "process_meeting", m.id, payload)
    audit(ctx.db, ctx.wid, ctx.user.name, "meeting.uploaded", "meeting", m.id, source=source)
    ctx.db.commit()
    return meeting_out(m)


@router.get("/{mid}")
def get_meeting(mid: int, ctx: Ctx = Depends(workspace_ctx)):
    return _detail(ctx, get_owned(ctx, Meeting, mid))


@router.post("/{mid}/retry")
def retry_meeting(mid: int, ctx: Ctx = Depends(workspace_ctx)):
    ctx.require("member")
    m = get_owned(ctx, Meeting, mid)
    if m.status != "failed":
        raise HTTPException(409, "Only failed meetings can be retried")
    last = ctx.db.scalar(select(Job).where(Job.kind == "process_meeting", Job.ref_id == m.id).order_by(Job.id.desc()))
    m.status, m.error = "queued", ""
    m.stage_log = [*m.stage_log, {"stage": "retry_requested", "at": datetime.utcnow().isoformat(), "detail": ctx.user.name}]
    jobs.enqueue(ctx.db, ctx.wid, "process_meeting", m.id, dict(last.payload) if last else {})
    audit(ctx.db, ctx.wid, ctx.user.name, "meeting.retry", "meeting", m.id)
    ctx.db.commit()
    return meeting_out(m)


class ReviewIn(BaseModel):
    tasks: list[dict] = Field(default_factory=list)  # [{"id": 1, "action": "approve"|"reject"}]
    decisions: list[dict] = Field(default_factory=list)


@router.post("/{mid}/review")
def review_meeting(mid: int, body: ReviewIn, ctx: Ctx = Depends(workspace_ctx)):
    ctx.require("manager")
    m = get_owned(ctx, Meeting, mid)
    for item in body.tasks:
        t = get_owned(ctx, Task, int(item["id"]))
        if t.meeting_id != m.id:
            raise HTTPException(404, "Task not found in this meeting")
        if item.get("action") == "approve":
            review.approve_task(ctx.db, t, ctx.user)
        elif item.get("action") == "reject":
            review.reject_task(ctx.db, t, ctx.user)
        else:
            raise HTTPException(422, "Action must be approve or reject")
    for item in body.decisions:
        d = get_owned(ctx, Decision, int(item["id"]))
        if d.meeting_id != m.id:
            raise HTTPException(404, "Decision not found in this meeting")
        if item.get("action") not in ("approve", "reject"):
            raise HTTPException(422, "Action must be approve or reject")
        review.review_decision(ctx.db, d, ctx.user, item["action"] == "approve")
    review.refresh_meeting_status(ctx.db, m)
    ctx.db.commit()
    return _detail(ctx, m)
