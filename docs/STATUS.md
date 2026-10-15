# Feature status and verification report

Legend: ✅ implemented and tested locally · 🧪 implemented, only mocked/fake provider verified · ⛔ not implemented

## The 20 backend features
| # | Feature | Status | Notes |
|---|---|---|---|
| 1 | Meeting ingestion + STT | ✅ text/VTT/SRT; 🧪 audio | Audio path tested with a fake STT; `GeminiSTT` unverified |
| 2 | Evidence-based extraction | ✅ rule-based; 🧪 Gemini | Evidence verification and schema validation are deterministic and tested; Gemini client unverified |
| 3 | Commitment tracker | ✅ | Owner/deadline/uncertainty flags, original deadline, change counts |
| 4 | Task management | ✅ | List/board, filters, search, pagination, role rules |
| 5 | Dependency engine | ✅ | Cycle detection, auto-blocking, re-evaluation on completion/reopen |
| 6 | Risk & blocker detection | ✅ | Rule-based; every risk names its rule; no predictions |
| 7 | Decision conflict detector | ✅ heuristic | Value/negation differences; always needs human confirmation |
| 8 | Next-meeting planner | ✅ | Reasoned items, editing, revisions, approval |
| 9 | Workload balancer | ✅ | Weighted points vs. capacity; manager-approved reassignment |
| 10 | Meeting memory (RAG) | ✅ lexical | Hashed lexical embeddings, not semantic; citations; tenant-filtered |
| 11 | Commitment change history | ✅ | Per-task event log |
| 12 | Multi-step follow-up agent | ✅ deterministic | Reminder rules → drafts → approval → guarded send. Not LLM-driven |
| 13 | Email follow-up | ✅ mock; 🧪 Gmail | Gmail API client unverified |
| 14 | WhatsApp follow-up | ✅ mock; 🧪 Cloud API | Client and webhook signature validation; live API unverified |
| 15 | Human approval system | ✅ | Pending/approved/rejected/expired/revoked/executed/failed, revalidation |
| 16 | Background job recovery | ✅ | Stale-job recovery, bounded retries, deferral |
| 17 | Multi-team workspaces + roles | ✅ | Tenant isolation tested |
| 18 | Effectiveness analytics | ✅ | Definitions returned by the API |
| 19 | Confidence + correction capture | ✅ | Corrections recorded; metrics shown. Not used to retrain anything |
| 20 | Google Calendar (optional) | 🧪 mock / ⛔ real | Approval-gated flow with a mock provider; **no real Google Calendar provider** |

## Verification actually performed (Oct 2026, this repository)
- `ruff check .` — clean.
- `pytest` (backend) — **54 passed**: unit rules, API workflows A–H, RBAC, tenant isolation, approvals/expiry/revocation, retries/recovery, quiet hours, rate limit, webhooks, migrations (`alembic upgrade`, `alembic check`, `downgrade`), seed.
- `pytest e2e` (Playwright, Chromium 141, real server, mock providers) — **9 passed**: register → paste meeting → review → approve → tasks/dashboard; all 12 pages load with no console errors or 5xx; dependency blocking via keyboard Kanban; focus/Escape/discard-changes behaviour; mobile nav, theme persistence, reduced motion; decision conflict; memory citations; full follow-up approval → worker send; read-only viewer.
- axe-core (WCAG 2.x A/AA) over 16 routes × light/dark — 0 violations after fixes (automated only).
- Visual check of screenshots (light, dark, mobile).

## Not verified / known limitations
- PostgreSQL, Docker build/run, GitHub Actions: written, not executed here.
- Gemini, Gmail, WhatsApp Cloud API: never called with real credentials.
- Drag-and-drop on the board is implemented but only the keyboard “Move to” path is covered by tests.
- No dependency vulnerability scan; no load testing; no manual screen-reader test.
- Single worker only; in-memory login rate limiter (per process).
- No email verification, password reset or SSO; sign-up can be disabled with `ALLOW_SIGNUP=false`.
- Per-person notification channel preferences are not implemented (in-app notifications only; quiet hours are per workspace).
- Duplicate-task detection across meetings is not implemented; owner matching is by name.
- Rule-based extraction is far weaker than a real model; expect to edit items.
- Auth token is kept in `sessionStorage` (XSS-exposed in principle); the strict CSP mitigates but does not eliminate this trade-off versus httpOnly cookies.
