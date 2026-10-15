"""Auth, RBAC, planner, workload, analytics, quiet hours, reminders, calendar, settings."""

from datetime import date, timedelta

from sqlalchemy import select

from app.models import Task, Workspace
from app.providers.messaging import MOCKS
from tests.conftest import process_all
from tests.test_api_flows import _setup_overdue, approve_all, mk_meeting


def test_auth_register_login_and_bad_credentials(client):
    r = client.post(
        "/api/auth/register", json={"email": "new@example.com", "name": "New", "password": "a-long-password-1", "workspace_name": "NewCo"}
    )
    assert r.status_code == 201 and r.json()["workspaces"][0]["role"] == "owner"
    assert (
        client.post(
            "/api/auth/register", json={"email": "new@example.com", "name": "N", "password": "a-long-password-1", "workspace_name": "X"}
        ).status_code
        == 409
    )
    assert (
        client.post("/api/auth/register", json={"email": "x@example.com", "name": "N", "password": "short", "workspace_name": "X"}).status_code == 422
    )
    assert client.post("/api/auth/login", json={"email": "new@example.com", "password": "wrong"}).status_code == 401
    tok = client.post("/api/auth/login", json={"email": "NEW@example.com", "password": "a-long-password-1"}).json()["token"]
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"}).json()["user"]["email"] == "new@example.com"
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_login_rate_limited(client):
    codes = [client.post("/api/auth/login", json={"email": "a@example.com", "password": "x"}).status_code for _ in range(12)]
    assert codes[:10] == [401] * 10 and 429 in codes[10:]


def test_role_enforcement(env):
    base = f"/api/w/{env.acme}"
    assert env.client.post(f"{base}/tasks", headers=env.h["vic"], json={"title": "nope"}).status_code == 403  # viewer
    assert (
        env.client.post(f"{base}/meetings", headers=env.h["vic"], json={"title": "t", "transcript_text": "Alice: hello there friends"}).status_code
        == 403
    )
    assert env.client.patch(f"{base}/workspace", headers=env.h["maya"], json={"name": "X"}).status_code == 403
    assert env.client.get(f"{base}/audit", headers=env.h["alice"]).status_code == 403
    assert env.client.get(f"{base}/audit", headers=env.h["adam"]).status_code == 200
    # member editing someone else's task is refused; manager may
    t = env.client.post(f"{base}/tasks", headers=env.h["maya"], json={"title": "Maya's thing", "owner_name": "Maya"}).json()
    assert env.client.patch(f"{base}/tasks/{t['id']}", headers=env.h["alice"], json={"title": "hijack"}).status_code == 403
    assert env.client.patch(f"{base}/tasks/{t['id']}", headers=env.h["maya"], json={"title": "renamed"}).json()["title"] == "renamed"


def test_member_management_rules(env):
    base = f"/api/w/{env.acme}"
    r = env.client.post(
        f"{base}/members",
        headers=env.h["adam"],
        json={"email": "kim@example.com", "name": "Kim", "role": "member", "initial_password": "long-enough-pass"},
    )
    assert r.status_code == 201
    assert (
        env.client.post(
            f"{base}/members",
            headers=env.h["adam"],
            json={"email": "boss@example.com", "name": "B", "role": "owner", "initial_password": "long-enough-pass"},
        ).status_code
        == 403
    )
    uid = env.client.get(f"{base}/members", headers=env.h["adam"]).json()[0]["user_id"]  # olivia, the only owner
    assert env.client.patch(f"{base}/members/{uid}", headers=env.h["adam"], json={"role": "member"}).status_code == 403
    assert env.client.patch(f"{base}/members/{uid}", headers=env.h["olivia"], json={"role": "member"}).status_code == 409  # last owner


