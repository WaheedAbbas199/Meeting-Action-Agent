import { html, mount, $, on, raw } from '../dom.js';
import { api } from '../api.js';
import { store, can } from '../store.js';
import { openDrawer, toast, busy, statusBadge, prio, dueLabel, fmtDateTime, fmtDate, evidenceBlock, confidence, confirmDialog, openModal, errMsg } from '../ui.js';
import { field, options, PRIO_OPTS, formData } from './common.js';

/** Task detail drawer. `onChange` is called after any server-confirmed change. */
export async function openTaskDrawer(id, onChange = () => {}) {
  let dirty = false;
  const dr = openDrawer({ title: 'Task', subtitle: `#${id}`, isDirty: () => dirty });
  mount(dr.body, html`<div class="skeleton block"></div><div class="skeleton block"></div>`);
  const load = async () => {
    let t;
    try { t = await api.w.get(`/tasks/${id}`); } catch (e) { mount(dr.body, html`<div class="callout bad" role="alert">${errMsg(e)}</div>`); return; }
    const editable = t.can_edit && t.review_state === 'approved';
    const members = await api.w.get('/members').catch(() => []);
    mount(dr.body, html`
      <div class="row">${statusBadge(t.status)} ${prio(t.priority)} ${confidence(t.confidence)} ${t.review_state !== 'approved' ? statusBadge(t.review_state) : ''}</div>
      ${t.blocker_reason ? html`<div class="callout warn"><div><strong>Blocked.</strong> ${t.blocker_reason}</div></div>` : ''}
      <form id="tform" class="stack" novalidate>
        ${field('t-title', 'Title', html`<input id="t-title" name="title" class="input" value="${t.title}" ${editable || t.review_state === 'pending' ? '' : raw('disabled')} maxlength="300" required>`)}
        <div class="grid cols-2">
          ${field('t-owner', 'Owner', html`<select id="t-owner" name="owner_user_id" class="select" ${can('manager') ? '' : raw('disabled')}><option value="">${t.owner_name && !t.owner_user_id ? `${t.owner_name} (not a member)` : 'Unassigned'}</option>${options(members.map((m) => [m.user_id, m.name]), t.owner_user_id)}</select>`, t.uncertain_fields.includes('owner') ? 'The AI was unsure who owns this.' : '')}
          ${field('t-prio', 'Priority', html`<select id="t-prio" name="priority" class="select">${options(PRIO_OPTS, t.priority)}</select>`)}
        </div>
        ${field('t-due', 'Deadline', html`<input id="t-due" name="due_date" type="date" class="input" value="${t.due_date || ''}">`, t.uncertain_fields.includes('due_date') ? 'No reliable deadline was found. Confirm one.' : t.due_inferred ? 'Inferred from a relative date in the meeting.' : t.original_due_date ? `Originally ${fmtDate(t.original_due_date)} · changed ${t.deadline_changes}×` : '')}
        ${field('t-desc', 'Notes', html`<textarea id="t-desc" name="description" class="textarea" maxlength="5000">${t.description}</textarea>`)}
        <div class="row between"><span class="meta">${dueLabel(t)}</span>${(editable || t.review_state === 'pending') && t.can_edit ? html`<button class="btn primary" type="submit">Save changes</button>` : ''}</div>
      </form>
      ${editable ? html`<section class="stack-sm"><h3>Status</h3><div class="row">${['open', 'in_progress', 'blocked', 'done'].map((s) => html`<button class="btn sm" data-status="${s}" aria-pressed="${t.status === s}" ${t.status === s ? raw('disabled') : ''}>${{ open: 'Open', in_progress: 'In progress', blocked: 'Blocked', done: 'Done' }[s]}</button>`)}</div></section>` : ''}
      <section class="stack-sm"><h3>Dependencies</h3>
        ${t.prerequisites.length ? t.prerequisites.map((p) => html`<div class="row between"><span>Waits on <a href="#/tasks?open=${p.id}" data-open="${p.id}">#${p.id} ${p.title}</a> ${statusBadge(p.status)}</span>${editable ? html`<button class="btn ghost sm" data-rmdep="${p.id}" aria-label="Remove dependency on ${p.title}">Remove</button>` : ''}</div>`) : html`<p class="meta">No prerequisites.</p>`}
        ${t.dependents.length ? html`<p class="meta">Unblocks: ${t.dependents.map((d) => `#${d.id} ${d.title}`).join(', ')}</p>` : ''}
        ${editable ? html`<div class="row"><select id="dep-sel" class="select sel-sm" aria-label="Choose prerequisite task"><option value="">Add prerequisite…</option></select><button class="btn sm" id="dep-add">Add</button></div>` : ''}
      </section>
      ${t.evidence_quote ? html`<section class="stack-sm"><h3>Evidence</h3>${t.evidence_context.length ? t.evidence_context.map((c) => c.is_evidence ? evidenceBlock(c.text, `${c.speaker || 'Unknown speaker'}${t.meeting ? ` · ${t.meeting.title}` : ''}`) : html`<p class="meta">${c.speaker ? `${c.speaker}: ` : ''}${c.text}</p>`) : evidenceBlock(t.evidence_quote)}
        ${t.meeting ? html`<a href="#/meetings/${t.meeting.id}">Open meeting “${t.meeting.title}”</a>` : ''}</section>` : ''}
      ${t.review_state === 'approved' && can('member') ? html`<section class="stack-sm"><h3>Follow up</h3><button class="btn sm" id="fu-btn">Draft a follow-up…</button></section>` : ''}
      <section class="stack-sm"><h3>Activity</h3>${t.events.length ? html`<ol class="timeline">${t.events.map((e) => html`<li><strong>${e.actor}</strong> ${e.kind.replaceAll('_', ' ')}${e.field ? html` · ${e.field}: <span class="muted">${e.old || '—'}</span> → ${e.new || '—'}` : ''}<div class="meta">${fmtDateTime(e.at)}</div></li>`)}</ol>` : html`<p class="meta">No activity yet.</p>`}</section>`);
    dirty = false;
    // dependency candidates
    if (editable) {
      api.w.get('/tasks?page_size=100&status=open,in_progress,blocked').then((r) => { const sel = $('#dep-sel', dr.body); if (sel) mount(sel, html`<option value="">Add prerequisite…</option>${r.items.filter((x) => x.id !== t.id && !t.prerequisites.some((p) => p.id === x.id)).map((x) => html`<option value="${x.id}">#${x.id} ${x.title}</option>`)}`); }).catch(() => {});
    }
    const form = $('#tform', dr.body);
    form?.addEventListener('input', () => { dirty = true; });
    form?.addEventListener('submit', async (e) => {
      e.preventDefault(); const d = formData(form); const btn = e.submitter;
      if (!d.title.trim()) { toast('A task needs a title.', 'error'); return; }
      const body = { title: d.title, priority: d.priority, due_date: d.due_date || null, description: d.description };
      if (!$('#t-owner', form).disabled) body.owner_user_id = d.owner_user_id ? Number(d.owner_user_id) : null;
      await busy(btn, async () => { try { await api.w.patch(`/tasks/${id}`, body); dirty = false; toast('Task updated'); await load(); onChange(); } catch (er) { toast(errMsg(er), 'error'); } });
    });
  };
  on(dr.body, 'click', '[data-status]', async (e, b) => {
    const s = b.dataset.status; let reason = '';
    if (s === 'blocked') { reason = await promptReason(); if (!reason) return; }
    await busy(b, async () => { try { await api.w.post(`/tasks/${id}/status`, { status: s, blocker_reason: reason }); toast('Status updated'); await load(); onChange(); } catch (er) { toast(errMsg(er), 'error'); } });
  });
  on(dr.body, 'click', '#dep-add', async (e, b) => {
    const v = $('#dep-sel', dr.body).value; if (!v) return;
    await busy(b, async () => { try { await api.w.post(`/tasks/${id}/dependencies`, { depends_on_id: Number(v) }); toast('Dependency added'); await load(); onChange(); } catch (er) { toast(errMsg(er), 'error'); } });
  });
  on(dr.body, 'click', '[data-rmdep]', async (e, b) => { await busy(b, async () => { try { await api.w.del(`/tasks/${id}/dependencies/${b.dataset.rmdep}`); toast('Dependency removed'); await load(); onChange(); } catch (er) { toast(errMsg(er), 'error'); } }); });
  on(dr.body, 'click', '[data-open]', (e, a) => { e.preventDefault(); dr.close(); setTimeout(() => openTaskDrawer(Number(a.dataset.open), onChange), 200); });
  on(dr.body, 'click', '#fu-btn', () => { dr.close(); setTimeout(() => import('../pages/followups.js').then((m) => m.openNewFollowup(id, onChange)), 200); });
  await load();
  return dr;
}

export async function promptReason() {
  let value = '';
  const r = await openModal({ title: 'Why is this blocked?', labelledBy: 'reason-title', body: field('block-reason', 'Blocker reason', html`<textarea id="block-reason" class="textarea" maxlength="1000" autofocus placeholder="e.g. Waiting for legal sign-off"></textarea>`),
    actions: html`<button class="btn" data-close="cancel">Cancel</button><button class="btn primary" data-close="ok">Mark blocked</button>`,
    onMount: (box) => box.querySelector('textarea').addEventListener('input', (e) => { value = e.target.value; }) });
  if (r !== 'ok') return '';
  if (!value.trim()) { toast('A blocker reason is required.', 'error'); return ''; }
  return value.trim();
}
