import { html, mount } from '../dom.js';
import { api } from '../api.js';
import { pageHead } from '../components/common.js';
import { skeletonCards, pct, fmtDate } from '../ui.js';
import { barChart } from '../chart.js';

export default {
  title: 'Analytics',
  async render({ root, signal, isCurrent }) {
    mount(root, html`${pageHead('Meeting effectiveness analytics', '')}${skeletonCards(4)}`);
    const a = await api.w.get('/analytics', { signal });
    if (!isCurrent()) return;
    const k = (label, v, hint) => html`<div class="card kpi" title="${hint}"><span class="value">${v}</span><span class="label">${label}</span></div>`;
    const fu = a.followups, q = a.ai_quality, labels = a.trends.weeks.map((w) => w.slice(5));
    mount(root, html`${pageHead('Meeting effectiveness analytics', 'Calculated from your workspace records. Hover a number for its definition.')}
      <div class="grid cols-4 stagger">${k('Completion rate', pct(a.completion_rate), a.definitions.completion_rate)}${k('On-time completion', pct(a.on_time_completion_rate), a.definitions.on_time_completion_rate)}${k('Overdue', a.overdue, a.definitions.overdue)}${k('Outstanding commitments', a.open_tasks, a.definitions.open_tasks)}
        ${k('Blocked tasks', a.blocked, a.definitions.blocked)}${k('Pending decisions', a.pending_decisions, a.definitions.pending_decisions)}${k('Deadline changes', a.deadline_changes.total, `${a.deadline_changes.tasks_affected} task(s) affected`)}${k('Follow-up attempts', fu.attempts, 'Provider send attempts recorded')}</div>
      <div class="grid cols-2 mt-4"><section class="card"><div class="card-head"><h2>Weekly trend</h2></div>${a.trends.sufficient ? barChart({ labels, title: 'Tasks created and completed per week', series: [{ name: 'Created', values: a.trends.created, cls: 'bar-a' }, { name: 'Completed', values: a.trends.completed, cls: 'bar-b' }] }) : html`<p class="muted">${a.trends.note}</p>`}</section>
        <section class="card"><div class="card-head"><h2>Follow-up outcomes</h2></div>${fu.total ? html`<table><tbody>${Object.entries(fu.by_status).map(([s, n]) => html`<tr><td>${s.replaceAll('_', ' ')}</td><td class="right"><strong>${n}</strong></td></tr>`)}</tbody></table>` : html`<p class="muted">No follow-ups yet.</p>`}</section></div>
      <section class="card mt-4"><div class="card-head"><h2>AI extraction quality</h2><span class="meta">From human review decisions and corrections</span></div>
        <div class="grid cols-4"><div class="kpi"><span class="value">${q.extracted}</span><span class="label">Candidates extracted</span></div><div class="kpi"><span class="value">${pct(q.acceptance_rate)}</span><span class="label">Acceptance rate</span></div><div class="kpi"><span class="value">${q.corrected}</span><span class="label">Approved items corrected</span></div><div class="kpi"><span class="value">${pct(q.correction_rate)}</span><span class="label">Correction rate</span></div></div></section>
      <section class="mt-4"><h2 class="mb-4">Recent meetings</h2>${a.meeting_effectiveness.length ? html`<div class="table-wrap"><table><caption class="sr-only">Meeting effectiveness</caption><thead><tr><th scope="col">Meeting</th><th scope="col">Date</th><th scope="col">Tasks</th><th scope="col">With owner</th><th scope="col">With deadline</th><th scope="col">Completed</th></tr></thead>
        <tbody>${a.meeting_effectiveness.map((m) => html`<tr><td><a href="#/meetings/${m.meeting_id}">${m.title}</a></td><td>${fmtDate(m.held_on)}</td><td>${m.tasks}</td><td>${m.tasks ? pct(m.with_owner / m.tasks) : '—'}</td><td>${m.tasks ? pct(m.with_deadline / m.tasks) : '—'}</td><td>${m.tasks ? pct(m.completed / m.tasks) : '—'}</td></tr>`)}</tbody></table></div>` : html`<p class="muted">No meetings yet.</p>`}</section>`);
  },
};
