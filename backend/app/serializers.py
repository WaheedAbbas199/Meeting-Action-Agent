"""Plain-dict serializers (explicit field control; no accidental leakage of internal columns)."""

from datetime import date, datetime


def iso(v):
    if isinstance(v, datetime):
        return v.isoformat() + "Z"
    if isinstance(v, date):
        return v.isoformat()
    return v


def task_out(t, today: date | None = None) -> dict:
    today = today or date.today()
    due = t.due_date
    return {
        "id": t.id,
        "title": t.title,
        "description": t.description,
        "owner_name": t.owner_name,
        "owner_user_id": t.owner_user_id,
        "priority": t.priority,
        "status": t.status,
        "review_state": t.review_state,
        "due_date": iso(due),
        "due_inferred": t.due_inferred,
        "original_due_date": iso(t.original_due_date),
        "deadline_changes": t.deadline_changes,
        "blocker_reason": t.blocker_reason,
        "auto_blocked": t.auto_blocked,
        "evidence_quote": t.evidence_quote,
        "segment_idx": t.segment_idx,
        "meeting_id": t.meeting_id,
        "confidence": t.confidence,
        "uncertain_fields": t.uncertain_fields or [],
        "created_at": iso(t.created_at),
        "completed_at": iso(t.completed_at),
        "overdue": bool(due and due < today and t.status in ("open", "in_progress", "blocked")),
        "days_until_due": (due - today).days if due else None,
    }


def decision_out(d) -> dict:
    return {
        "id": d.id,
        "kind": d.kind,
        "text": d.text,
        "topic": d.topic,
        "status": d.status,
        "review_state": d.review_state,
        "evidence_quote": d.evidence_quote,
        "segment_idx": d.segment_idx,
        "confidence": d.confidence,
        "meeting_id": d.meeting_id,
        "conflicts_with_id": d.conflicts_with_id,
        "conflict_reason": d.conflict_reason,
        "conflict_state": d.conflict_state,
        "created_at": iso(d.created_at),
    }


def meeting_out(m) -> dict:
    return {
        "id": m.id,
        "title": m.title,
        "timezone": m.timezone,
        "held_on": iso(m.held_on),
        "source_type": m.source_type,
        "filename": m.filename,
        "status": m.status,
        "stage_log": m.stage_log or [],
        "error": m.error,
        "summary": m.summary,
        "warnings": m.warnings or [],
        "created_at": iso(m.created_at),
    }


def followup_out(f, contact=None, task=None) -> dict:
    return {
        "id": f.id,
        "task_id": f.task_id,
        "task_title": task.title if task else "",
        "contact_id": f.contact_id,
        "recipient": contact.name if contact else "",
        "channel": f.channel,
        "subject": f.subject,
        "body": f.body,
        "status": f.status,
        "attempts": f.attempts,
        "last_error": f.last_error,
        "provider_message_id": f.provider_message_id,
        "delivery_status": f.delivery_status,
        "created_at": iso(f.created_at),
        "sent_at": iso(f.sent_at),
    }


def approval_out(a, names: dict | None = None) -> dict:
    names = names or {}
    return {
        "id": a.id,
        "kind": a.kind,
        "ref_id": a.ref_id,
        "payload": a.payload,
        "status": a.status,
        "requested_by": names.get(a.requested_by, ""),
        "decided_by": names.get(a.decided_by, ""),
        "decided_at": iso(a.decided_at),
        "decision_note": a.decision_note,
        "expires_at": iso(a.expires_at),
        "created_at": iso(a.created_at),
    }


def contact_out(c) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "email": c.email,
        "phone": c.phone,
        "email_authorized": c.email_authorized,
        "whatsapp_opt_in": c.whatsapp_opt_in,
        "user_id": c.user_id,
    }