def test_reassign_requires_manager_and_logs_history(env):
    base = f"/api/w/{env.acme}"
    t = env.client.post(f"{base}/tasks", headers=env.h["maya"], json={"title": "Do thing", "owner_name": "Alice"}).json()
    members = {m["name"]: m["user_id"] for m in env.client.get(f"{base}/members", headers=env.h["maya"]).json()}
    assert (
        env.client.post(f"{base}/workload/apply", headers=env.h["alice"], json={"task_id": t["id"], "to_user_id": members["Maya"]}).status_code == 403
    )
    assert (
        env.client.post(f"{base}/workload/apply", headers=env.h["maya"], json={"task_id": t["id"], "to_user_id": members["Maya"]}).json()[
            "owner_name"
        ]
        == "Maya"
    )
    ev = env.client.get(f"{base}/tasks/{t['id']}", headers=env.h["maya"]).json()["events"]
    assert any(e["field"] == "owner_name" and e["old"] == "Alice" for e in ev)


def test_deadline_changes_tracked_and_slip_risk(env):
    base = f"/api/w/{env.acme}"
    soon = (date.today() + timedelta(days=5)).isoformat()
    t = env.client.post(f"{base}/tasks", headers=env.h["maya"], json={"title": "Ship it", "owner_name": "Maya", "due_date": soon}).json()
    for d in (1, 2, 3):
        env.client.patch(f"{base}/tasks/{t['id']}", headers=env.h["maya"], json={"due_date": (date.today() + timedelta(days=5 + d)).isoformat()})
    got = env.client.get(f"{base}/tasks/{t['id']}", headers=env.h["maya"]).json()
    assert got["deadline_changes"] == 3 and got["original_due_date"] == soon
    kinds = [r["kind"] for r in env.client.get(f"{base}/risks", headers=env.h["maya"]).json()["items"]]
    assert "deadline_slipped" in kinds
    assert env.client.get(f"{base}/analytics", headers=env.h["maya"]).json()["deadline_changes"] == {"total": 3, "tasks_affected": 1}


def test_workload_overload_and_suggestion(env):
    base = f"/api/w/{env.acme}"
    for i in range(3):
        env.client.post(f"{base}/tasks", headers=env.h["maya"], json={"title": f"Heavy {i}", "owner_name": "Alice", "priority": "high"})
    w = env.client.get(f"{base}/workload", headers=env.h["maya"]).json()
    alice = next(m for m in w["members"] if m["name"] == "Alice")
    assert alice["points"] == 9 and alice["overloaded"]
    assert w["suggestions"] and w["suggestions"][0]["from_name"] == "Alice" and "capacity" in w["suggestions"][0]["reason"]
    assert "not a performance score" in w["note"]


def test_planner_agenda_edit_revisions_approve_and_calendar(env):
    base = f"/api/w/{env.acme}"
    env.client.post(f"{base}/tasks", headers=env.h["maya"], json={"title": "Late task", "owner_name": "Alice", "due_date": "2020-01-01"})
    ag = env.client.post(f"{base}/agendas", headers=env.h["alice"], json={"title": "Sync"}).json()
    assert ag["items"][0]["kind"] == "overdue" and "Overdue by" not in ag["items"][0]["reason"] and "day(s) ago" in ag["items"][0]["reason"]
    edited = env.client.put(
        f"{base}/agendas/{ag['id']}",
        headers=env.h["alice"],
        json={"title": "Sync v2", "items": [*ag["items"], {"title": "Custom topic", "minutes": 10}]},
    ).json()
    assert edited["revision"] == 2 and len(edited["items"]) == 2
    assert env.client.put(f"{base}/agendas/{ag['id']}", headers=env.h["alice"], json={"title": "x", "items": [{"title": " "}]}).status_code == 422
    assert (
        env.client.post(f"{base}/agendas/{ag['id']}/calendar", headers=env.h["alice"], json={"start": "2026-11-02T10:00:00Z"}).status_code == 409
    )  # not approved
    assert env.client.post(f"{base}/agendas/{ag['id']}/approve", headers=env.h["alice"]).status_code == 403
    assert env.client.post(f"{base}/agendas/{ag['id']}/approve", headers=env.h["maya"]).json()["status"] == "approved"
    p = env.client.post(f"{base}/agendas/{ag['id']}/calendar", headers=env.h["alice"], json={"start": "2026-11-02T10:00:00Z"}).json()
    assert MOCKS["calendar"].sent == []  # needs approval first
    env.client.post(f"{base}/approvals/{p['approval_id']}/decide", headers=env.h["maya"], json={"approve": True})
    process_all(env.db)
    assert len(MOCKS["calendar"].sent) == 1
    detail = env.client.get(f"{base}/agendas/{ag['id']}", headers=env.h["alice"]).json()
    assert [r["revision"] for r in detail["revisions"]] == [2, 1]


