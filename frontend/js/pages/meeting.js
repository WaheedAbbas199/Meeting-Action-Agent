import { html, mount, $, on, raw } from '../dom.js';
import { api, isAbort } from '../api.js';
import { can } from '../store.js';
import { pageHead } from '../components/common.js';
import { skeletonList, statusBadge, prio, dueLabel, confidence, evidenceBlock, fmtDate, toast, busy, errMsg, confirmDialog } from '../ui.js';
import { openTaskDrawer } from '../components/task-drawer.js';
import { icon } from '../icons.js';

const BUSY = ['queued', 'transcribing', 'extracting'];
const STAGES = [['queued', 'Queued'], ['transcribed', 'Transcribed (audio only)'], ['parsed', 'Transcript parsed'], ['extracted', 'Candidates extracted'], ['verified', 'Evidence verified'], ['ready_for_review', 'Ready for review']];

export default {
  title: 'Meeting',
  async render({ root, params, signal, reload, onCleanup, isCurrent }) {
    const id = params[0]; let tab = 'review';
    mount(root, html`${pageHead('Meeting', '', '', html`<a href="#/meetings">Meetings</a> / …`)}${skeletonList(4)}`);
    let m = await api.w.get(`/meetings/${id}`, { signal });
    let timer = null;
    const poll = () => {
      clearTimeout(timer);
      if (!BUSY.includes(m.status)) return;
      timer = setTimeout(async () => { try { m = await api.w.get(`/meetings/${id}`, { signal }); draw(); } catch (e) { if (!isAbort(e)) poll(); } }, 1500);
    };
    onCleanup(() => clearTimeout(timer));
    const stageList = () => { const log = new Set(m.stage_log.map((s) => s.stage)); const failed = m.status === 'failed'; let activeSet = false;
      return html`<div class="stages" role="list" aria-label="Processing stages">${STAGES.filter(([k]) => k !== 'transcribed' || m.source_type === 'audio').map(([k, label]) => { const isDone = log.has(k) || (k === 'ready_for_review' && ['review', 'completed'].includes(m.status)); const cls = isDone ? 'done' : (!activeSet && !failed ? (activeSet = true, 'active') : failed && !activeSet ? (activeSet = true, 'failed') : 'pending'); return html`<div class="stage ${cls}" role="listitem"><span class="dot">${isDone ? icon('check') : ''}</span><span>${label}</span><span class="sr-only">${cls}</span></div>`; })}</div>`; };
    function item(t) {
      const pending = t.review_state === 'pending';
      return html`<article class="item ${t.review_state} ${t.uncertain_fields.length && pending ? 'uncertain' : ''}" data-tid="${t.id}"><div class="row between"><strong>${t.title}</strong><span class="row">${prio(t.priority)} ${confidence(t.confidence)} ${!pending ? statusBadge(t.review_state) : ''}</span></div>
        <div class="row meta"><span>Owner: ${t.owner_name || html`<em>not identified</em>`}</span><span>·</span><span>${dueLabel(t)}</span></div>
        ${t.uncertain_fields.length && pending ? html`<div class="callout warn" role="note">Needs your input: ${t.uncertain_fields.map((f) => ({ owner: 'owner', due_date: 'deadline' }[f] || f)).join(' and ')} could not be determined reliably. Edit before approving.</div>` : ''}
        ${evidenceBlock(t.evidence_quote, t.segment_idx != null ? `Transcript segment ${t.segment_idx + 1}` : 'Spans multiple segments')}
        <div class="row"><button class="btn sm" data-edit="${t.id}">${pending ? 'Edit' : 'Details'}</button>${pending && can('manager') ? html`<button class="btn sm primary" data-ta="approve" data-id="${t.id}">Approve</button><button class="btn sm danger" data-ta="reject" data-id="${t.id}">Reject</button>` : ''}</div></article>`;
    }
    function dec(d) {
      const pending = d.review_state === 'pending';
      return html`<article class="item ${d.review_state}" data-did="${d.id}"><div class="row between"><strong>${d.kind === 'question' ? 'Open question' : 'Decision'}: ${d.text}</strong><span class="row">${confidence(d.confidence)} ${d.conflict_state === 'open' ? html`<span class="badge bad">Possible conflict</span>` : ''} ${!pending ? statusBadge(d.review_state) : ''}</span></div>
        ${d.conflict_state === 'open' ? html`<div class="callout warn">${d.conflict_reason} <a href="#/decisions">Resolve in Decisions</a></div>` : ''}
        ${evidenceBlock(d.evidence_quote, d.segment_idx != null ? `Transcript segment ${d.segment_idx + 1}` : '')}
        ${pending && can('manager') ? html`<div class="row"><button class="btn sm primary" data-da="approve" data-id="${d.id}">Keep</button><button class="btn sm danger" data-da="reject" data-id="${d.id}">Discard</button></div>` : ''}</article>`;
    }
    function draw() {
      const pendT = m.tasks.filter((t) => t.review_state === 'pending'), pendD = m.decisions.filter((d) => d.review_state === 'pending');
      const bulkable = pendT.filter((t) => !t.uncertain_fields.length);
      mount(root, html`${pageHead(m.title, `Held ${fmtDate(m.held_on)} · ${m.source_type === 'audio' ? `audio (${m.filename})` : 'transcript'}`, html`${statusBadge(m.status)}${m.status === 'failed' && can('member') ? html`<button class="btn" id="retry">${icon('refresh')} Retry processing</button>` : ''}`, html`<a href="#/meetings">Meetings</a> / ${m.title}`)}
        ${m.status === 'failed' ? html`<div class="callout bad" role="alert"><div><strong>Processing failed.</strong> ${m.error}</div></div>` : ''}
        ${m.warnings.map((w) => html`<div class="callout warn mb-4" role="note">${w}</div>`)}
        ${BUSY.includes(m.status) || m.status === 'failed' ? html`<section class="card mb-4" aria-live="polite"><div class="card-head"><h2>Processing</h2></div>${stageList()}<p class="meta mt-4">Stages reflect real backend progress.</p></section>` : ''}
        ${['review', 'completed'].includes(m.status) ? html`
          <div class="tabs" role="tablist"><button class="tab" role="tab" data-tab="review" aria-selected="${tab === 'review'}">Review (${pendT.length + pendD.length} pending)</button><button class="tab" role="tab" data-tab="transcript" aria-selected="${tab === 'transcript'}">Transcript</button></div>
          ${tab === 'review' ? html`<div class="stack">
            ${m.summary ? html`<section class="card flat"><h2>Summary</h2><p class="muted mt-2">${m.summary}</p></section>` : ''}
            ${!can('manager') && (pendT.length || pendD.length) ? html`<div class="callout info">A manager needs to approve these items. You can still correct details before they do.</div>` : ''}
            <section class="stack" aria-labelledby="tk-h"><div class="row between"><h2 id="tk-h">Tasks and commitments (${m.tasks.length})</h2>${can('manager') && bulkable.length ? html`<button class="btn sm" id="bulk">Approve ${bulkable.length} complete item${bulkable.length > 1 ? 's' : ''}</button>` : ''}</div>
              ${m.tasks.length ? m.tasks.map(item) : html`<p class="muted">No tasks with supporting evidence were found.</p>`}</section>
            <section class="stack" aria-labelledby="dc-h"><h2 id="dc-h">Decisions and open questions (${m.decisions.length})</h2>${m.decisions.length ? m.decisions.map(dec) : html`<p class="muted">None found.</p>`}</section></div>`
          : html`<section class="card"><div class="transcript" tabindex="0" aria-label="Transcript">${m.segments.map((s) => html`<div class="seg-line" id="seg-${s.idx}"><span class="ts">${s.timestamp || `#${s.idx + 1}`}</span><span class="sp">${s.speaker || '—'}</span><span>${s.text}</span></div>`)}</div></section>`}` : ''}`);
      poll();
    }
    draw();
    on(root, 'click', '[data-tab]', (e, b) => { tab = b.dataset.tab; draw(); });
    on(root, 'click', '[data-edit]', (e, b) => openTaskDrawer(Number(b.dataset.edit), async () => { m = await api.w.get(`/meetings/${id}`); draw(); }));
    const review = async (btn, body, okMsg) => busy(btn, async () => { try { m = await api.w.post(`/meetings/${id}/review`, body); toast(okMsg); draw(); } catch (er) { toast(errMsg(er), 'error'); } });
    on(root, 'click', '[data-ta]', (e, b) => review(b, { tasks: [{ id: Number(b.dataset.id), action: b.dataset.ta }] }, b.dataset.ta === 'approve' ? 'Task approved' : 'Task rejected'));
    on(root, 'click', '[data-da]', (e, b) => review(b, { decisions: [{ id: Number(b.dataset.id), action: b.dataset.da }] }, b.dataset.da === 'approve' ? 'Item kept' : 'Item discarded'));
    on(root, 'click', '#bulk', async (e, b) => {
      const ids = m.tasks.filter((t) => t.review_state === 'pending' && !t.uncertain_fields.length).map((t) => t.id);
      if (await confirmDialog({ title: `Approve ${ids.length} tasks?`, message: 'Only items with an identified owner and deadline are included. They become active tasks.', confirmLabel: 'Approve' })) review(b, { tasks: ids.map((i) => ({ id: i, action: 'approve' })) }, `${ids.length} tasks approved`);
    });
    on(root, 'click', '#retry', (e, b) => busy(b, async () => { try { await api.w.post(`/meetings/${id}/retry`); toast('Retry started'); reload(); } catch (er) { toast(errMsg(er), 'error'); } }));
  },
};
