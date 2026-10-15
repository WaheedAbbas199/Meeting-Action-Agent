import { html, mount, $, $$, hydrate } from './dom.js';
import { icon } from './icons.js';

// ---------- formatting ----------
const dfmt = new Intl.DateTimeFormat(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
const tfmt = new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
export const fmtDate = (iso) => (iso ? dfmt.format(new Date(iso.length === 10 ? `${iso}T00:00:00` : iso)) : '—');
export const fmtDateTime = (iso) => (iso ? tfmt.format(new Date(iso)) : '—');
export function relTime(iso) {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return 'just now'; if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`; return `${Math.floor(s / 86400)} d ago`;
}
export const pct = (v) => (v == null ? '—' : `${Math.round(v * 100)}%`);
export const initials = (n = '') => n.split(/\s+/).map((p) => p[0]).slice(0, 2).join('').toUpperCase();
export function dueLabel(t) {
  if (!t.due_date) return html`<span class="muted">No deadline</span>`;
  if (t.overdue) return html`<span class="due overdue">${fmtDate(t.due_date)} · ${Math.abs(t.days_until_due)}d overdue</span>`;
  if (t.days_until_due != null && t.days_until_due <= 2 && !['done', 'rejected'].includes(t.status)) return html`<span class="due soon">${fmtDate(t.due_date)} · ${t.days_until_due === 0 ? 'today' : `in ${t.days_until_due}d`}</span>`;
  return html`<span class="due">${fmtDate(t.due_date)}</span>`;
}

// ---------- badges ----------
const STATUS = { open: ['Open', 'info'], in_progress: ['In progress', 'brand'], blocked: ['Blocked', 'bad'], done: ['Done', 'good'], proposed: ['Proposed', 'warn'], rejected: ['Rejected', ''],
  pending: ['Pending', 'warn'], approved: ['Approved', 'good'], expired: ['Expired', ''], revoked: ['Revoked', ''], executed: ['Executed', 'good'], failed: ['Failed', 'bad'],
  draft: ['Draft', ''], pending_approval: ['Awaiting approval', 'warn'], scheduled: ['Scheduled', 'info'], sending: ['Sending', 'info'], sent: ['Sent', 'good'],
  confirmed: ['Confirmed', 'good'], dismissed: ['Dismissed', ''], superseded: ['Superseded', ''], queued: ['Queued', 'info'], transcribing: ['Transcribing', 'brand'],
  extracting: ['Extracting', 'brand'], review: ['Needs review', 'warn'], completed: ['Completed', 'good'], draft_agenda: ['Draft', ''] };
export const statusBadge = (s) => { const [l, c] = STATUS[s] || [s, '']; return html`<span class="badge ${c} ${['transcribing', 'extracting', 'sending', 'queued'].includes(s) ? 'live' : ''}">${l}</span>`; };
export const prio = (p) => html`<span class="prio ${p}">${p}</span>`;
export function confidence(c) {
  const cls = c < 0.5 ? 'low' : c < 0.75 ? 'mid' : '';
  return html`<span class="conf ${cls}" title="Model confidence"><span class="conf-bar" aria-hidden="true"><i data-scale="${c}"></i></span><span>${Math.round(c * 100)}%<span class="sr-only"> confidence</span></span></span>`;
}
export const evidenceBlock = (quote, cite = '') => (quote ? html`<blockquote class="evidence">“${quote}”${cite ? html`<cite>${cite}</cite>` : ''}</blockquote>` : '');

// ---------- states ----------
export const skeletonCards = (n = 4) => html`<div class="grid cols-4" aria-busy="true" aria-label="Loading">${Array.from({ length: n }, () => html`<div class="skeleton kpi-s"></div>`)}</div>
  <div class="skeleton block mt-4"></div>`;
export const skeletonList = (n = 5) => html`<div class="stack-sm" aria-busy="true" aria-label="Loading">${Array.from({ length: n }, () => html`<div class="skeleton row-s"></div>`)}</div>`;
export const emptyState = (title, text, action = '') => html`<div class="state">${icon('inbox', 'glyph')}<h3>${title}</h3><p>${text}</p>${action}</div>`;
export const errorState = (err, retry = true) => html`<div class="state error" role="alert"><h3>We couldn’t load this</h3><p>${err?.message || 'Unknown error'}</p>${retry ? html`<button class="btn" data-action="retry">${icon('refresh')} Try again</button>` : ''}</div>`;

// ---------- toasts (announced via live regions; success only after the server confirmed) ----------
export function toast(message, type = 'success', ms = 4500) {
  const host = $('#toasts'); if (!host) return;
  const el = document.createElement('div');
  el.className = `toast ${type}`; el.setAttribute('role', type === 'error' ? 'alert' : 'status');
  const msg = document.createElement('span'); msg.textContent = message;
  const x = document.createElement('button'); x.type = 'button'; x.setAttribute('aria-label', 'Dismiss notification'); x.textContent = '×';
  const close = () => el.remove(); x.addEventListener('click', close); el.append(msg, x); host.append(el);
  if (ms) setTimeout(close, type === 'error' ? Math.max(ms, 7000) : ms);
}

// ---------- focus trap + overlays ----------
const FOCUSABLE = 'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';
function trap(container, onEscape) {
  const prev = document.activeElement;
  const key = (e) => {
    if (e.key === 'Escape') { e.stopPropagation(); onEscape(); return; }
    if (e.key !== 'Tab') return;
    const f = $$(FOCUSABLE, container).filter((n) => n.offsetParent !== null || n === document.activeElement);
    if (!f.length) { e.preventDefault(); return; }
    const first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  };
  document.addEventListener('keydown', key, true);
  return () => { document.removeEventListener('keydown', key, true); if (prev && document.contains(prev)) prev.focus(); };
}
function animateOut(wrap, done) {
  wrap.classList.add('closing'); const t = setTimeout(done, 140); wrap.addEventListener('animationend', () => { clearTimeout(t); done(); }, { once: true });
}
let lockCount = 0;
const lock = (on) => { lockCount += on ? 1 : -1; document.body.style.overflow = lockCount > 0 ? 'hidden' : ''; };

/** Generic modal. `isDirty` guards against losing unsaved input. Resolves with the value passed to close(). */
export function openModal({ title, body, actions = '', wide = false, isDirty = null, onMount = null, labelledBy = 'modal-title' }) {
  return new Promise((resolve) => {
    const wrap = document.createElement('div'); wrap.className = 'overlay';
    const box = document.createElement('div'); box.className = `modal ${wide ? 'wide' : ''}`; box.setAttribute('role', 'dialog'); box.setAttribute('aria-modal', 'true'); box.setAttribute('aria-labelledby', labelledBy);
    mount(box, html`<h2 id="${labelledBy}">${title}</h2><div class="modal-body stack">${body}</div><div class="modal-actions">${actions}</div>`);
    wrap.append(box); document.body.append(wrap); lock(true);
    let closed = false;
    const finish = (v) => { if (closed) return; closed = true; release(); lock(false); animateOut(wrap, () => wrap.remove()); resolve(v); };
    const requestClose = async () => { if (isDirty?.() && !(await confirmDialog({ title: 'Discard changes?', message: 'You have unsaved changes that will be lost.', confirmLabel: 'Discard', danger: true }))) return; finish(undefined); };
    const release = trap(box, requestClose);
    wrap.addEventListener('mousedown', (e) => { if (e.target === wrap) requestClose(); });
    box.addEventListener('click', (e) => { const b = e.target.closest('[data-close]'); if (b) finish(b.dataset.close === 'cancel' ? undefined : b.dataset.close); });
    (box.querySelector('[autofocus]') || box.querySelector(FOCUSABLE))?.focus();
    onMount?.(box, finish);
  });
}
export async function confirmDialog({ title, message, confirmLabel = 'Confirm', danger = false }) {
  const r = await openModal({ title, labelledBy: 'confirm-title', body: html`<p class="muted">${message}</p>`,
    actions: html`<button class="btn" data-close="cancel">Cancel</button><button class="btn ${danger ? 'danger solid' : 'primary'}" data-close="yes" autofocus>${confirmLabel}</button>` });
  return r === 'yes';
}
/** Right-side drawer with the same focus handling as modals. */
export function openDrawer({ title, subtitle = '', isDirty = null }) {
  const wrap = document.createElement('div'); wrap.className = 'drawer-wrap';
  const d = document.createElement('aside'); d.className = 'drawer'; d.setAttribute('role', 'dialog'); d.setAttribute('aria-modal', 'true'); d.setAttribute('aria-labelledby', 'drawer-title');
  mount(d, html`<div class="drawer-head"><div><h2 id="drawer-title">${title}</h2>${subtitle ? html`<p class="meta">${subtitle}</p>` : ''}</div><button class="btn ghost icon" data-drawer-close aria-label="Close panel">${icon('x')}</button></div><div class="drawer-body stack"></div>`);
  wrap.append(d); document.body.append(wrap); lock(true);
  const body = $('.drawer-body', d); let closed = false;
  const close = () => { if (closed) return; closed = true; release(); lock(false); animateOut(wrap, () => wrap.remove()); api.onClose?.(); };
  const requestClose = async () => { if (isDirty?.() && !(await confirmDialog({ title: 'Discard changes?', message: 'You have unsaved changes that will be lost.', confirmLabel: 'Discard', danger: true }))) return; close(); };
  const release = trap(d, requestClose);
  wrap.addEventListener('mousedown', (e) => { if (e.target === wrap) requestClose(); });
  d.addEventListener('click', (e) => { if (e.target.closest('[data-drawer-close]')) requestClose(); });
  const api = { el: d, body, close, setContent: (safe) => { mount(body, safe); }, onClose: null };
  $('[data-drawer-close]', d).focus();
  return api;
}

/** Disable a button and show a spinner while an async action runs. The action must resolve only after server confirmation. */
export async function busy(btn, fn) {
  if (!btn || btn.disabled) return;
  const old = btn.innerHTML; btn.disabled = true; btn.setAttribute('aria-busy', 'true'); btn.innerHTML = `<span class="spinner" aria-hidden="true"></span>${btn.textContent.trim() ? ' ' + btn.textContent.trim() : ''}`;
  try { return await fn(); } finally { if (btn.isConnected) { btn.disabled = false; btn.removeAttribute('aria-busy'); btn.innerHTML = old; } }
}
export const errMsg = (e) => e?.message || 'Something went wrong';
export { hydrate };
