import { html, mount, $, on } from '../dom.js';
import { api } from '../api.js';
import { can } from '../store.js';
import { pageHead, field, options } from '../components/common.js';
import { skeletonList, statusBadge, emptyState, toast, busy, errMsg, openModal, fmtDateTime, confirmDialog } from '../ui.js';

/** Create a draft for a task, then let the user review the exact message before submitting for approval. */
export async function openNewFollowup(taskId, done = () => {}) {
  let tasks = [], contacts = [];
  try { [tasks, contacts] = await Promise.all([api.w.get('/tasks?page_size=100&status=open,in_progress,blocked'), api.w.get('/contacts')]); } catch (e) { return toast(errMsg(e), 'error'); }
  if (!contacts.length) return toast('Add a contact with consent first (Settings → Contacts).', 'error');
  const r = await openModal({ title: 'New follow-up draft', body: html`<form id="ff" class="stack" novalidate>
    ${field('ff-task', 'Task', html`<select id="ff-task" class="select">${options(tasks.items.map((t) => [t.id, `#${t.id} ${t.title}`]), taskId)}</select>`)}
    ${field('ff-contact', 'Recipient', html`<select id="ff-contact" class="select">${options(contacts.map((c) => [c.id, c.name]), '')}</select>`, 'Only contacts who have consented to the channel can be used.')}
    ${field('ff-ch', 'Channel', html`<select id="ff-ch" class="select"><option value="email">Email</option><option value="whatsapp">WhatsApp</option></select>`)}<p class="error-text" id="ff-err" role="alert"></p></form>`,
    actions: html`<button class="btn" data-close="cancel">Cancel</button><button class="btn primary" id="ff-go">Create draft</button>`,
    onMount: (box, finish) => $('#ff-go', box).addEventListener('click', (e) => busy(e.currentTarget, async () => {
      try { finish(await api.w.post('/followups', { task_id: Number($('#ff-task', box).value), contact_id: Number($('#ff-contact', box).value), channel: $('#ff-ch', box).value })); }
      catch (er) { $('#ff-err', box).textContent = errMsg(er); }
    })) });
  if (r) { toast('Draft created. Review it, then submit for approval.'); done(); if (location.hash.startsWith('#/followups')) window.dispatchEvent(new HashChangeEvent('hashchange')); else location.hash = '/followups'; }
}

export default {
  title: 'Follow-ups',
  async render({ root, signal, reload, isCurrent }) {
    mount(root, html`${pageHead('Email & WhatsApp follow-ups', '')}${skeletonList()}`);
    const [fus, ints] = await Promise.all([api.w.get('/followups', { signal }), api.w.get('/integrations', { signal })]);
    if (!isCurrent()) return;
    const ch = Object.fromEntries(ints.map((i) => [i.kind, i]));
    mount(root, html`${pageHead('Email & WhatsApp follow-ups', 'Drafts are never sent until a manager approves the exact message.',
        html`${can('manager') ? html`<button class="btn" id="rr">Apply reminder rules</button>` : ''}${can('member') ? html`<button class="btn primary" id="nf">New draft</button>` : ''}`)}
      <div class="grid cols-2 mb-4">${['email', 'whatsapp'].map((k) => html`<div class="callout ${ch[k]?.ready && ch[k]?.enabled ? 'good' : 'warn'}" role="note"><div><strong>${k === 'email' ? 'Email' : 'WhatsApp'}:</strong> ${ch[k]?.enabled && ch[k]?.ready ? ch[k].message : ch[k]?.ready ? 'Available but not enabled for this workspace (Settings → Integrations).' : `Sending is off. ${ch[k]?.message || ''}`}</div></div>`)}</div>
      ${fus.length ? html`<div class="table-wrap"><table><caption class="sr-only">Follow-ups</caption><thead><tr><th scope="col">Task</th><th scope="col">To</th><th scope="col">Channel</th><th scope="col">Status</th><th scope="col">Details</th><th scope="col"><span class="sr-only">Actions</span></th></tr></thead>
        <tbody>${fus.map((f) => html`<tr><td>${f.task_title || '—'}</td><td>${f.recipient || '—'}</td><td>${f.channel === 'email' ? 'Email' : 'WhatsApp'}</td><td>${statusBadge(f.status)}</td>
          <td class="meta">${f.last_error ? html`<span class="error-text">${f.last_error}</span>` : f.sent_at ? html`Sent ${fmtDateTime(f.sent_at)}${f.delivery_status ? ` · provider reports “${f.delivery_status}”` : ' · delivery not confirmed by provider'}` : f.attempts ? `${f.attempts} attempt(s)` : ''}</td>
          <td class="right nowrap"><button class="btn sm" data-view="${f.id}">Preview</button>${f.status === 'draft' && can('member') ? html` <button class="btn sm primary" data-submit="${f.id}">Submit for approval</button>` : ''}${f.status === 'failed' && can('manager') ? html` <button class="btn sm" data-retry="${f.id}">Retry</button> <button class="btn sm" data-submit="${f.id}">Re-submit</button>` : ''}${['rejected', 'expired', 'revoked'].includes(f.status) && can('member') ? html` <button class="btn sm" data-submit="${f.id}">Submit again</button>` : ''}</td></tr>`)}</tbody></table></div>`
        : emptyState('No follow-ups yet', 'Open a task and choose “Draft a follow-up”, or apply your reminder rules.', can('member') ? html`<button class="btn primary" id="nf2">Create a draft</button>` : '')}`);
    const start = () => openNewFollowup(null, () => {}); $('#nf', root)?.addEventListener('click', start); $('#nf2', root)?.addEventListener('click', start);
    $('#rr', root)?.addEventListener('click', (e) => busy(e.currentTarget, async () => { try { const r = await api.w.post('/followups/run-reminders'); toast(`${r.drafts_created} draft(s) created${r.skipped.length ? `, ${r.skipped.length} skipped` : ''}`); reload(); } catch (er) { toast(errMsg(er), 'error'); } }));
    on(root, 'click', '[data-view]', (e, b) => { const f = fus.find((x) => x.id === Number(b.dataset.view)); openModal({ title: `${f.channel === 'email' ? 'Email' : 'WhatsApp'} to ${f.recipient}`, body: html`${f.subject ? html`<p><strong>Subject:</strong> ${f.subject}</p>` : ''}<pre class="card flat pre">${f.body}</pre>`, actions: html`<button class="btn primary" data-close="cancel">Close</button>` }); });
    on(root, 'click', '[data-submit]', async (e, b) => {
      if (!(await confirmDialog({ title: 'Submit for approval?', message: 'A manager will review this exact message and recipient. Nothing is sent until they approve.', confirmLabel: 'Submit' }))) return;
      await busy(b, async () => { try { await api.w.post(`/followups/${b.dataset.submit}/submit`); toast('Submitted. Waiting for approval.'); window.dispatchEvent(new Event('app:badges')); reload(); } catch (er) { toast(errMsg(er), 'error'); } });
    });
    on(root, 'click', '[data-retry]', (e, b) => busy(b, async () => { try { await api.w.post(`/followups/${b.dataset.retry}/retry`); toast('Retry queued'); reload(); } catch (er) { toast(errMsg(er), 'error'); } }));
  },
};
