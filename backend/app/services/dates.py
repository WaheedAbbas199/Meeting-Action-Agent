"""Deterministic deadline interpretation. Dates are never guessed silently: ambiguity is flagged."""

import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}


@dataclass
class DueResult:
    due: date | None
    inferred: bool = False  # derived from a relative expression
    uncertain: bool = False  # ambiguous or unparseable: needs human confirmation
    reason: str = ""


def _upcoming(weekday: int, after: date) -> date:
    delta = (weekday - after.weekday()) % 7
    return after + timedelta(days=delta or 7)


def parse_due(text: str, held_on: date) -> DueResult:
    t = (text or "").strip().lower().rstrip(".")
    if not t:
        return DueResult(None, uncertain=True, reason="No deadline mentioned")
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", t)
    if m:
        try:
            return DueResult(date(int(m[1]), int(m[2]), int(m[3])))
        except ValueError:
            return DueResult(None, uncertain=True, reason=f"Invalid date '{text}'")
    if t == "today" or t == "end of day" or t == "end of the day":
        return DueResult(held_on, inferred=True)
    if t == "tomorrow":
        return DueResult(held_on + timedelta(days=1), inferred=True)
    m = re.fullmatch(r"(?:(this|next)\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)", t)
    if m:
        wd = WEEKDAYS.index(m[2])
        if m[1] == "next":
            monday_next = held_on + timedelta(days=7 - held_on.weekday())
            return DueResult(monday_next + timedelta(days=wd), inferred=True)
        d = _upcoming(wd, held_on)
        same_day = held_on.weekday() == wd
        return DueResult(d, inferred=True, uncertain=same_day, reason="Said on the same weekday; assumed next week" if same_day else "")
    if t in ("end of week", "end of the week", "this week"):
        fri = held_on + timedelta(days=(4 - held_on.weekday()) % 7)
        return DueResult(fri, inferred=True, uncertain=held_on.weekday() > 4, reason="")
    if t == "next week":
        monday_next = held_on + timedelta(days=7 - held_on.weekday())
        return DueResult(monday_next + timedelta(days=4), inferred=True, uncertain=True, reason="'Next week' is vague; set to Friday of next week")
    if t in ("end of month", "end of the month", "this month"):
        last = calendar.monthrange(held_on.year, held_on.month)[1]
        return DueResult(date(held_on.year, held_on.month, last), inferred=True)
    m = re.fullmatch(r"([a-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?", t) or None
    day_first = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]{3,9})", t)
    mon = day = None
    if m:
        mon, day = MONTHS.get(m[1][:3]), int(m[2])
    elif day_first:
        mon, day = MONTHS.get(day_first[2][:3]), int(day_first[1])
    if mon and day:
        try:
            d = date(held_on.year, mon, day)
            if d < held_on - timedelta(days=30):
                d = date(held_on.year + 1, mon, day)
            return DueResult(d, inferred=True)
        except ValueError:
            pass
    return DueResult(None, uncertain=True, reason=f"Could not interpret deadline '{text}'")
