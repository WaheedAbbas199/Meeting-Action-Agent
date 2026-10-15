import { html, mount, on } from '../dom.js';
import { api } from '../api.js';
import { can } from '../store.js';
import { pageHead } from '../components/common.js';
import { skeletonList, statusBadge, confidence, evidenceBlock, emptyState, toast, busy, errMsg, confirmDialog, fmtDate } from '../ui.js';

export default {
  title: 'Decisions',
  async render({ root, signal, reload, isCurrent }) {
    let tab = 'conflicts';
    mount(root, html`${pageHead('Decisions', 'Decisions and open questions across meetings. Conflicts always need a human call.')}${skeletonList()}`);
    const all = await api.w.get('/decisions', { signal });
    if (!isCurrent()) return;
    const conflicts = all.filter((d) => d.conflict_state === 'open');
    if (!conflicts.length) tab = 'decisions';
    const cards = {};
    await Promise.all(conflicts.map(async (c) => { cards[c.id] = await api.w.get(`/decisions/${c.id}`, { signal }); }));
    const side = (label, d) => html`<div class="card flat"><span class="label">${label}</span><p class="mt-2"><strong>${d.text}</strong></p><p class="meta">${d.meeting_title || 'Meeting'} · ${statusBadge(d.status)}</p>${evidenceBlock(d.evidence_quote, d.meeting_title)}</div>`;
    const dcard = (d) => html`<article class="card"><div class="row between"><strong>${d.text}</strong><span class="row">${confidence(d.confidence)}${statusBadge(d.status)}${d.review_state === 'pending' ? html`<span class="badge warn plain">Awaiting meeting review</span>` : ''}</span></div>
      <p class="meta mt-2">${d.meeting_title ? html`<a href="#/meetings/${d.meeting_id}">${d.meeting_title}</a>` : ''} · ${fmtDate(d.created_at)}</p>${evidenceBlock(d.evidence_quote)}
      ${can('manager') && d.review_state === 'approved' && d.kind === 'decision' && d.status === 'proposed' ? html`<div class="row mt-4"><button class="btn sm primary" data-st="confirmed" data-id="${d.id}">Confirm decision</button><button class="btn sm" data-st="dismissed" data-id="${d.id}">Dismiss</button></div>` : ''}</article>`;
    const draw = () => {
      const list = all.filter((d) => (tab === 'decisions' ? d.kind === 'decision' : tab === 'questions' ? d.kind === 'question' : false));
      mount(root, html`${pageHead('Decisions', 'Decisions and open questions across meetings. Conflicts always need a human call.')}
        <div class="tabs" role="tablist"><button class="tab" role="tab" data-tab="conflicts" aria-selected="${tab === 'conflicts'}">Conflicts (${conflicts.length})</button><button class="tab" role="tab" data-tab="decisions" aria-selected="${tab === 'decisions'}">Decisions</button><button class="tab" role="tab" data-tab="questions" aria-selected="${tab === 'questions'}">Open questions</button></div>
        ${tab === 'conflicts' ? (conflicts.length ? html`<div class="stack stagger">${conflicts.map((c) => { const v = cards[c.id]; return html`<article class="card"><div class="callout warn mb-4" role="note"><div><strong>Possible conflict.</strong> ${c.conflict_reason}</div></div>
          <div class="grid cols-2">${v.conflicting ? side('Earlier decision', v.conflicting) : ''}${side('New statement', v)}</div>
          ${can('manager') ? html`<div class="row mt-4"><button class="btn primary" data-res="confirm" data-id="${c.id}">The new statement replaces the earlier one</button><button class="btn" data-res="dismiss" data-id="${c.id}">Not a conflict</button></div><p class="meta mt-2">The earlier decision is kept as history.</p>` : html`<p class="meta mt-4">Only managers can resolve conflicts.</p>`}</article>`; })}</div>` : emptyState('No conflicts', 'New decisions are compared with earlier ones. Anything that looks contradictory appears here.'))
        : list.length ? html`<div class="stack stagger">${list.map(dcard)}</div>` : emptyState('Nothing here yet', 'Items appear after a meeting is processed.')}`);
    };
    draw();
    on(root, 'click', '[data-tab]', (e, b) => { tab = b.dataset.tab; draw(); });
    on(root, 'click', '[data-res]', async (e, b) => {
      const confirm = b.dataset.res === 'confirm';
      if (!(await confirmDialog({ title: confirm ? 'Replace the earlier decision?' : 'Mark as not a conflict?', message: confirm ? 'The new statement becomes the current decision. The earlier one is kept as superseded history.' : 'Both statements stay as recorded.', confirmLabel: confirm ? 'Replace' : 'Dismiss conflict' }))) return;
      await busy(b, async () => { try { await api.w.post(`/decisions/${b.dataset.id}/resolve`, { action: b.dataset.res }); toast('Conflict resolved'); reload(); } catch (er) { toast(errMsg(er), 'error'); } });
    });
    on(root, 'click', '[data-st]', (e, b) => busy(b, async () => { try { await api.w.post(`/decisions/${b.dataset.id}/status`, { status: b.dataset.st }); toast(`Decision ${b.dataset.st}`); reload(); } catch (er) { toast(errMsg(er), 'error'); } }));
  },
};
