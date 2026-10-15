"""Decision conflict detection. Heuristic and advisory: a human must confirm or dismiss every conflict."""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Decision
from app.services.audit import audit

STOP = {
    "the",
    "a",
    "an",
    "to",
    "of",
    "and",
    "for",
    "on",
    "in",
    "we",
    "will",
    "that",
    "this",
    "it",
    "is",
    "be",
    "with",
    "our",
    "decided",
    "agreed",
    "decision",
    "going",
    "go",
    "are",
    "let",
    "plan",
    "by",
    "at",
    "as",
    "or",
}
NEGATION = {
    "not",
    "no",
    "never",
    "don't",
    "dont",
    "won't",
    "wont",
    "cancel",
    "cancelled",
    "canceled",
    "drop",
    "dropped",
    "without",
    "instead",
    "stop",
}
VALUE = re.compile(
    r"\d{4}-\d{2}-\d{2}|\$?\d[\d,.]*%?|january|february|march|april|may|june|july|august|september|october|november|december|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday",
    re.I,
)


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9']+", text.lower()) if w not in STOP and w not in NEGATION and not VALUE.fullmatch(w) and len(w) > 2}


def _values(text: str) -> set[str]:
    return {v.lower().rstrip(".,") for v in VALUE.findall(text)}


def _negated(text: str) -> bool:
    return bool(set(re.findall(r"[a-z']+", text.lower())) & NEGATION)


def compare(a: str, b: str) -> str | None:
    """Return a human-readable conflict reason, or None if the statements do not conflict."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return None
    jac = len(ta & tb) / len(ta | tb)
    if jac < 0.35:
        return None
    shared = ", ".join(sorted(ta & tb)[:4])
    va, vb = _values(a), _values(b)
    if va and vb and va != vb:
        return f"Both statements concern '{shared}' but give different values: {', '.join(sorted(va))} vs {', '.join(sorted(vb))}."
    if _negated(a) != _negated(b):
        return f"Both statements concern '{shared}' but one is negated or cancels the other."
    return None


def detect_conflicts(db: Session, workspace_id: int, new_ids: list[int]) -> int:
    existing = db.scalars(
        select(Decision).where(
            Decision.workspace_id == workspace_id,
            Decision.kind == "decision",
            Decision.review_state == "approved",
            Decision.status.in_(["proposed", "confirmed"]),
            Decision.id.notin_(new_ids or [0]),
        )
    ).all()
    found = 0
    for nid in new_ids:
        new = db.get(Decision, nid)
        if not new or new.kind != "decision":
            continue
        for old in existing:
            reason = compare(old.text, new.text)
            if reason:
                new.conflicts_with_id, new.conflict_reason, new.conflict_state = old.id, reason, "open"
                found += 1
                break
    return found


def resolve_conflict(db: Session, d: Decision, action: str, actor: str) -> None:
    if d.conflict_state != "open" or d.conflicts_with_id is None:
        raise ValueError("This decision has no open conflict")
    old = db.get(Decision, d.conflicts_with_id)
    if action == "confirm":  # the newer statement replaces the older; the older is kept as history
        d.status, d.conflict_state = "confirmed", "confirmed"
        if old:
            old.status = "superseded"
    elif action == "dismiss":  # not a real conflict: both stay as recorded
        d.conflict_state = "dismissed"
    else:
        raise ValueError("Action must be confirm or dismiss")
    audit(db, d.workspace_id, actor, f"decision.conflict_{action}", "decision", d.id, supersedes=d.conflicts_with_id)
