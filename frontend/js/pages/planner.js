import { html, mount, $, on, raw } from '../dom.js';
import { api } from '../api.js';
import { can } from '../store.js';
import { pageHead, field } from '../components/common.js';
import { skeletonList, statusBadge, emptyState, toast, busy, errMsg, fmtDateTime, confirmDialog } from '../ui.js';
import { icon } from '../icons.js';

const KIND = { overdue: 'Overdue', blocked: 'Blocked', due_soon: 'Due soon', conflict: 'Conflict', question: 'Open question', custom: 'Custom' };

export default {
  title: 'Next meeting',
  async render({ root, signal, reload, isCurrent, query }) {
    mount(root, html`${pageHead('Next meeting planner', 'Agendas are drafted from open commitments, blockers, conflicts and unanswered questions.')}${skeletonList()}`);
    const list = await api.w.get('/agendas', { signal });
    if (!isCurrent()) return;
    let cur = list.find((a) => String(a.id) === query.id) || list[0] || null, dirty = false;
    const draw = () => {
      mount(root, html`${pageHead('Next meeting planner', 'Agendas are drafted from open commitments, blockers, conflicts and unanswered questions.', can('member') ? html`<button class="btn primary" id="gen">${icon('plus')} Draft new agenda</button>` : '')}
        ${!cur ? emptyState('No agenda yet', 'Generate a draft from your current tasks and decisions. Every item says why it is there.') : html`
        <div class="row mb-4"><label class="sr-only" for="ag-sel">Choose agenda</label><select id="ag-sel" class="select sel-sm">${list.map((a) => html`<option value="${a.id}" ${a.id === cur.id ? raw('selected') : ''}>${a.title} (rev ${a.revision})</option>`)}</select>${statusBadge(cur.status === 'draft' ? 'draft_agenda' : 'approved')}<span class="meta">Revision ${cur.revision}</span></div>
        <section class="card"><form id="agf" class="stack" novalidate>${field('ag-title', 'Agenda title', html`<input id="ag-title" class="input" value="${cur.title}" maxlength="200" ${can('member') ? '' : raw('disabled')}>`)}
          <ol class="stack list-reset" id="items">${cur.items.map((it, i) => html`<li class="item" data-i="${i}"><div class="row between"><div class="row"><span class="badge brand plain">${KIND[it.kind] || it.kind}</span><strong>${it.title}</strong></div>
            ${can('member') ? html`<div class="row"><button type="button" class="btn ghost sm" data-mv="-1" aria-label="Move item up">↑</button><button type="button" class="btn ghost sm" data-mv="1" aria-label="Move item down">↓</button><button type="button" class="btn ghost sm" data-rm aria-label="Remove item">${icon('x')}</button></div>` : ''}</div>
            <p class="muted">Why: ${it.reason || 'Added manually'}</p><label class="row meta">Minutes <input type="number" min="1" max="240" class="input w-sm" data-min value="${it.minutes}" aria-label="Minutes for ${it.title}" ${can('member') ? '' : raw('disabled')}></label></li>`)}</ol>
          ${can('member') ? html`<div class="row"><input id="custom" class="input w-md" placeholder="Add a custom topic" aria-label="Custom agenda topic"><button type="button" class="btn" id="add">Add topic</button></div>` : ''}
          <div class="row between"><span class="meta">${cur.items.reduce((s, i) => s + Number(i.minutes || 0), 0)} minutes planned</span><span class="row">${can('member') ? html`<button class="btn" type="submit">Save revision</button>` : ''}${can('manager') ? html`<button type="button" class="btn primary" id="appr">Approve agenda</button>` : ''}</span></div></form></section>
        ${cur.status === 'approved' && can('member') ? html`<section class="card mt-4"><h2>Calendar</h2><p class="muted mt-2">Creating a calendar event needs a manager’s approval first.</p><div class="row mt-4"><label class="sr-only" for="cal-start">Start</label><input id="cal-start" type="datetime-local" class="input w-sm"><button class="btn" id="cal">Request calendar event</button></div></section>` : ''}`}`);
      $('#gen', root)?.addEventListener('click', async (e) => busy(e.currentTarget, async () => { try { const a = await api.w.post('/agendas', { title: `Agenda ${new Date().toLocaleDateString()}` }); toast('Agenda drafted from current data'); location.hash = `/planner?id=${a.id}`; reload(); } catch (er) { toast(errMsg(er), 'error'); } }));
    };
    const collect = () => {
      const items = [...root.querySelectorAll('#items > li')].map((li) => { const base = cur.items[Number(li.dataset.i)]; return { ...base, minutes: Number(li.querySelector('[data-min]').value) || base.minutes }; });
      return items;
    };
    draw();
    root.addEventListener('change', (e) => { if (e.target.id === 'ag-sel') { cur = list.find((a) => a.id === Number(e.target.value)); draw(); } });
    root.addEventListener('input', () => { dirty = true; });
    on(root, 'click', '[data-rm]', (e, b) => { cur = { ...cur, items: collect().filter((_, i) => i !== Number(b.closest('li').dataset.i)) }; draw(); dirty = true; });
    on(root, 'click', '[data-mv]', (e, b) => { const items = collect(), i = Number(b.closest('li').dataset.i), j = i + Number(b.dataset.mv); if (j < 0 || j >= items.length) return; [items[i], items[j]] = [items[j], items[i]]; cur = { ...cur, items }; draw(); dirty = true; });
    on(root, 'click', '#add', () => { const v = $('#custom', root).value.trim(); if (!v) return toast('Type a topic first.', 'error'); cur = { ...cur, items: [...collect(), { id: 'new', kind: 'custom', title: v, reason: '', ref: {}, minutes: 5 }] }; draw(); dirty = true; });
    root.addEventListener('submit', async (e) => {
      e.preventDefault(); const title = $('#ag-title', root).value.trim(); if (!title) return toast('The agenda needs a title.', 'error');
      await busy(e.submitter, async () => { try { const a = await api.w.put(`/agendas/${cur.id}`, { title, items: collect() }); Object.assign(list.find((x) => x.id === cur.id), a); cur = a; dirty = false; toast(`Saved as revision ${a.revision}`); draw(); } catch (er) { toast(errMsg(er), 'error'); } });
    });
    on(root, 'click', '#appr', async (e, b) => {
      if (dirty) return toast('Save your changes before approving.', 'error');
      if (!(await confirmDialog({ title: 'Approve this agenda?', message: `Revision ${cur.revision} will be marked approved.`, confirmLabel: 'Approve' }))) return;
      await busy(b, async () => { try { const a = await api.w.post(`/agendas/${cur.id}/approve`); Object.assign(list.find((x) => x.id === cur.id), a); cur = a; toast('Agenda approved'); draw(); } catch (er) { toast(errMsg(er), 'error'); } });
    });
    on(root, 'click', '#cal', async (e, b) => {
      const v = $('#cal-start', root).value; if (!v) return toast('Pick a start time.', 'error');
      await busy(b, async () => { try { await api.w.post(`/agendas/${cur.id}/calendar`, { start: new Date(v).toISOString() }); toast('Sent for approval. See the Approvals page.'); } catch (er) { toast(errMsg(er), 'error'); } });
    });
  },
};
