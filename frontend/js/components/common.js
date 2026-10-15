import { html, raw } from '../dom.js';

export const pageHead = (title, sub = '', actions = '', crumbs = '') => html`<div class="page-head"><div>${crumbs ? html`<nav class="breadcrumbs" aria-label="Breadcrumb">${crumbs}</nav>` : ''}<h1>${title}</h1>${sub ? html`<p>${sub}</p>` : ''}</div><div class="row">${actions}</div></div>`;
export const field = (id, label, control, help = '') => html`<div class="field"><label for="${id}">${label}</label>${control}${help ? html`<span class="help">${help}</span>` : ''}</div>`;
export const options = (list, selected) => list.map(([v, l]) => html`<option value="${v}" ${String(v) === String(selected) ? raw('selected') : ''}>${l}</option>`);
export const STATUS_OPTS = [['', 'All statuses'], ['open', 'Open'], ['in_progress', 'In progress'], ['blocked', 'Blocked'], ['done', 'Done']];
export const PRIO_OPTS = [['urgent', 'Urgent'], ['high', 'High'], ['medium', 'Medium'], ['low', 'Low']];
export const formData = (form) => Object.fromEntries(new FormData(form).entries());
export const tzList = () => { try { return Intl.supportedValuesOf('timeZone'); } catch { return ['UTC']; } };
export const localTz = () => Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
export const todayIso = () => { const d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 10); };
