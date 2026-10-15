"""FastAPI application factory."""

import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.db import Base, get_engine, session_factory
from app.logging_config import log, setup_logging
from app.providers.base import ProviderError
from app.routers import auth, comms, insights, meetings, planning, tasks, workspace
from app.services import jobs
from app.services.tasks import RuleError

logger = logging.getLogger("maa")

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'"
)


def create_app() -> FastAPI:
    s = get_settings()
    s.validate_for_runtime()
    setup_logging(s.log_json and not s.is_test)
    worker = jobs.Worker()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        engine = get_engine()
        if not s.is_production and s.database_url.startswith("sqlite"):
            Path("data").mkdir(exist_ok=True)
            Base.metadata.create_all(engine)  # dev convenience; production uses `alembic upgrade head`
        db = session_factory()()
        try:
            n = jobs.recover_stale(db)
            db.commit()
            if n:
                log(logger, "recovered stale jobs", count=n)
        finally:
            db.close()
        if s.run_worker and not s.is_test:
            worker.start()
        yield
        worker.stop()

    app = FastAPI(
        title="Meeting Action Agent", version="1.0.0", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None
    )
    if s.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[o.strip() for o in s.cors_origins.split(",") if o.strip()],
            allow_methods=["*"],
            allow_headers=["Authorization", "Content-Type"],
        )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        rid = request.headers.get("x-request-id", uuid.uuid4().hex[:12])
        resp = await call_next(request)
        resp.headers.update({"X-Request-ID": rid, "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer"})
        if request.url.path.startswith("/api/docs") or request.url.path.startswith("/api/openapi"):
            return resp  # Swagger UI needs inline assets
        resp.headers["Content-Security-Policy"] = CSP
        if request.url.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.exception_handler(RuleError)
    async def rule_error(_: Request, exc: RuleError):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(ProviderError)
    async def provider_error(_: Request, exc: ProviderError):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        logger.exception("unhandled error on %s", request.url.path)
        return JSONResponse({"detail": "Something went wrong on our side. Try again."}, status_code=500)

    for r in (auth, workspace, meetings, tasks, planning, comms, insights):
        app.include_router(r.router)

    if s.serve_frontend:
        fdir = Path(s.frontend_dir) if s.frontend_dir else Path(__file__).resolve().parents[2] / "frontend"
        if fdir.is_dir():
            app.mount("/", StaticFiles(directory=fdir, html=True), name="frontend")
    return app


app = create_app()
