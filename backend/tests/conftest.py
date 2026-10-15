import os

os.environ.update(
    {
        "APP_ENV": "test",
        "DATABASE_URL": "sqlite://",
        "RUN_WORKER": "false",
        "SERVE_FRONTEND": "false",
        "JWT_SECRET": "test-secret-test-secret-test-secret-123456",
        "EMAIL_PROVIDER": "mock",
        "WHATSAPP_PROVIDER": "mock",
        "CALENDAR_PROVIDER": "mock",
        "STT_PROVIDER": "fake",
        "WHATSAPP_APP_SECRET": "whsec",
        "WHATSAPP_VERIFY_TOKEN": "verify-me",
        "UPLOAD_DIR": "/tmp/maa-test-uploads",
    }
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()
from app import db as dbmod  # noqa: E402
from app.db import Base  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import IntegrationConfig, Membership, User, Workspace  # noqa: E402
from app.providers.messaging import MOCKS  # noqa: E402
from app.security import hash_password, login_limiter  # noqa: E402


@pytest.fixture()
def app():
    engine = dbmod.init_engine("sqlite://")
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    for m in MOCKS.values():
        m.reset()
    login_limiter.reset()
    return create_app()


@pytest.fixture()
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def db():
    s = dbmod.session_factory()()
    yield s
    s.close()


class Env:
    """Helper holding two isolated organizations with users of each role."""

    def __init__(self, client, db):
        self.client, self.db = client, db
        self.pw = "correct-horse-battery"

    def make_workspace(self, name, users: dict[str, str]) -> int:
        ws = Workspace(name=name, timezone="UTC", settings={})
        self.db.add(ws)
        self.db.flush()
        for uname, role in users.items():
            email = f"{uname}@{name.lower().replace(' ', '')}.test"
            u = self.db.query(User).filter_by(email=email).first() or User(email=email, name=uname.title(), password_hash=hash_password(self.pw))
            self.db.add(u)
            self.db.flush()
            self.db.add(Membership(user_id=u.id, workspace_id=ws.id, role=role, weekly_capacity=6))
        for kind in ("email", "whatsapp", "calendar"):
            self.db.add(IntegrationConfig(workspace_id=ws.id, kind=kind, enabled=True))
        self.db.commit()
        return ws.id

    def login(self, uname, org) -> dict:
        r = self.client.post("/api/auth/login", json={"email": f"{uname}@{org.lower().replace(' ', '')}.test", "password": self.pw})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture()
def env(client, db):
    e = Env(client, db)
    e.acme = e.make_workspace("Acme", {"olivia": "owner", "maya": "manager", "alice": "member", "vic": "viewer", "adam": "admin"})
    e.globex = e.make_workspace("Globex", {"greg": "owner"})
    e.h = {n: e.login(n, "Acme") for n in ("olivia", "maya", "alice", "vic", "adam")}
    e.hg = e.login("greg", "Globex")
    return e


def process_all(db):
    from app.services import jobs

    return jobs.run_pending(db)


TRANSCRIPT = """[00:00:05] Maya: Let's start. Alice, can you prepare the budget report by Friday?
[00:00:20] Alice: Yes.
[00:00:40] Bob: I will draft the launch plan by next Monday, blocked on the budget report.
[00:01:00] Maya: We decided to launch on 2026-11-01.
[00:01:10] Maya: Who owns the vendor contract?
"""
