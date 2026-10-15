"""LangGraph pipeline: load -> (transcribe) -> parse -> extract -> verify -> persist.

Controlled workflow, not a free-form agent: the LLM only produces schema-validated candidates.
Evidence is verified deterministically, and nothing reaches the task list without human review.
"""

import re
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import utcnow
from app.models import Decision, Meeting, Segment, Task, TaskDependency
from app.providers.base import ProviderError
from app.providers.llm import get_llm
from app.providers.stt import get_stt
from app.services import memory
from app.services.audit import audit, notify
from app.services.dates import parse_due
from app.services.decisions import detect_conflicts
from app.services.tasks import ACTIVE, resolve_owner, would_create_cycle
from app.services.transcript import injection_segments, locate_quote, parse_transcript


class State(TypedDict, total=False):
    meeting_id: int
    skip: bool
    needs_stt: bool
    segments: list[dict]
    extraction: Any
    tasks: list[dict]
    decisions: list[dict]
    warnings: list[str]


def _stage(db: Session, m: Meeting, status: str, stage: str, detail: str = "") -> None:
    m.status = status
    m.stage_log = [*(m.stage_log or []), {"stage": stage, "at": utcnow().isoformat(), "detail": detail}]
    db.commit()


def _sim(a: str, b: str) -> float:
    ta, tb = set(re.findall(r"[a-z0-9]{3,}", a.lower())), set(re.findall(r"[a-z0-9]{3,}", b.lower()))
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0


