# Meeting Action Agent

Turns meeting conversations into **verified, trackable execution**: paste or upload a transcript, review evidence-backed decisions and tasks, track commitments and dependencies, spot risks, recall past meetings, and follow up through **human-approved** email and WhatsApp.

> Honest status: everything below was run and tested locally with mocked external providers. Gemini, Gmail, WhatsApp Cloud API and PostgreSQL code paths are implemented but **not verified** against live services. See [docs/STATUS.md](docs/STATUS.md).

## Quick start (local, no credentials needed)

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate      # Python 3.12
pip install -r requirements.txt
python -m app.seed                                       # optional: labelled demo workspace
uvicorn app.main:app --reload                            # http://127.0.0.1:8000
```

Demo login (after seeding): `demo@example.com` / `demo-password-123`. Or just click **Create an account** on the sign-in page.

Defaults: SQLite database in `backend/data/`, rule-based extraction (no AI), email/WhatsApp **disabled**. To try the approval flow without sending anything real, set `EMAIL_PROVIDER=mock` (development only) and enable it in *Settings → Integrations*.

## Run the tests

```bash
cd backend && pip install -r requirements-dev.txt
ruff check . && pytest -q                       # 54 tests: unit, API, security, migrations
cd .. && python -m playwright install chromium   # once
pytest e2e -q                                    # 9 real-browser tests against a live server
```

## Docker (PostgreSQL)

```bash
export POSTGRES_PASSWORD=$(openssl rand -hex 16) JWT_SECRET=$(openssl rand -hex 32)
docker compose up --build        # http://localhost:8000, migrations run on start
```

The Docker and PostgreSQL setup was written but **not built or run** in the environment this was produced in.

## Using real providers

| Capability | Env vars | Notes |
|---|---|---|
| Model extraction + memory answers | `LLM_PROVIDER=gemini`, `GEMINI_API_KEY`, `GEMINI_MODEL` | Model name is configurable; confirm availability for your key |
| Audio transcription | `STT_PROVIDER=gemini` (+ key) | Max 20 MB inline upload |
| Email | `EMAIL_PROVIDER=gmail`, `GMAIL_*` | Gmail API, OAuth refresh token |
| WhatsApp | `WHATSAPP_PROVIDER=cloud`, `WHATSAPP_*` | Official Cloud API; business-initiated messages need an approved template (`WHATSAPP_TEMPLATE_NAME`); webhook at `/api/webhooks/whatsapp` is signature-validated |

Copy `.env.example` to `.env`. Never commit secrets. Real sends are blocked when `APP_ENV=test`.

## What is where

```
backend/app/          FastAPI app: routers/, services/ (rules), providers/ (LLM, STT, email, WhatsApp), graph/ (LangGraph pipeline), models.py
backend/alembic/      Database migrations
backend/tests/        Unit, API, security, migration tests
frontend/             Vanilla JS (ES modules) + CSS design system, served by FastAPI
e2e/                  Playwright browser tests
docs/                 ARCHITECTURE, API, DESIGN_SYSTEM, DEPLOYMENT, TROUBLESHOOTING, STATUS
```

## Safety model in one paragraph

AI output is *candidates only*: every item must quote the transcript verbatim (otherwise it is discarded), and nothing becomes a task or decision until a manager approves it. Transcripts are untrusted data; embedded instructions are flagged and never executed. External messages need a consented recipient, an enabled provider, a manager's approval that has not expired, and are re-validated immediately before sending (task still open, approver still a manager, quiet hours, hourly rate limit). All data access is scoped by workspace; other tenants' records return 404/403.
