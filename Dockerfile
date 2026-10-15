# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

FROM base AS deps
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --prefix=/install -r backend/requirements.txt

FROM base AS runtime
RUN useradd --create-home --uid 10001 maa && mkdir -p /app/data/uploads && chown -R maa /app
COPY --from=deps /install /usr/local
COPY --chown=maa backend backend
COPY --chown=maa frontend frontend
USER maa
WORKDIR /app/backend
ENV APP_ENV=production FRONTEND_DIR=/app/frontend UPLOAD_DIR=/app/data/uploads
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/ready',timeout=3).status==200 else 1)"
# Migrations run before the server starts; a failed migration stops the container.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