def test_quiet_hours_defer_sending(env):
    t, cid = _setup_overdue(env)
    ws = env.db.get(Workspace, env.acme)
    ws.settings = {"quiet_start": "00:00", "quiet_end": "23:59"}
    env.db.commit()
    fid = env.client.post(
        f"/api/w/{env.acme}/followups", headers=env.h["alice"], json={"task_id": t.id, "contact_id": cid, "channel": "email"}
    ).json()["id"]
    ap = env.client.post(f"/api/w/{env.acme}/followups/{fid}/submit", headers=env.h["alice"]).json()
    env.client.post(f"/api/w/{env.acme}/approvals/{ap['id']}/decide", headers=env.h["maya"], json={"approve": True})
    stats = process_all(env.db)
    assert stats["deferred"] == 1 and MOCKS["email"].sent == []
    ws = env.db.get(Workspace, env.acme)
    ws.settings = {}
    env.db.commit()
    from datetime import datetime

    from app.services import jobs

    assert jobs.run_pending(env.db, now=datetime.utcnow() + timedelta(days=2))["succeeded"] == 1


def test_hourly_send_limit_defers(env, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "sends_per_hour", 1)
    t, cid = _setup_overdue(env)
    for ch in ("email", "whatsapp"):
        fid = env.client.post(
            f"/api/w/{env.acme}/followups", headers=env.h["alice"], json={"task_id": t.id, "contact_id": cid, "channel": ch}
        ).json()["id"]
        ap = env.client.post(f"/api/w/{env.acme}/followups/{fid}/submit", headers=env.h["alice"]).json()
        env.client.post(f"/api/w/{env.acme}/approvals/{ap['id']}/decide", headers=env.h["maya"], json={"approve": True})
    stats = process_all(env.db)
    assert stats["succeeded"] == 1 and stats["deferred"] == 1


def test_reminder_rules_create_drafts_only(env):
    base = f"/api/w/{env.acme}"
    env.client.post(f"{base}/contacts", headers=env.h["maya"], json={"name": "Alice", "email": "alice@example.com", "email_authorized": True})
    env.client.post(
        f"{base}/tasks",
        headers=env.h["maya"],
        json={"title": "Due tomorrow", "owner_name": "Alice", "due_date": (date.today() + timedelta(days=1)).isoformat()},
    )
    env.client.post(
        f"{base}/tasks",
        headers=env.h["maya"],
        json={"title": "Nobody", "owner_name": "Ghost", "due_date": (date.today() + timedelta(days=1)).isoformat()},
    )
    assert (
        env.client.post(f"{base}/reminder-rules", headers=env.h["alice"], json={"name": "x", "trigger": "before_due", "days": 1}).status_code == 403
    )
    env.client.post(
        f"{base}/reminder-rules", headers=env.h["maya"], json={"name": "1 day before", "trigger": "before_due", "days": 1, "channel": "email"}
    )
    r = env.client.post(f"{base}/followups/run-reminders", headers=env.h["maya"]).json()
    assert r["drafts_created"] == 1 and len(r["skipped"]) == 1
    assert env.client.post(f"{base}/followups/run-reminders", headers=env.h["maya"]).json()["drafts_created"] == 0  # idempotent
    assert env.client.get(f"{base}/followups", headers=env.h["maya"]).json()[0]["status"] == "draft"
    assert MOCKS["email"].sent == []


