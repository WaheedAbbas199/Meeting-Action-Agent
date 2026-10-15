import { html, mount, $, on } from '../dom.js';
import { api } from '../api.js';
import { store, can } from '../store.js';
import { pageHead } from '../components/common.js';
import { skeletonCards, statusBadge, prio, dueLabel, pct, relTime, fmtDate, emptyState } from '../ui.js';
import { openTaskDrawer } from '../components/task-drawer.js';

export default {
  title: 'Dashboard',
  async render({ root, signal, reload, isCurrent }) {
    mount(root, html`${pageHead('Dashboard', 'What your team committed to, what is at risk, and what needs a decision.')}${skeletonCards(6)}`);
    const d = await api.w.get('/dashboard', { signal });
    if (!isCurrent()) return;
    const kpi = (label, value, href, cls = '', hint = '') => html`<a class="card kpi interactive ${cls}" href="${href}" title="${hint}"><span class="value">${value}</span><span class="label">${label}</span></a>`;
    mount(root, html`${pageHead('Dashboard', store.ws.is_demo ? 'This workspace contains clearly-labelled sample data.' : 'What your team committed to, what is at risk, and what needs a decision.',
        can('member') ? html`<a class="btn primary" href="#/meetings?new=1">New meeting</a>` : '')}
      <div class="grid cols-3 stagger">
        ${kpi('Open tasks', d.open_tasks, '#/tasks', '', d.definitions.open_tasks)}${kpi('Overdue commitments', d.overdue, '#/tasks?due=overdue', d.overdue ? 'bad' : 'good', d.definitions.overdue)}
        ${kpi('Due in 3 days', d.due_soon, '#/tasks?due=soon', d.due_soon ? 'warn' : '', d.definitions.due_soon)}${kpi('Blocked tasks', d.blocked, '#/tasks?status=blocked', d.blocked ? 'bad' : '', d.definitions.blocked)}
        ${kpi('Pending decisions', d.pending_decisions, '#/decisions', d.pending_decisions ? 'warn' : '', d.definitions.pending_decisions)}${kpi('Pending approvals', d.pending_approvals, '#/approvals', d.pending_approvals ? 'warn' : '', d.definitions.pending_approvals)}
      </div>
      <div class="grid cols-2 mt-4">
        <section class="card" aria-labelledby="up-h"><div class="card-head"><h2 id="up-h">Next up</h2><a href="#/tasks">All tasks</a></div>
          ${d.upcoming_tasks.length ? html`<div class="stack-sm">${d.upcoming_tasks.map((t) => html`<button class="row between btn ghost list-btn" data-task="${t.id}"><span class="grow truncate">${t.title}<br><span class="meta">${t.owner_name || 'Unassigned'} · ${prio(t.priority)}</span></span><span class="nowrap">${dueLabel(t)}</span></button>`)}</div>` : emptyState('No open tasks', 'Process a meeting to see commitments here.', can('member') ? html`<a class="btn primary" href="#/meetings?new=1">Add a meeting</a>` : '')}</section>
        <section class="card" aria-labelledby="rk-h"><div class="card-head"><h2 id="rk-h">Needs attention</h2><a href="#/risks">All risks</a></div>
          ${d.risks.length ? html`<div class="stack-sm">${d.risks.map((r) => html`<button class="row btn ghost list-btn top" data-task="${r.task_id}"><span class="risk-dot ${r.severity} mt-2" aria-hidden="true"></span><span class="grow"><strong>${r.title}</strong><br><span class="meta">${r.explanation}</span></span><span class="sr-only">Severity ${r.severity}</span></button>`)}</div>` : emptyState('Nothing at risk', 'No overdue, blocked or unowned work right now.')}</section>
        <section class="card" aria-labelledby="rm-h"><div class="card-head"><h2 id="rm-h">Recent meetings</h2><a href="#/meetings">All meetings</a></div>
          ${d.recent_meetings.length ? html`<div class="stack-sm">${d.recent_meetings.map((m) => html`<a class="row between" href="#/meetings/${m.id}"><span>${m.title}<br><span class="meta">${fmtDate(m.held_on)}</span></span>${statusBadge(m.status)}</a>`)}</div>` : emptyState('No meetings yet', 'Paste a transcript or upload a file to get started.')}</section>
        <section class="card" aria-labelledby="ra-h"><div class="card-head"><h2 id="ra-h">Recent activity</h2></div>
          ${d.recent_activity.length ? html`<ol class="timeline">${d.recent_activity.map((a) => html`<li><strong>${a.actor}</strong> ${a.kind.replaceAll('_', ' ')}${a.field ? html` ${a.field}: ${a.old || '—'} → ${a.new || '—'}` : ''} on <em>${a.task_title}</em><div class="meta">${relTime(a.at)}</div></li>`)}</ol>` : html`<p class="muted">No activity yet.</p>`}</section>
      </div>
      <details class="card flat mt-4"><summary>How these numbers are calculated</summary><dl class="stack-sm mt-2">${Object.entries(d.definitions).map(([k, v]) => html`<div><dt><strong>${k.replaceAll('_', ' ')}</strong></dt><dd class="muted dd">${v}</dd></div>`)}</dl></details>`);
    on(root, 'click', '[data-task]', (e, b) => openTaskDrawer(Number(b.dataset.task), reload));
  },
};
