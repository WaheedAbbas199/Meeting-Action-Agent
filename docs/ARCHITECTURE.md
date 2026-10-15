# Architecture

```
Browser (vanilla JS SPA, hash router)
   │  JSON over HTTPS, Bearer JWT
FastAPI ── routers ──► services (deterministic rules) ──► SQLAlchemy ──► SQLite (dev/tests) | PostgreSQL (prod)
   │                         ▲
   │                         └── providers: LLM (heuristic | Gemini), STT, Email (Gmail), WhatsApp (Cloud API), Calendar (mock only)
   └── DB-backed job queue ──► worker thread ──► LangGraph pipeline / guarded send
```

## Principle: AI proposes, deterministic code decides
- **AI/LLM**: language understanding only (extraction, answers). Output is schema-validated (`parse_extraction_json`), evidence-verified (`locate_quote`) and goes to human review.
- **Deterministic**: permissions, deadlines (`services/dates.py`), dependencies and blocking (`services/tasks.py`), risks (`services/risk.py`), metrics (`services/analytics.py`), approvals and execution state (`services/followups.py`).

## Meeting pipeline (LangGraph, `graph/workflow.py`)
`load → (transcribe) → parse → extract → verify → persist`. Each node writes a timestamped stage to `meeting.stage_log`, which the UI shows; there are no invented progress percentages. Persistence is one transaction and a re-run is a no-op for meetings already in review, so retries cannot duplicate tasks.

## Data model (workspace-scoped)
Users/Memberships(role) → Workspace → Meetings → Segments(embedding) → Tasks (+Dependencies, Events) / Decisions (+conflict fields) / Agendas(+Revisions) / Contacts / FollowUps / Approvals / Jobs / ReminderRules / Notifications / AuditLog / Corrections / IntegrationConfig. Every tenant row has `workspace_id`; `deps.get_owned` returns 404 for rows of other workspaces.

## Roles
viewer < member < manager < admin < owner. Members create/edit (own or unassigned tasks); managers approve extraction, messages, reassignments and conflict resolutions; admins manage settings/people/integrations.

## Reliability
- Jobs: `queued → running → succeeded|dead`; stale `running` jobs are recovered on start and every tick; transient provider errors retry with exponential backoff up to `JOB_MAX_ATTEMPTS`; permanent errors fail fast and mark the entity failed.
- Sends: provider idempotency key + local status checks; a message already `sent` is never re-sent. Quiet hours and the hourly limit defer (without consuming attempts).
- Limitation: run **one** worker process. Multi-worker needs row locking (`FOR UPDATE SKIP LOCKED` on PostgreSQL), which is not implemented.

## Security controls
bcrypt passwords, JWT (8h), login rate limit, strict CSP (no inline script/style), `nosniff`, `X-Frame-Options`, request-size limits on uploads, safe error messages, audit log, secrets only from environment, webhook HMAC validation with constant-time compare, mock providers refused in production.
