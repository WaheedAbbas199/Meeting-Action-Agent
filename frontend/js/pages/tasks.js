import { html, mount, $, $$, on, debounce, raw } from '../dom.js';
import { api, isAbort } from '../api.js';
import { can } from '../store.js';
import { go } from '../router.js';
import { pageHead, field, options, STATUS_OPTS, PRIO_OPTS, formData } from '../components/common.js';
import { skeletonList, statusBadge, prio, dueLabel, emptyState, errorState, toast, busy, errMsg, openModal } from '../ui.js';
import { openTaskDrawer, promptReason } from '../components/task-drawer.js';
import { icon } from '../icons.js';

const COLS = [['open', 'Open'], ['in_progress', 'In progress'], ['blocked', 'Blocked'], ['done', 'Done']];

function newTaskModal() {
  let dirty = false;
  return openModal({ title: 'New task', isDirty: () => dirty, body: html`<form id="ntf" class="stack" novalidate>
      ${field('n-title', 'Title', html`<input id="n-title" name="title" class="input" maxlength="300" required autofocus>`)}
      <div class="grid cols-2">${field('n-owner', 'Owner (name)', html`<input id="n-owner" name="owner_name" class="input" maxlength="120">`)}${field('n-prio', 'Priority', html`<select id="n-prio" name="priority" class="select">${options(PRIO_OPTS, 'medium')}</select>`)}</div>
      ${field('n-due', 'Deadline', html`<input id="n-due" name="due_date" type="date" class="input">`)}<p class="error-text" id="n-err" role="alert"></p></form>`,
    actions: html`<button class="btn" data-close="cancel">Cancel</button><button class="btn primary" id="n-save">Create task</button>`,
    onMount: (box, finish) => {
      box.addEventListener('input', () => { dirty = true; });
      $('#n-save', box).addEventListener('click', async (e) => {
        const d = formData($('#ntf', box)); const err = $('#n-err', box); err.textContent = '';
        if (!d.title.trim()) { err.textContent = 'A task needs a title.'; $('#n-title', box).focus(); return; }
        await busy(e.currentTarget, async () => { try { const r = await api.w.post('/tasks', { ...d, due_date: d.due_date || null }); dirty = false; finish(r); } catch (er) { err.textContent = errMsg(er); } });
      });
    } });
}

