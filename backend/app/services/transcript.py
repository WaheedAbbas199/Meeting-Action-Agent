"""Transcript parsing (plain, bracketed timestamps, VTT, SRT), evidence checks, injection flags."""

import re

INJECTION_PATTERNS = [
    r"ignore (?:all |any )?(?:the )?(?:previous|prior|above|earlier) (?:instructions|rules|prompts?)",
    r"disregard (?:the |all )?(?:above|previous|system|rules|instructions)",
    r"system prompt",
    r"you are now (?:a|an|the)\b",
    r"reveal (?:your|the) (?:instructions|prompt|api key|secrets?)",
    r"override (?:the )?(?:approval|policy|safety)",
]
_INJ = re.compile("|".join(INJECTION_PATTERNS), re.I)
_NOT_SPEAKERS = {"action item", "action", "todo", "to-do", "decision", "note", "notes", "summary", "agenda", "question"}
_TS = r"(?:(\d{1,2}):)?(\d{1,2}):(\d{2})(?:[.,]\d+)?"
_BRACKET = re.compile(rf"^\[?\(?{_TS}\)?\]?\s*(.*)$")
_SPEAKER = re.compile(r"^([A-Z][\w .'\-]{0,40}?):\s+(.+)$")
_CUE = re.compile(rf"^{_TS}\s*-->\s*{_TS}")


def _secs(h, m, s) -> float:
    return int(h or 0) * 3600 + int(m) * 60 + int(s)


def parse_transcript(text: str) -> list[dict]:
    text = text.replace("\r\n", "\n").replace("\ufeff", "").strip()
    segs: list[dict] = []
    if "-->" in text:
        for block in re.split(r"\n\s*\n", re.sub(r"^WEBVTT.*\n", "", text)):
            lines = [ln.strip() for ln in block.split("\n") if ln.strip() and not ln.strip().isdigit()]
            cue = next((i for i, ln in enumerate(lines) if _CUE.match(ln)), None)
            if cue is None:
                continue
            c = _CUE.match(lines[cue])
            body = " ".join(re.sub(r"</?v[^>]*>|<[^>]+>", "", ln) for ln in lines[cue + 1 :])
            vm = re.match(r"<v ([^>]+)>", " ".join(lines[cue + 1 :]))
            speaker = vm.group(1) if vm else ""
            sm = _SPEAKER.match(body)
            if sm and sm.group(1).lower() not in _NOT_SPEAKERS:
                speaker, body = sm.group(1), sm.group(2)
            if body:
                segs.append({"idx": len(segs), "start_sec": _secs(c[1], c[2], c[3]), "speaker": speaker, "text": body})
        return segs
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        start = None
        bm = _BRACKET.match(line) if re.match(r"^[\[(]?\d{1,2}:\d{2}", line) else None
        if bm:
            start = _secs(bm[1], bm[2], bm[3])
            line = bm[4].strip()
        speaker = ""
        sm = _SPEAKER.match(line)
        if sm and sm.group(1).lower() not in _NOT_SPEAKERS:
            speaker, line = sm.group(1).strip(), sm.group(2).strip()
        if line:
            segs.append({"idx": len(segs), "start_sec": start, "speaker": speaker, "text": line})
    return segs


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def locate_quote(quote: str, segments: list[dict]) -> int | None:
    """Return the index of the segment containing the verbatim (normalized) quote, else None."""
    q = norm(quote)
    if len(q) < 6:
        return None
    for seg in segments:
        if q in norm(seg["text"]):
            return seg["idx"]
    joined = " ".join(norm(s["text"]) for s in segments)
    return -1 if q in joined else None  # spans segments: supported but no single index


def injection_segments(segments: list[dict]) -> list[int]:
    return [s["idx"] for s in segments if _INJ.search(s["text"])]


def fmt_ts(sec: float | None) -> str:
    if sec is None:
        return ""
    sec = int(sec)
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"
