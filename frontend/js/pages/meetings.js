import { html, mount, $, on } from '../dom.js';
import { api } from '../api.js';
import { can } from '../store.js';
import { go } from '../router.js';
import { pageHead, field, formData, tzList, localTz, todayIso, options } from '../components/common.js';
import { skeletonList, statusBadge, fmtDate, emptyState, toast, busy, errMsg, openModal } from '../ui.js';
import { icon } from '../icons.js';

function newMeetingModal() {
  let tab = 'paste', dirty = false;
  const body = () => html`<div class="seg" role="group" aria-label="Source"><button type="button" data-tab="paste" aria-pressed="${tab === 'paste'}">Paste transcript</button><button type="button" data-tab="file" aria-pressed="${tab === 'file'}">Upload file</button></div>
    <form id="mform" class="stack" novalidate>
      ${field('m-title', 'Meeting title', html`<input id="m-title" name="title" class="input" maxlength="200" required autofocus placeholder="e.g. Q4 planning sync">`)}
      <div class="grid cols-2">${field('m-date', 'Held on', html`<input id="m-date" name="held_on" type="date" class="input" value="${todayIso()}" required>`, 'Relative deadlines like “by Friday” are resolved from this date.')}
      ${field('m-tz', 'Timezone', html`<select id="m-tz" name="timezone" class="select">${options(tzList().map((z) => [z, z]), localTz())}</select>`)}</div>
      ${tab === 'paste' ? field('m-text', 'Transcript', html`<textarea id="m-text" name="transcript_text" class="textarea" rows="9" placeholder="[00:00:05] Maya: Alice, can you prepare the budget report by Friday?&#10;Alice: Yes, I'll have it ready."></textarea>`, 'Format: “Speaker: text”, optional [hh:mm:ss] timestamps. VTT and SRT also work.')
        : field('m-file', 'Transcript or audio file', html`<input id="m-file" name="file" type="file" class="input" accept=".txt,.vtt,.srt,.md,.mp3,.wav,.m4a,.ogg,.flac,.aac">`, 'Text transcripts (.txt, .vtt, .srt) always work. Audio needs a speech-to-text provider configured by an admin.')}
      <p class="error-text" id="m-err" role="alert"></p>
    </form>`;
  return openModal({ title: 'New meeting', wide: true, body: body(), isDirty: () => dirty,
    actions: html`<button class="btn" data-close="cancel">Cancel</button><button class="btn primary" id="m-submit">Process meeting</button>`,
    onMount: (box, finish) => {
      const redraw = () => { const keep = formData($('#mform', box)); mount($('.modal-body', box), body()); Object.entries(keep).forEach(([k, v]) => { const el = box.querySelector(`[name="${k}"]`); if (el && el.type !== 'file') el.value = v; }); };
      box.addEventListener('input', () => { dirty = true; });
      on(box, 'click', '[data-tab]', (e, b) => { tab = b.dataset.tab; redraw(); });
      $('#m-submit', box).addEventListener('click', async (e) => {
        const f = $('#mform', box), d = formData(f), err = $('#m-err', box); err.textContent = '';
        if (!d.title?.trim()) { err.textContent = 'Give the meeting a title.'; $('#m-title', box).setAttribute('aria-invalid', 'true'); $('#m-title', box).focus(); return; }
        await busy(e.currentTarget, async () => {
          try {
            let r;
            if (tab === 'paste') { if ((d.transcript_text || '').trim().length < 10) { err.textContent = 'Paste the transcript text (at least a sentence).'; return; } r = await api.w.post('/meetings', { title: d.title, held_on: d.held_on, timezone: d.timezone, transcript_text: d.transcript_text }); }
            else { const file = $('#m-file', box).files[0]; if (!file) { err.textContent = 'Choose a file to upload.'; return; } const fd = new FormData(); fd.append('title', d.title); fd.append('timezone', d.timezone); fd.append('held_on', d.held_on); fd.append('file', file); r = await api.w.upload('/meetings/upload', fd); }
            dirty = false; finish(r);
          } catch (er) { err.textContent = errMsg(er); }
        });
      });
    } });
}

export default {
  title: 'Meetings',
  async render({ root, signal, reload, query, isCurrent }) {
    mount(root, html`${pageHead('Meetings', 'Upload or paste a transcript. Review what the AI found before anything becomes a task.')}${skeletonList()}`);
    const list = await api.w.get('/meetings', { signal });
    if (!isCurrent()) return;
    mount(root, html`${pageHead('Meetings', 'Upload or paste a transcript. Review what the AI found before anything becomes a task.', can('member') ? html`<button class="btn primary" id="new-m">${icon('plus')} New meeting</button>` : '')}
      ${list.length ? html`<div class="table-wrap"><table><caption class="sr-only">Meetings</caption><thead><tr><th scope="col">Meeting</th><th scope="col">Held on</th><th scope="col">Source</th><th scope="col">Status</th><th scope="col">To review</th></tr></thead>
        <tbody>${list.map((m) => html`<tr class="clickable" data-go="${m.id}"><td><a href="#/meetings/${m.id}"><strong>${m.title}</strong></a>${m.warnings.length ? html` <span class="badge warn plain" title="${m.warnings[0]}">Warning</span>` : ''}</td><td>${fmtDate(m.held_on)}</td><td>${m.source_type === 'audio' ? 'Audio' : 'Transcript'}</td><td>${statusBadge(m.status)}</td><td>${m.pending_review || '—'}</td></tr>`)}</tbody></table></div>`
        : emptyState('No meetings yet', 'Add a transcript and the agent will propose tasks and decisions with evidence for your review.', can('member') ? html`<button class="btn primary" id="new-m2">Add your first meeting</button>` : '')}`);
    const open = async () => { const r = await newMeetingModal(); if (r?.id) { toast('Meeting submitted. Processing has started.'); go(`/meetings/${r.id}`); } };
    $('#new-m', root)?.addEventListener('click', open); $('#new-m2', root)?.addEventListener('click', open);
    on(root, 'click', '[data-go]', (e, tr) => { if (!e.target.closest('a')) go(`/meetings/${tr.dataset.go}`); });
    if (query.new && can('member')) open();
  },
};