def test_corrections_and_ai_quality_metrics(env):
    mid = mk_meeting(env)
    d = env.client.get(f"/api/w/{env.acme}/meetings/{mid}", headers=env.h["maya"]).json()
    t = next(x for x in d["tasks"] if x["title"] == "draft the launch plan")
    env.client.patch(f"/api/w/{env.acme}/tasks/{t['id']}", headers=env.h["maya"], json={"title": "Draft the launch plan v1"})
    approve_all(env, mid)
    a = env.client.get(f"/api/w/{env.acme}/analytics", headers=env.h["maya"]).json()
    assert a["ai_quality"]["corrected"] == 1 and a["ai_quality"]["approved"] == 2 and a["ai_quality"]["correction_rate"] == 0.5
    assert a["trends"]["sufficient"] is False and a["completion_rate"] == 0.0
    assert a["meeting_effectiveness"][0]["tasks"] == 2


def test_analytics_on_time_rate_and_definitions(env):
    base = f"/api/w/{env.acme}"
    ok = env.client.post(
        f"{base}/tasks", headers=env.h["maya"], json={"title": "A", "owner_name": "Maya", "due_date": (date.today() + timedelta(days=3)).isoformat()}
    ).json()
    late = env.client.post(f"{base}/tasks", headers=env.h["maya"], json={"title": "B", "owner_name": "Maya", "due_date": "2020-01-01"}).json()
    for t in (ok, late):
        env.client.post(f"{base}/tasks/{t['id']}/status", headers=env.h["maya"], json={"status": "done"})
    a = env.client.get(f"{base}/dashboard", headers=env.h["maya"]).json()
    assert a["on_time_completion_rate"] == 0.5 and a["completion_rate"] == 1.0 and "open_tasks" in a["definitions"]
    empty = env.client.get(f"/api/w/{env.globex}/dashboard", headers=env.hg).json()
    assert empty["completion_rate"] is None and empty["open_tasks"] == 0


def test_settings_validation_and_integration_safety(env):
    base = f"/api/w/{env.acme}"
    assert env.client.patch(f"{base}/workspace", headers=env.h["adam"], json={"timezone": "Mars/Base"}).status_code == 422
    assert env.client.patch(f"{base}/workspace", headers=env.h["adam"], json={"quiet_start": "25:00"}).status_code == 422
    ok = env.client.patch(f"{base}/workspace", headers=env.h["adam"], json={"timezone": "Asia/Karachi", "quiet_start": "22:00", "quiet_end": "07:00"})
    assert ok.json()["timezone"] == "Asia/Karachi"
    ints = env.client.get(f"{base}/integrations", headers=env.h["adam"]).json()
    assert {i["kind"] for i in ints} == {"email", "whatsapp", "calendar", "ai", "stt"}
    assert "whsec" not in str(ints) and "verify-me" not in str(ints)  # configured secrets never appear in API output
    assert env.client.put(f"{base}/integrations/email", headers=env.h["maya"], json={"enabled": False}).status_code == 403


def test_security_headers_and_error_hygiene(env):
    r = env.client.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff" and "default-src 'self'" in r.headers["content-security-policy"]
    assert env.client.get(f"/api/w/{env.acme}/tasks/99999", headers=env.h["maya"]).json()["detail"] == "Task not found"


def test_upload_limits(env, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "max_upload_bytes", 50)
    big = env.client.post(
        f"/api/w/{env.acme}/meetings/upload", headers=env.h["alice"], data={"title": "x"}, files={"file": ("a.txt", b"x" * 100, "text/plain")}
    )
    assert big.status_code == 413
    empty = env.client.post(
        f"/api/w/{env.acme}/meetings/upload", headers=env.h["alice"], data={"title": "x"}, files={"file": ("a.txt", b"", "text/plain")}
    )
    assert empty.status_code == 422
    assert env.db.scalar(select(Task.id)) is None
