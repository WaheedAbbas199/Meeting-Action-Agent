import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def _alembic(db_url: str, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "DATABASE_URL": db_url, "APP_ENV": "development"}
    return subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND, env=env, capture_output=True, text=True)


def test_migrations_upgrade_match_models_and_downgrade(tmp_path):
    url = f"sqlite:///{tmp_path}/m.db"
    up = _alembic(url, "upgrade", "head")
    assert up.returncode == 0, up.stderr
    chk = _alembic(url, "check")
    assert chk.returncode == 0, chk.stdout + chk.stderr  # models and migrations are in sync
    down = _alembic(url, "downgrade", "base")
    assert down.returncode == 0, down.stderr


def test_seed_creates_flagged_demo_data(tmp_path):
    url = f"sqlite:///{tmp_path}/s.db"
    env = {**os.environ, "DATABASE_URL": url, "APP_ENV": "development", "LLM_PROVIDER": "heuristic"}
    r = subprocess.run([sys.executable, "-m", "app.seed"], cwd=BACKEND, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-800:]
    assert "Seeded demo workspace" in r.stdout
    prod = subprocess.run(
        [sys.executable, "-m", "app.seed"], cwd=BACKEND, env={**env, "APP_ENV": "production", "JWT_SECRET": "x" * 40}, capture_output=True, text=True
    )
    assert prod.returncode != 0
