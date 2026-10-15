import { html, mount, on } from '../dom.js';
import { api } from '../api.js';
import { can } from '../store.js';
import { pageHead } from '../components/common.js';
import { skeletonList, emptyState, toast, busy, errMsg, confirmDialog } from '../ui.js';
import { meter } from '../chart.js';
import { openTaskDrawer } from '../components/task-drawer.js';

export default {
  title: 'Team workload',
  async render({ root, signal, reload, isCurrent }) {
    mount(root, html`${pageHead('Team workload', '')}${skeletonList()}`);
    const w = await api.w.get('/workload', { signal });
    if (!isCurrent()) return;
    mount(root, html`${pageHead('Team workload', w.note)}
      <div class="grid auto stagger">${w.members.map((m) => html`<article class="card"><div class="row between"><strong>${m.name}</strong>${m.overloaded ? html`<span class="badge bad">Over capacity</span>` : html`<span class="badge good">Within capacity</span>`}</div>
        <p class="meta">${m.team || 'No team'} · ${m.open_tasks} open · ${m.due_this_week} due this week</p><div class="mt-4">${meter(m.points, m.capacity, m.overloaded, `${m.name} workload`)}</div><p class="meta mt-2">${m.points} of ${m.capacity} capacity points</p></article>`)}</div>
      <section class="mt-4" aria-labelledby="sg"><h2 id="sg" class="mb-4">Suggested reassignments</h2>
        ${w.suggestions.length ? html`<div class="stack">${w.suggestions.map((s) => html`<article class="card"><div class="row between"><div><strong>${s.title}</strong><p class="muted">${s.from_name} → ${s.to_name}</p><p class="meta">${s.reason}</p></div>
          <span class="row"><button class="btn sm" data-task="${s.task_id}">View task</button>${can('manager') ? html`<button class="btn sm primary" data-apply="${s.task_id}" data-to="${s.to_user_id}" data-name="${s.to_name}">Reassign to ${s.to_name}</button>` : ''}</span></div></article>`)}</div>`
        : emptyState('No reassignments suggested', 'Nobody is over capacity, or no teammate has room to take on work.')}
        ${!can('manager') && w.suggestions.length ? html`<p class="meta mt-2">Only managers can apply reassignments.</p>` : ''}</section>
      ${w.unassigned.length ? html`<section class="mt-4"><h2 class="mb-4">Not matched to a member (${w.unassigned.length})</h2><div class="card"><ul class="stack-sm list-reset">${w.unassigned.map((t) => html`<li class="row between"><span>${t.title} <span class="meta">${t.owner_name ? `Owner “${t.owner_name}” is not a member` : 'Unassigned'}</span></span><button class="btn sm" data-task="${t.id}">Open</button></li>`)}</ul></div></section>` : ''}`);
    on(root, 'click', '[data-task]', (e, b) => openTaskDrawer(Number(b.dataset.task), reload));
    on(root, 'click', '[data-apply]', async (e, b) => {
      if (!(await confirmDialog({ title: 'Reassign this task?', message: `The task moves to ${b.dataset.name}. The change is recorded in its history.`, confirmLabel: 'Reassign' }))) return;
      await busy(b, async () => { try { await api.w.post('/workload/apply', { task_id: Number(b.dataset.apply), to_user_id: Number(b.dataset.to) }); toast('Task reassigned'); reload(); } catch (er) { toast(errMsg(er), 'error'); } });
    });
  },
};
