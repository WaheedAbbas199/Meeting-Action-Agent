"""Meeting memory (RAG). Local hashed lexical embeddings: dependency-free and deterministic.

Swap `embed` for a real embedding model + pgvector when semantic recall matters; the interface
(embed, search) stays the same. Retrieval is always filtered by workspace_id.
"""

import hashlib
import math
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Meeting, Segment
from app.services.transcript import fmt_ts

DIM = 384
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
    "that",
    "this",
    "it",
    "is",
    "be",
    "with",
    "our",
    "was",
    "what",
    "did",
    "do",
    "who",
    "when",
    "how",
    "are",
    "i",
    "you",
    "about",
    "have",
    "has",
    "will",
    "by",
    "at",
    "as",
    "or",
    "were",
}
MIN_SCORE = 0.18


def _stem(w: str) -> str:
    for suf in ("ing", "ed", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[: -len(suf)]
    return w


def _tokens(text: str) -> list[str]:
    return [_stem(w) for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP and len(w) > 1]


def embed(text: str) -> list[float]:
    toks = _tokens(text)
    vec = [0.0] * DIM
    for feat in toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:], strict=False)]:
        h = int(hashlib.md5(feat.encode()).hexdigest(), 16)
        vec[h % DIM] += 1.0 if "_" not in feat else 0.5
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [round(v / norm, 4) for v in vec]


def search(db: Session, workspace_id: int, query: str, k: int = 5) -> list[dict]:
    q = embed(query)
    rows = db.execute(
        select(Segment, Meeting)
        .join(Meeting, Meeting.id == Segment.meeting_id)
        .where(Segment.workspace_id == workspace_id, Meeting.workspace_id == workspace_id, Segment.embedding.is_not(None))
    ).all()
    scored = []
    for seg, mtg in rows:
        score = sum(a * b for a, b in zip(q, seg.embedding, strict=False))
        if score >= MIN_SCORE:
            scored.append((score, seg, mtg))
    scored.sort(key=lambda x: -x[0])
    return [
        {
            "meeting_id": m.id,
            "meeting_title": m.title,
            "held_on": m.held_on.isoformat(),
            "segment_idx": s.idx,
            "timestamp": fmt_ts(s.start_sec),
            "speaker": s.speaker,
            "text": s.text,
            "score": round(sc, 3),
        }
        for sc, s, m in scored[:k]
    ]
