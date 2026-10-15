# Deployment

**Status: not verified in a target environment.** The steps below are the intended path.

1. Provision PostgreSQL 16 and set `DATABASE_URL=postgresql+psycopg://user:pass@host:5432/db`.
2. Set `APP_ENV=production` and a strong `JWT_SECRET` (the app refuses to start otherwise). Mock providers are refused in production.
3. Run migrations: `cd backend && alembic upgrade head` (the Docker image does this on start).
4. Start exactly **one** app instance with the worker enabled (`RUN_WORKER=true`), or run a single dedicated worker. Scaling out horizontally needs job row locking first (see ARCHITECTURE).
5. Terminate TLS in front (reverse proxy / load balancer) and forward `X-Forwarded-*`; the container runs uvicorn with `--proxy-headers`. Add HSTS at the proxy.
6. Configure providers (see README) and enable them per workspace in *Settings → Integrations*. For WhatsApp, register `https://<host>/api/webhooks/whatsapp` and set `WHATSAPP_VERIFY_TOKEN` and `WHATSAPP_APP_SECRET`.
7. Back up the database and the `uploads` volume (audio is deleted after transcription; failed uploads can remain).
8. Probes: liveness `GET /api/health`, readiness `GET /api/ready`. Logs are JSON on stdout without secrets.

Before go-live also: run a dependency vulnerability scan (not done here), replace the in-memory login rate limiter with a shared one if you run more than one instance, and add email verification/password reset if you leave sign-up open (`ALLOW_SIGNUP=false` disables public sign-up).