export default {
  title: 'Tasks',
  async render({ root, signal, reload, query, onCleanup, isCurrent }) {
    const st = { q: '', status: query.status || '', priority: '', owner: '', due: query.due || '', sort: 'due', page: 1, view: sessionStorage.getItem('maa.taskview') || 'list' };
    mount(root, html`${pageHead('Tasks', 'Every commitment with owner, deadline, dependencies and the evidence behind it.', can('member') ? html`<button class="btn primary" id="nt">${icon('plus')} New task</button>` : '')}
      <div class="row mb-4" role="search" aria-label="Filter tasks">
        <div class="search grow w-md">${icon('search')}<label class="sr-only" for="f-q">Search tasks</label><input id="f-q" class="input" type="search" placeholder="Search title or owner"></div>
        <label class="sr-only" for="f-status">Status</label><select id="f-status" class="select sel-sm">${options(STATUS_OPTS, st.status)}</select>
        <label class="sr-only" for="f-prio">Priority</label><select id="f-prio" class="select sel-sm">${options([['', 'Any priority'], ...PRIO_OPTS], '')}</select>
        <label class="sr-only" for="f-owner">Owner</label><select id="f-owner" class="select sel-sm">${options([['', 'Any owner'], ['me', 'Assigned to me'], ['unassigned', 'Unassigned']], '')}</select>
        <label class="sr-only" for="f-due">Deadline</label><select id="f-due" class="select sel-sm">${options([['', 'Any deadline'], ['overdue', 'Overdue'], ['soon', 'Due within 7 days'], ['none', 'No deadline']], st.due)}</select>
        <label class="sr-only" for="f-sort">Sort</label><select id="f-sort" class="select sel-sm">${options([['due', 'Sort: deadline'], ['priority', 'Sort: priority'], ['created', 'Sort: newest'], ['title', 'Sort: title']], 'due')}</select>
        <div class="seg" role="group" aria-label="View"><button id="v-list" aria-pressed="${st.view === 'list'}">List</button><button id="v-board" aria-pressed="${st.view === 'board'}">Board</button></div></div>
      <div id="tbody" aria-live="polite">${skeletonList()}</div><p class="sr-only" id="tstatus" role="status"></p>`);
    let rctl = null;
    const load = async () => {
      rctl?.abort(); rctl = new AbortController(); const sig = rctl.signal;
      const p = new URLSearchParams({ sort: st.sort, page: st.view === 'board' ? 1 : st.page, page_size: st.view === 'board' ? 100 : 25 });
      if (st.status && st.view === 'list') p.set('status', st.status); if (st.view === 'board') p.set('status', 'open,in_progress,blocked,done');
      ['q', 'priority', 'owner', 'due'].forEach((k) => st[k] && p.set(k, st[k]));
      if (st.priority) p.set('priority', st.priority);
      try {
        const r = await api.w.get(`/tasks?${p}`, { signal: sig });
        if (!isCurrent() || sig.aborted) return;
        $('#tstatus', root).textContent = `${r.total} task${r.total === 1 ? '' : 's'} found`;
        mount($('#tbody', root), st.view === 'board' ? board(r.items) : list(r));
      } catch (e) { if (!isAbort(e)) { mount($('#tbody', root), errorState(e)); $('[data-action="retry"]', root)?.addEventListener('click', load); } }
    };
    const list = (r) => !r.items.length ? emptyState('No tasks match', 'Try clearing a filter, or create a task.', can('member') ? html`<button class="btn" data-action="clear">Clear filters</button>` : '') : html`
      <div class="table-wrap"><table><caption class="sr-only">Tasks</caption><thead><tr><th scope="col">Task</th><th scope="col">Owner</th><th scope="col">Priority</th><th scope="col">Status</th><th scope="col">Deadline</th></tr></thead>
      <tbody>${r.items.map((t) => html`<tr class="clickable" data-open="${t.id}"><td><button class="btn ghost sm" data-open="${t.id}" aria-label="Open task ${t.title}"><strong class="truncate">${t.title}</strong></button>${t.blocker_reason ? html`<div class="meta">${t.blocker_reason}</div>` : ''}</td><td>${t.owner_name || html`<span class="muted">Unassigned</span>`}</td><td>${prio(t.priority)}</td><td>${statusBadge(t.status)}</td><td>${dueLabel(t)}</td></tr>`)}</tbody></table>
      <div class="pager"><span>Page ${r.page} of ${Math.max(1, Math.ceil(r.total / r.page_size))} · ${r.total} total</span><span class="row"><button class="btn sm" data-page="-1" ${r.page <= 1 ? raw('disabled') : ''}>Previous</button><button class="btn sm" data-page="1" ${r.page * r.page_size >= r.total ? raw('disabled') : ''}>Next</button></span></div></div>`;
    const board = (items) => html`<p class="meta mb-4">Drag a card to change its status, or use the “Move to” menu on each card. ${can('member') ? '' : 'You have read-only access.'}</p>
      <div class="kanban">${COLS.map(([k, label]) => { const cards = items.filter((t) => t.status === k); return html`<section class="col" data-col="${k}" aria-label="${label}"><div class="col-head"><span>${label}</span><span class="badge plain">${cards.length}</span></div><div class="stack-sm" data-dropzone>${cards.map((t) => html`<article class="tcard" draggable="${can('member')}" data-card="${t.id}"><button class="title" data-open="${t.id}">${t.title}</button><div class="row between meta"><span>${t.owner_name || 'Unassigned'}</span>${prio(t.priority)}</div><div class="meta">${dueLabel(t)}</div>
        ${can('member') ? html`<label class="sr-only" for="mv-${t.id}">Move ${t.title} to</label><select id="mv-${t.id}" class="select sel-sm" data-move="${t.id}"><option value="">Move to…</option>${COLS.filter(([c]) => c !== k).map(([c, l]) => html`<option value="${c}">${l}</option>`)}</select>` : ''}</article>`)}${cards.length ? '' : html`<p class="meta pad">Nothing here.</p>`}</div></section>`; })}</div>`;
    const changeStatus = async (id, status, el) => {
      let reason = ''; if (status === 'blocked') { reason = await promptReason(); if (!reason) return load(); }
      try { await api.w.post(`/tasks/${id}/status`, { status, blocker_reason: reason }); toast(`Moved to ${COLS.find(([k]) => k === status)[1]}`); await load(); const c = $(`[data-card="${id}"]`, root); c?.classList.add('flash'); }
      catch (e) { toast(errMsg(e), 'error'); load(); }
    };
    // filters (debounced search; every change cancels the previous request)
    const refetch = () => { st.page = 1; load(); };
    $('#f-q', root).addEventListener('input', debounce((e) => { st.q = e.target.value.trim(); refetch(); }, 300));
    [['f-status', 'status'], ['f-prio', 'priority'], ['f-owner', 'owner'], ['f-due', 'due'], ['f-sort', 'sort']].forEach(([id, k]) => $('#' + id, root).addEventListener('change', (e) => { st[k] = e.target.value; refetch(); }));
    const setView = (v) => { st.view = v; sessionStorage.setItem('maa.taskview', v); $('#v-list', root).setAttribute('aria-pressed', v === 'list'); $('#v-board', root).setAttribute('aria-pressed', v === 'board'); load(); };
    $('#v-list', root).addEventListener('click', () => setView('list')); $('#v-board', root).addEventListener('click', () => setView('board'));
    $('#nt', root)?.addEventListener('click', async () => { const r = await newTaskModal(); if (r) { toast('Task created'); load(); } });
    on(root, 'click', '[data-open]', (e, el) => { e.stopPropagation(); openTaskDrawer(Number(el.dataset.open), load); });
    on(root, 'click', '[data-page]', (e, b) => { st.page += Number(b.dataset.page); load(); });
    on(root, 'click', '[data-action="clear"]', () => { Object.assign(st, { q: '', status: '', priority: '', owner: '', due: '' }); ['f-q', 'f-status', 'f-prio', 'f-owner', 'f-due'].forEach((i) => { $('#' + i, root).value = ''; }); refetch(); });
    on(root, 'change', '[data-move]', (e, s) => s.value && changeStatus(Number(s.dataset.move), s.value));
    // drag and drop (the select above is the keyboard-accessible alternative)
    let dragId = null;
    root.addEventListener('dragstart', (e) => { const c = e.target.closest('[data-card]'); if (!c) return; dragId = Number(c.dataset.card); c.classList.add('dragging'); e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', String(dragId)); });
    root.addEventListener('dragend', (e) => { e.target.closest?.('[data-card]')?.classList.remove('dragging'); $$('.col', root).forEach((c) => c.classList.remove('drop')); });
    root.addEventListener('dragover', (e) => { const c = e.target.closest('.col'); if (c && dragId) { e.preventDefault(); $$('.col', root).forEach((x) => x.classList.toggle('drop', x === c)); } });
    root.addEventListener('drop', (e) => { const c = e.target.closest('.col'); if (!c || !dragId) return; e.preventDefault(); const id = dragId; dragId = null; $$('.col', root).forEach((x) => x.classList.remove('drop')); changeStatus(id, c.dataset.col); });
    if (query.open) openTaskDrawer(Number(query.open), load);
    await load();
  },
};
