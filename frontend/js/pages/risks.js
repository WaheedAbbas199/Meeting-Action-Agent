import { html, mount, on } from '../dom.js';
import { api } from '../api.js';
import { pageHead } from '../components/common.js';
import { skeletonList, statusBadge, fmtDate, emptyState } from '../ui.js';
import { openTaskDrawer } from '../components/task-drawer.js';

const KIND = { overdue: 'Overdue', due_soon: 'Due soon', blocked: 'Blocked', no_owner: 'No owner', deadline_slipped: 'Deadline slipped' };

export default {
  title: 'Risks & blockers',
  async render({ root, signal, reload, isCurrent }) {
    mount(root, html`${pageHead('Risks & blockers', 'Rule-based signals only. Each risk explains the exact rule that triggered it.')}${skeletonList()}`);
    const [r, g] = await Promise.all([api.w.get('/risks', { signal }), api.w.get('/dependency-graph', { signal })]);
    if (!isCurrent()) return;
    const byId = Object.fromEntries(g.nodes.map((n) => [n.id, n]));
    mount(root, html`${pageHead('Risks & blockers', r.note)}
      <section aria-labelledby="rl"><h2 id="rl" class="mb-4">Risks (${r.items.length})</h2>
      ${r.items.length ? html`<div class="stack stagger">${r.items.map((x) => html`<article class="card"><div class="row between"><div class="row"><span class="risk-dot ${x.severity}" aria-hidden="true"></span><strong>${x.title}</strong><span class="badge ${x.severity === 'high' ? 'bad' : 'warn'}">${KIND[x.kind] || x.kind}</span><span class="sr-only">Severity ${x.severity}</span></div><button class="btn sm" data-task="${x.task_id}">Open task</button></div>
        <p class="muted mt-2">${x.explanation}</p><p class="meta mt-2">Owner: ${x.owner_name || 'unassigned'} · Deadline: ${fmtDate(x.due_date)}</p>
        ${x.dependents_impacted.length ? html`<div class="callout warn mt-4"><div><strong>Impact:</strong> ${x.dependents_impacted.length} dependent task${x.dependents_impacted.length > 1 ? 's' : ''} also affected — ${x.dependents_impacted.map((d) => `#${d.id} ${d.title}`).join(', ')}</div></div>` : ''}</article>`)}</div>`
        : emptyState('No risks detected', 'No overdue, blocked, unowned or repeatedly-slipping work right now.')}</section>
      <section class="mt-4" aria-labelledby="dg"><h2 id="dg" class="mb-4">Dependency map</h2>
      ${g.edges.length ? html`<div class="card"><ul class="stack-sm list-reset">${g.edges.map((e) => html`<li class="row"><button class="btn ghost sm" data-task="${e.task_id}">#${e.task_id} ${byId[e.task_id]?.title}</button>${statusBadge(byId[e.task_id]?.status)}<span class="muted">waits on</span><button class="btn ghost sm" data-task="${e.depends_on_id}">#${e.depends_on_id} ${byId[e.depends_on_id]?.title}</button>${statusBadge(byId[e.depends_on_id]?.status)}</li>`)}</ul></div>`
        : emptyState('No dependencies yet', 'Add a prerequisite from a task’s detail panel. Dependent tasks block automatically.')}</section>`);
    on(root, 'click', '[data-task]', (e, b) => openTaskDrawer(Number(b.dataset.task), reload));
  },
};
