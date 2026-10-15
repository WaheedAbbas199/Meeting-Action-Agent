"""Seed a clearly-labelled DEMO workspace for local evaluation (never runs in production).

Usage: python -m app.seed   ->  demo owner login: demo@example.com / demo-password-123
Demo data is flagged (workspace.is_demo) and the UI shows a "Demo data" badge.
"""

from datetime import date, timedelta

from sqlalchemy import select

from app.config import get_settings
from app.db import Base, get_engine, session_factory
from app.models import Contact, Meeting, Membership, ReminderRule, Task, User, Workspace
from app.security import hash_password
from app.services import jobs, review
from app.services.tasks import set_status

PASSWORD = "demo-password-123"


def run() -> None:
    s = get_settings()
    if s.is_production:
        raise SystemExit("Refusing to seed demo data in production")
    Base.metadata.create_all(get_engine())
    db = session_factory()()
    if db.scalar(select(Workspace).where(Workspace.is_demo.is_(True))):
        print("Demo workspace already exists")
        return
    ws = Workspace(name="Northwind (demo data)", timezone="Asia/Karachi", is_demo=True, settings={"quiet_start": "22:00", "quiet_end": "07:00"})
    db.add(ws)
    db.flush()
    people = [
        ("Demo Owner", "demo@example.com", "owner"),
        ("Maya Khan", "maya@example.com", "manager"),
        ("Alice Ahmed", "alice@example.com", "member"),
        ("Bob Raza", "bob@example.com", "member"),
        ("Vic Viewer", "vic@example.com", "viewer"),
    ]
    users = {}
    for name, email, role in people:
        u = User(email=email, name=name, password_hash=hash_password(PASSWORD))
        db.add(u)
        db.flush()
        db.add(Membership(user_id=u.id, workspace_id=ws.id, role=role, weekly_capacity=8, team="Product"))
        users[name.split()[0]] = u
    db.add_all(
        [
            Contact(workspace_id=ws.id, name="Alice Ahmed", email="alice@example.com", email_authorized=True, user_id=users["Alice"].id),
            Contact(
                workspace_id=ws.id,
                name="Bob Raza",
                email="bob@example.com",
                email_authorized=True,
                phone="+923001112233",
                whatsapp_opt_in=True,
                user_id=users["Bob"].id,
            ),
        ]
    )
    db.add(ReminderRule(workspace_id=ws.id, name="Remind 1 day before due", trigger="before_due", days=1, channel="email"))
    today = date.today()
    d1, d2 = today - timedelta(days=9), today - timedelta(days=2)
    transcripts = [
        (
            f"Product kickoff ({d1})",
            d1,
            f"""[00:00:10] Maya: Thanks everyone. Alice, can you prepare the budget report by {(d1 + timedelta(days=4)).isoformat()}?
[00:00:45] Bob: I will draft the launch plan by {(today + timedelta(days=3)).isoformat()}, blocked on the budget report.
[00:01:20] Maya: We decided to launch the product on {(today + timedelta(days=30)).isoformat()}.
[00:01:40] Alice: I'll book the venue for the launch event by {(today + timedelta(days=6)).isoformat()}.
[00:02:05] Bob: Who owns the vendor contract?""",
        ),
        (
            f"Weekly sync ({d2})",
            d2,
            f"""[00:00:15] Maya: We agreed to hold the weekly sync on Tuesdays.
[00:00:50] Bob: I'll set up the analytics dashboard by {(today + timedelta(days=1)).isoformat()}.
[00:01:30] Alice: I will review the vendor contract by {(today + timedelta(days=2)).isoformat()}.""",
        ),
    ]
    for title, held, text in transcripts:
        m = Meeting(workspace_id=ws.id, title=title, held_on=held, transcript_text=text, created_by=users["Maya"].id, timezone=ws.timezone)
        db.add(m)
        db.flush()
        jobs.enqueue(db, ws.id, "process_meeting", m.id)
        db.commit()
        jobs.run_pending(db)
        for t in db.scalars(select(Task).where(Task.meeting_id == m.id)):
            review.approve_task(db, t, users["Maya"])
        from app.models import Decision

        for d in db.scalars(select(Decision).where(Decision.meeting_id == m.id)):
            review.review_decision(db, d, users["Maya"], True)
        review.refresh_meeting_status(db, m)
        db.commit()
    budget = db.scalar(select(Task).where(Task.title.like("%budget report%")))
    if budget:
        set_status(db, budget, "in_progress", "Demo Owner")
    db.commit()
    print(f"Seeded demo workspace #{ws.id}. Sign in as demo@example.com / {PASSWORD}")


if __name__ == "__main__":
    run()
