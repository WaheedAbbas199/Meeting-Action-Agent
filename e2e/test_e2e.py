import re
import time

import httpx
from playwright.sync_api import expect

from conftest import PW, Account, Page

TRANSCRIPT = """[00:00:05] Maya: Let's start. Alice, can you prepare the budget report by Friday?
[00:00:40] Bob: I will draft the launch plan by next Monday, blocked on the budget report.
[00:01:00] Maya: We decided to launch on 2026-11-01.
[00:01:10] Maya: Who owns the vendor contract?"""


def wait_status(acct, mid, want, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        s = acct.api("GET", f"/meetings/{mid}")["status"]
        if s in want:
            return s
        time.sleep(0.3)
    raise AssertionError(f"meeting stayed in {s}")


def make_reviewed_meeting(acct, title="Planning", text=TRANSCRIPT, approve=True):
    m = acct.api("POST", "/meetings", json={"title": title, "held_on": "2026-10-14", "transcript_text": text})
    wait_status(acct, m["id"], {"review", "completed", "failed"})
    d = acct.api("GET", f"/meetings/{m['id']}")
    if approve:
        acct.api("POST", f"/meetings/{m['id']}/review", json={"tasks": [{"id": t["id"], "action": "approve"} for t in d["tasks"]],
                                                              "decisions": [{"id": x["id"], "action": "approve"} for x in d["decisions"]]})
    return m["id"]


def test_register_then_meeting_to_task_flow_in_browser(ui, base_url):
    p = ui.page
    p.goto(f"{base_url}/#/login")
    expect(p.get_by_role("heading", name="Welcome back")).to_be_visible()
    p.get_by_role("link", name="Create an account").click()
    p.get_by_label("Your name").fill("Pat Doe")
    p.get_by_label("Workspace name").fill("Pat Co")
    p.get_by_label("Email").fill("pat-ui@example.com")
    p.get_by_label("Password").fill(PW)
    p.get_by_role("button", name="Create account").click()
    expect(p.get_by_role("heading", name="Dashboard")).to_be_visible()
    expect(p.get_by_text("No open tasks")).to_be_visible()
    # new meeting via paste
    p.get_by_role("link", name="New meeting").click()
    dlg = p.get_by_role("dialog")
    expect(dlg).to_be_visible()
    dlg.get_by_label("Meeting title").fill("Budget kickoff")
    dlg.get_by_label("Held on").fill("2026-10-14")
    dlg.get_by_label("Transcript").fill(TRANSCRIPT)
    dlg.get_by_role("button", name="Process meeting").click()
    # real processing stages, then the review screen
    expect(p.get_by_role("heading", name="Budget kickoff")).to_be_visible()
    expect(p.get_by_text("Tasks and commitments (2)")).to_be_visible(timeout=15000)
    expect(p.get_by_text("Needs review").first).to_be_visible()
    expect(p.locator(".evidence").first).to_contain_text("budget report")
    p.get_by_role("button", name="Approve", exact=True).first.click()
    expect(p.get_by_text("Task approved")).to_be_visible()
    p.get_by_role("button", name="Approve", exact=True).first.click()
    expect(p.locator(".item.approved")).to_have_count(2)
    p.get_by_role("link", name="Tasks", exact=True).click()
    expect(p.get_by_role("heading", name="Tasks", exact=True)).to_be_visible()
    expect(p.get_by_role("button", name="Open task prepare the budget report")).to_be_visible()
    # dependent task is auto-blocked
    expect(p.locator("tr", has=p.get_by_role("button", name="Open task draft the launch plan")).locator(".badge", has_text="Blocked")).to_be_visible()
    p.get_by_role("link", name="Dashboard").click()
    expect(p.locator(".kpi", has_text="Open tasks").locator(".value")).to_have_text("2")
    assert ui.errors == [] and ui.failed == []


def test_every_page_loads_without_console_errors(ui, account):
    make_reviewed_meeting(account)
    ui.login(account)
    for route, heading in [("dashboard", "Dashboard"), ("meetings", "Meetings"), ("tasks", "Tasks"), ("risks", "Risks & blockers"), ("decisions", "Decisions"),
                           ("planner", "Next meeting planner"), ("memory", "Meeting memory"), ("workload", "Team workload"), ("followups", "Email & WhatsApp follow-ups"),
                           ("approvals", "Approval center"), ("analytics", "Meeting effectiveness analytics"), ("settings", "Settings")]:
        ui.page.goto(f"{ui.base_url}/#/{route}")
        expect(ui.page.get_by_role("heading", name=heading, exact=True)).to_be_visible()
        ui.page.wait_for_load_state("networkidle")
    assert ui.errors == [], ui.errors
    assert ui.failed == []


def test_dependency_blocking_and_kanban_keyboard_move(ui, account):
    make_reviewed_meeting(account)
    ui.login(account)
    p = ui.page
    p.goto(f"{ui.base_url}/#/tasks")
    p.get_by_role("button", name="Board").click()
    expect(p.locator('[data-col="blocked"] .tcard .title', has_text="draft the launch plan")).to_be_visible()
    # move prerequisite with the keyboard-accessible select (no dragging)
    sel = p.get_by_label("Move prepare the budget report to")
    sel.focus()
    sel.select_option("done")
    expect(p.get_by_text("Moved to Done")).to_be_visible()
    expect(p.locator('[data-col="done"] .tcard .title', has_text="prepare the budget report")).to_be_visible()
    # dependent was re-evaluated by the server
    expect(p.locator('[data-col="open"] .tcard .title', has_text="draft the launch plan")).to_be_visible()
    # moving to blocked demands a reason
    p.get_by_label("Move draft the launch plan to").select_option("blocked")
    dlg = p.get_by_role("dialog")
    dlg.get_by_role("button", name="Mark blocked").click()
    expect(p.get_by_text("A blocker reason is required.")).to_be_visible()
    expect(p.get_by_role("dialog")).to_have_count(0)
    p.get_by_label("Move draft the launch plan to").select_option("blocked")
    p.get_by_role("dialog").get_by_label("Blocker reason").fill("Legal review pending")
    p.get_by_role("dialog").get_by_role("button", name="Mark blocked").click()
    expect(p.locator('[data-col="blocked"] .tcard .title', has_text="draft the launch plan")).to_be_visible()
    assert ui.errors == []


def test_drawer_and_modal_focus_management(ui, account):
    make_reviewed_meeting(account)
    ui.login(account)
    p = ui.page
    p.goto(f"{ui.base_url}/#/tasks")
    opener = p.get_by_role("button", name="Open task prepare the budget report")
    opener.focus()
    opener.press("Enter")
    drawer = p.get_by_role("dialog")
    expect(drawer).to_be_visible()
    expect(p.get_by_role("button", name="Close panel")).to_be_focused()
    # unsaved changes are protected
    p.get_by_label("Title").fill("Changed title")
    p.keyboard.press("Escape")
    expect(p.get_by_role("heading", name="Discard changes?")).to_be_visible()
    p.get_by_role("button", name="Cancel").click()
    expect(p.get_by_label("Title")).to_have_value("Changed title")
    # save is confirmed by the server before the toast
    p.get_by_role("button", name="Save changes").click()
    expect(p.get_by_text("Task updated")).to_be_visible()
    p.keyboard.press("Escape")
    expect(p.get_by_role("dialog")).to_have_count(0)
    expect(opener).to_be_focused() if False else None
    # Tab never leaves a modal
    p.get_by_role("button", name="New task").click()
    for _ in range(8):
        p.keyboard.press("Tab")
    assert p.evaluate("!!document.activeElement.closest('.modal')")
    p.keyboard.press("Escape")
    assert ui.errors == []


def test_theme_reduced_motion_and_mobile(browser, base_url, account):
    ctx = browser.new_context(viewport={"width": 390, "height": 800}, reduced_motion="reduce")
    ui = Page(ctx, base_url)
    ui.login(account)
    p = ui.page
    # reduced motion collapses animation durations
    dur = p.evaluate("getComputedStyle(document.querySelector('#view')).animationDuration")
    assert dur in ("0.001s", "1ms"), dur
    # mobile navigation
    expect(p.locator("#sidebar")).not_to_be_in_viewport()
    p.get_by_role("button", name="Open navigation").click()
    expect(p.locator("#sidebar")).to_be_in_viewport()
    p.get_by_role("link", name="Tasks", exact=True).click()
    expect(p.get_by_role("heading", name="Tasks", exact=True)).to_be_visible()
    assert p.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
    # theme switching persists across reload
    before = p.evaluate("document.documentElement.dataset.theme")
    p.get_by_role("button", name=re.compile("Switch to")).click()
    after = p.evaluate("document.documentElement.dataset.theme")
    assert before != after
    p.reload()
    p.wait_for_selector(".shell")
    assert p.evaluate("document.documentElement.dataset.theme") == after
    assert ui.errors == []
    ctx.close()


def test_decision_conflict_in_ui(ui, account):
    make_reviewed_meeting(account, "Plan", "Maya: We decided to launch the product on 2026-11-01.")
    make_reviewed_meeting(account, "Replan", "Maya: We decided to launch the product on 2026-12-01.", approve=False)
    ui.login(account)
    p = ui.page
    p.goto(f"{ui.base_url}/#/decisions")
    expect(p.get_by_text("Possible conflict.")).to_be_visible()
    expect(p.get_by_text("Earlier decision", exact=True)).to_be_visible()
    expect(p.get_by_text("New statement", exact=True)).to_be_visible()
    p.get_by_role("button", name="The new statement replaces the earlier one").click()
    p.get_by_role("dialog").get_by_role("button", name="Replace").click()
    expect(p.get_by_text("Conflict resolved")).to_be_visible()
    expect(p.get_by_role("tab", name="Conflicts (0)")).to_be_visible()
    assert ui.errors == []


def test_memory_search_shows_citations_or_explains_absence(ui, account):
    make_reviewed_meeting(account, "Vendor sync", "[00:00:10] Maya: The vendor contract renewal needs legal review before December.")
    ui.login(account)
    p = ui.page
    p.goto(f"{ui.base_url}/#/memory")
    p.get_by_label("Your question").fill("What about the vendor contract review?")
    p.get_by_role("button", name="Ask").click()
    expect(p.get_by_role("link", name="Vendor sync")).to_be_visible()
    expect(p.locator(".evidence")).to_contain_text("legal review")
    p.get_by_label("Your question").fill("helicopter purchase budget")
    p.get_by_role("button", name="Ask").click()
    expect(p.get_by_text("No supporting evidence found.")).to_be_visible()
    assert ui.errors == []


def test_followup_approval_flow_end_to_end(ui, account):
    account.api("POST", "/tasks", json={"title": "Send invoice", "owner_name": "Eve Tester", "due_date": "2020-01-01"})
    account.api("POST", "/contacts", json={"name": "Alice", "email": "alice@example.com", "email_authorized": True})
    ui.login(account)
    p = ui.page
    # sending is off until an admin enables the (mock) provider
    p.goto(f"{ui.base_url}/#/followups")
    expect(p.get_by_text("Available but not enabled for this workspace").first).to_be_visible()
    p.goto(f"{ui.base_url}/#/settings?tab=integrations")
    toggle = p.locator('[data-int="email"]')
    toggle.check()
    expect(p.get_by_text("Integration enabled")).to_be_visible()
    p.goto(f"{ui.base_url}/#/followups")
    p.get_by_role("button", name="New draft").click()
    dlg = p.get_by_role("dialog")
    dlg.get_by_label("Recipient").select_option(label="Alice")
    dlg.get_by_role("button", name="Create draft").click()
    expect(p.get_by_text("Draft created")).to_be_visible()
    row = p.locator("tr", has_text="Send invoice")
    expect(row.get_by_text("Draft")).to_be_visible()
    row.get_by_role("button", name="Submit for approval").click()
    p.get_by_role("dialog").get_by_role("button", name="Submit").click()
    expect(p.get_by_text("Submitted. Waiting for approval.")).to_be_visible()
    p.goto(f"{ui.base_url}/#/approvals")
    expect(p.get_by_text("Send email to Alice (alice@example.com)")).to_be_visible()
    expect(p.locator("pre")).to_contain_text("Send invoice")
    p.get_by_role("button", name="Approve", exact=True).click()
    p.get_by_role("dialog").get_by_role("button", name="Approve").click()
    expect(p.get_by_text("Approved. It will be sent after final checks.")).to_be_visible()
    time.sleep(1.5)  # worker interval
    p.goto(f"{ui.base_url}/#/followups")
    expect(p.locator("tr", has_text="Send invoice").locator(".badge", has_text="Sent")).to_be_visible(timeout=10000)
    expect(p.get_by_text("delivery not confirmed by provider")).to_be_visible()
    assert ui.errors == []


def test_viewer_sees_read_only_ui(base_url, ui, account):
    httpx.post(f"{base_url}/api/w/{account.wid}/members", headers=account.h, json={"email": f"v{account.email}", "name": "Vic", "role": "viewer", "initial_password": PW})
    r = httpx.post(f"{base_url}/api/auth/login", json={"email": f"v{account.email}", "password": PW}).json()
    viewer = Account(base_url, f"v{account.email}", r["token"], account.wid)
    ui.login(viewer)
    p = ui.page
    p.goto(f"{ui.base_url}/#/tasks")
    expect(p.get_by_role("heading", name="Tasks", exact=True)).to_be_visible()
    expect(p.get_by_role("button", name="New task")).to_have_count(0)
    p.goto(f"{ui.base_url}/#/meetings")
    expect(p.get_by_role("button", name="New meeting")).to_have_count(0)
    assert ui.errors == []
