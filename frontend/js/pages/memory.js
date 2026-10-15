import { html, mount, $ } from '../dom.js';
import { api, isAbort } from '../api.js';
import { pageHead } from '../components/common.js';
import { busy, errMsg, toast, fmtDate } from '../ui.js';
import { icon } from '../icons.js';

export default {
  title: 'Meeting memory',
  async render({ root, signal }) {
    mount(root, html`${pageHead('Meeting memory', 'Ask about anything discussed in meetings you can access. Answers cite transcript passages.')}
      <form id="ask" class="card stack" novalidate><div class="field"><label for="q">Your question</label><div class="row"><input id="q" class="input grow" maxlength="500" placeholder="e.g. What did we decide about the vendor contract?" autofocus><button class="btn primary" type="submit">${icon('search')} Ask</button></div>
      <span class="help">Retrieval uses local lexical matching. Rephrase with words used in the meeting if nothing is found.</span></div></form><div id="out" class="mt-4" aria-live="polite"></div>`);
    $('#ask', root).addEventListener('submit', async (e) => {
      e.preventDefault(); const q = $('#q', root).value.trim(); if (q.length < 3) return toast('Ask a question of at least a few words.', 'error');
      await busy(e.submitter, async () => {
        try {
          const r = await api.w.post('/memory/ask', { question: q }, { signal });
          mount($('#out', root), r.evidence_found ? html`<section class="stack"><div class="card"><h2>Answer</h2><p class="mt-2">${r.answer}</p></div><h3>Sources (${r.citations.length})</h3>
            ${r.citations.map((c) => html`<article class="card"><div class="row between"><a href="#/meetings/${c.meeting_id}"><strong>${c.meeting_title}</strong></a><span class="meta">${fmtDate(c.held_on)} · ${c.timestamp || `segment ${c.segment_idx + 1}`} · match ${Math.round(c.score * 100)}%</span></div><blockquote class="evidence mt-2">“${c.text}”<cite>${c.speaker || 'Unknown speaker'}</cite></blockquote></article>`)}</section>`
            : html`<div class="callout info" role="status"><div><strong>No supporting evidence found.</strong> ${r.answer}</div></div>`);
        } catch (er) { if (!isAbort(er)) mount($('#out', root), html`<div class="callout bad" role="alert">${errMsg(er)}</div>`); }
      });
    });
  },
};
