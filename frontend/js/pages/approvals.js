import { html, mount, $, on } from '../dom.js';
import { api } from '../api.js';
import { can } from '../store.js';
import { pageHead, field } from '../components/common.js';
import { skeletonList, statusBadge, emptyState, toast, busy, errMsg, openModal, fmtDateTime } from '../ui.js';

function left(iso) { const m = Math.round((new Date(iso) - Date.now()) / 60000); return m <= 0 ? 'expired' : m < 60 ? `${m} min left` : `${Math.round(m / 60)} h left`; }

export default {
  title: 'Approvals',
  async render({ root, signal, reload, isCurrent }) {
    mount(root, html`${pageHead('Approval center', '')}${skeletonList()}`);
    const all = await api.w.get('/approvals', { signal });
    if (!isCurrent()) return;
    const pending = all.filter((a) => a.status === 'pending'), history = all.filter((a) => a.status !== 'pending');
    const action = (a) => a.kind === 'followup' ? `Send ${a.payload.channel} to ${a.payload.recipient} (${a.payload.to})` : `Create calendar event “${a.payload.title}” at ${fmtDateTime(a.payload.start)}`;
    mount(root, html`${pageHead('Approval center', 'Approvals are re-validated at send time: recipient consent, task state, your role and the expiry are all checked again.')}
      <section aria-labelledby="pd"><h2 id="pd" class="mb-4">Waiting for a decision (${pending.length})</h2>
      ${pending.length ? html`<div class="stack stagger">${pending.map((a) => html`<article class="card"><div class="row between"><strong>${action(a)}</strong><span class="badge warn">${left(a.expires_at)}</span></div>
        <p class="meta mt-2">Requested by ${a.requested_by || 'unknown'} · expires ${fmtDateTime(a.expires_at)}</p>
        ${a.kind === 'followup' ? html`<div class="card flat mt-4"><p class="meta">Task: ${a.payload.task_title}</p>${a.payload.subject ? html`<p><strong>Subject:</strong> ${a.payload.subject}</p>` : ''}<pre class="pre mt-2">${a.payload.body}</pre></div>` : html`<p class="muted mt-2">${a.payload.items} agenda item(s).</p>`}
        ${can('manager') ? html`<div class="row mt-4"><button class="btn primary" data-dec="approve" data-id="${a.id}">Approve</button><button class="btn danger" data-dec="reject" data-id="${a.id}">Reject</button></div>` : html`<p class="meta mt-4">Only managers can decide.</p>`}</article>`)}</div>`
        : emptyState('All clear', 'No approvals are waiting.')}</section>
      <section class="mt-4" aria-labelledby="hs"><h2 id="hs" class="mb-4">History</h2>
      ${history.length ? html`<div class="table-wrap"><table><caption class="sr-only">Approval history</caption><thead><tr><th scope="col">Action</th><th scope="col">Status</th><th scope="col">Decided by</th><th scope="col">When</th><th scope="col">Note</th><th scope="col"><span class="sr-only">Actions</span></th></tr></thead>
        <tbody>${history.map((a) => html`<tr><td>${action(a)}</td><td>${statusBadge(a.status)}</td><td>${a.decided_by || '—'}</td><td>${a.decided_at ? fmtDateTime(a.decided_at) : '—'}</td><td class="meta">${a.decision_note || ''}</td><td class="right">${a.status === 'approved' && can('manager') ? html`<button class="btn sm danger" data-revoke="${a.id}">Revoke</button>` : ''}</td></tr>`)}</tbody></table></div>` : html`<p class="muted">No decisions recorded yet.</p>`}</section>`);
    on(root, 'click', '[data-dec]', async (e, b) => {
      const approve = b.dataset.dec === 'approve', a = pending.find((x) => x.id === Number(b.dataset.id)); let note = '';
      const r = await openModal({ title: approve ? 'Approve this action?' : 'Reject this action?', labelledBy: 'dec-title', body: html`<p class="muted">${action(a)}</p>${a.kind === 'followup' ? html`<pre class="card flat pre">${a.payload.body}</pre>` : ''}${field('dec-note', 'Note (optional)', html`<input id="dec-note" class="input" maxlength="500">`)}`,
        actions: html`<button class="btn" data-close="cancel">Cancel</button><button class="btn ${approve ? 'primary' : 'danger solid'}" data-close="ok" autofocus>${approve ? 'Approve' : 'Reject'}</button>`, onMount: (box) => box.querySelector('#dec-note').addEventListener('input', (ev) => { note = ev.target.value; }) });
      if (r !== 'ok') return;
      await busy(b, async () => { try { await api.w.post(`/approvals/${a.id}/decide`, { approve, note }); toast(approve ? 'Approved. It will be sent after final checks.' : 'Rejected'); window.dispatchEvent(new Event('app:badges')); reload(); } catch (er) { toast(errMsg(er), 'error'); reload(); } });
    });
    on(root, 'click', '[data-revoke]', (e, b) => busy(b, async () => { try { await api.w.post(`/approvals/${b.dataset.revoke}/revoke`); toast('Approval revoked'); reload(); } catch (er) { toast(errMsg(er), 'error'); } }));
  },
};