def build_graph(db: Session, payload: dict):
    g = StateGraph(State)

    def load(s: State) -> State:
        m = db.get(Meeting, s["meeting_id"])
        if m is None:
            raise ProviderError("Meeting not found")
        if m.status in ("review", "completed"):
            return {"skip": True}
        needs = m.source_type == "audio" and not m.transcript_text
        _stage(db, m, "transcribing" if needs else "extracting", "started")
        return {"skip": False, "needs_stt": needs, "warnings": []}

    def transcribe(s: State) -> State:
        m = db.get(Meeting, s["meeting_id"])
        path = Path(payload.get("audio_path", ""))
        if not path.is_file():
            raise ProviderError("Uploaded audio file is missing; upload it again")
        text = get_stt().transcribe(path.read_bytes(), m.filename)  # may raise (not configured / transient)
        m.transcript_text = text
        path.unlink(missing_ok=True)  # raw audio is not retained once transcribed
        _stage(db, m, "extracting", "transcribed", f"{len(text)} characters")
        return {}

    def parse(s: State) -> State:
        m = db.get(Meeting, s["meeting_id"])
        segs = parse_transcript(m.transcript_text)
        if not segs:
            raise ProviderError("The transcript is empty or could not be parsed")
        _stage(db, m, "extracting", "parsed", f"{len(segs)} segments")
        return {"segments": segs}

    def extract(s: State) -> State:
        res = get_llm().extract(s["segments"])
        m = db.get(Meeting, s["meeting_id"])
        _stage(db, m, "extracting", "extracted", f"{len(res.tasks)} task candidates, {len(res.decisions)} decision candidates")
        return {"extraction": res}

    def verify(s: State) -> State:
        m, segs, res = db.get(Meeting, s["meeting_id"]), s["segments"], s["extraction"]
        warnings: list[str] = []
        bad = set(injection_segments(segs))
        if bad:
            warnings.append(
                f"Possible prompt-injection text found in segment(s) {sorted(bad)}. Related items are marked low-confidence; instructions in transcripts are never executed."
            )
        tasks, dropped = [], 0
        for t in res.tasks:
            idx = locate_quote(t.evidence_quote, segs)
            if idx is None:
                dropped += 1
                continue
            due = parse_due(t.due_text, m.held_on)
            uncertain = []
            owner_id, ambiguous = resolve_owner(db, m.workspace_id, t.owner)
            if not t.owner or ambiguous:
                uncertain.append("owner")
            if due.uncertain:
                uncertain.append("due_date")
            conf = min(t.confidence, 0.3) if idx in bad else t.confidence
            tasks.append(
                {
                    "title": t.title,
                    "owner": t.owner,
                    "owner_id": owner_id,
                    "due": due,
                    "priority": t.priority,
                    "quote": t.evidence_quote,
                    "idx": None if idx < 0 else idx,
                    "conf": conf,
                    "uncertain": uncertain,
                    "deps": t.depends_on_titles,
                    "blocker": t.blocker,
                }
            )
        decisions = []
        for d in res.decisions:
            idx = locate_quote(d.evidence_quote, segs)
            if idx is None:
                dropped += 1
                continue
            decisions.append(
                {
                    "text": d.text,
                    "topic": d.topic,
                    "quote": d.evidence_quote,
                    "idx": None if idx < 0 else idx,
                    "conf": min(d.confidence, 0.3) if idx in bad else d.confidence,
                    "kind": d.kind,
                }
            )
        if dropped:
            warnings.append(f"{dropped} candidate item(s) were discarded because their evidence quote was not found in the transcript.")
        _stage(db, m, "extracting", "verified", f"{len(tasks)} tasks and {len(decisions)} decisions have evidence")
        return {"tasks": tasks, "decisions": decisions, "warnings": warnings}

    def persist(s: State) -> State:
        m = db.get(Meeting, s["meeting_id"])
        wid = m.workspace_id
        db.execute(delete(Segment).where(Segment.meeting_id == m.id))
        for seg in s["segments"]:
            db.add(
                Segment(
                    meeting_id=m.id,
                    workspace_id=wid,
                    idx=seg["idx"],
                    start_sec=seg["start_sec"],
                    speaker=seg["speaker"],
                    text=seg["text"],
                    embedding=memory.embed(seg["text"]),
                )
            )
        created: list[Task] = []
        for t in s["tasks"]:
            due = t["due"]
            row = Task(
                workspace_id=wid,
                meeting_id=m.id,
                title=t["title"],
                owner_name=t["owner"],
                owner_user_id=t["owner_id"],
                priority=t["priority"],
                status="proposed",
                review_state="pending",
                due_date=due.due,
                due_inferred=due.inferred,
                evidence_quote=t["quote"],
                segment_idx=t["idx"],
                confidence=t["conf"],
                uncertain_fields=t["uncertain"],
                blocker_reason=t["blocker"],
            )
            db.add(row)
            created.append(row)
        new_dec: list[Decision] = []
        for d in s["decisions"]:
            row = Decision(
                workspace_id=wid,
                meeting_id=m.id,
                kind=d["kind"],
                text=d["text"],
                topic=d["topic"],
                evidence_quote=d["quote"],
                segment_idx=d["idx"],
                confidence=d["conf"],
            )
            db.add(row)
            new_dec.append(row)
        db.flush()
        # dependency links by fuzzy title match against this meeting's tasks and existing open tasks
        existing = db.scalars(
            select(Task).where(Task.workspace_id == wid, Task.status.in_(ACTIVE), Task.id.notin_([c.id for c in created] or [0]))
        ).all()
        for row, t in zip(created, s["tasks"], strict=True):
            for title in t["deps"]:
                cands = [c for c in [*created, *existing] if c.id != row.id]
                best = max(cands, key=lambda c: _sim(title, c.title), default=None)
                if best and _sim(title, best.title) >= 0.5 and not would_create_cycle(db, row.id, best.id):
                    db.add(TaskDependency(workspace_id=wid, task_id=row.id, depends_on_id=best.id))
        conflicts = detect_conflicts(db, wid, [d.id for d in new_dec])
        warnings = list(s.get("warnings", []))
        if conflicts:
            warnings.append(f"{conflicts} decision(s) may conflict with earlier decisions. Review them in the Decision center.")
        m.summary = s["extraction"].summary
        m.warnings = warnings
        m.error = ""
        total = len(created) + len(new_dec)
        m.status = "review" if total else "completed"
        m.stage_log = [
            *(m.stage_log or []),
            {
                "stage": "ready_for_review" if total else "completed",
                "at": utcnow().isoformat(),
                "detail": f"{len(created)} tasks, {len(new_dec)} decisions",
            },
        ]
        audit(db, wid, "system", "meeting.processed", "meeting", m.id, tasks=len(created), decisions=len(new_dec))
        if m.created_by:
            notify(db, wid, m.created_by, "meeting", f'"{m.title}" is ready for review', f"#/meetings/{m.id}")
        db.commit()
        return {}

    for name, fn in [("load", load), ("transcribe", transcribe), ("parse", parse), ("extract", extract), ("verify", verify), ("persist", persist)]:
        g.add_node(name, fn)
    g.set_entry_point("load")
    g.add_conditional_edges(
        "load",
        lambda s: "end" if s["skip"] else ("transcribe" if s["needs_stt"] else "parse"),
        {"end": END, "transcribe": "transcribe", "parse": "parse"},
    )
    g.add_edge("transcribe", "parse")
    g.add_edge("parse", "extract")
    g.add_edge("extract", "verify")
    g.add_edge("verify", "persist")
    g.add_edge("persist", END)
    return g.compile()


def process_meeting(db: Session, meeting_id: int, payload: dict | None = None) -> None:
    build_graph(db, payload or {}).invoke({"meeting_id": meeting_id})
