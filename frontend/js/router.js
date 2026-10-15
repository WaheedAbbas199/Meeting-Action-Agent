import { $, mount, html } from './dom.js';
import { errorState } from './ui.js';
import { isAbort } from './api.js';

const loaders = {
  login: () => import('./pages/login.js'), dashboard: () => import('./pages/dashboard.js'), meetings: () => import('./pages/meetings.js'),
  meeting: () => import('./pages/meeting.js'), tasks: () => import('./pages/tasks.js'), risks: () => import('./pages/risks.js'),
  decisions: () => import('./pages/decisions.js'), planner: () => import('./pages/planner.js'), memory: () => import('./pages/memory.js'),
  workload: () => import('./pages/workload.js'), followups: () => import('./pages/followups.js'), approvals: () => import('./pages/approvals.js'),
  analytics: () => import('./pages/analytics.js'), settings: () => import('./pages/settings.js'),
};
export const routes = [
  [/^\/login$/, 'login'], [/^\/dashboard$/, 'dashboard'], [/^\/meetings$/, 'meetings'], [/^\/meetings\/(\d+)$/, 'meeting'], [/^\/tasks$/, 'tasks'],
  [/^\/risks$/, 'risks'], [/^\/decisions$/, 'decisions'], [/^\/planner$/, 'planner'], [/^\/memory$/, 'memory'], [/^\/workload$/, 'workload'],
  [/^\/followups$/, 'followups'], [/^\/approvals$/, 'approvals'], [/^\/analytics$/, 'analytics'], [/^\/settings$/, 'settings'],
];
let ctl = null, cleanup = [], seq = 0;

export const path = () => (location.hash.slice(1).split('?')[0] || '/dashboard');
export const query = () => Object.fromEntries(new URLSearchParams(location.hash.split('?')[1] || ''));
export const go = (p) => { if (location.hash === `#${p}`) window.dispatchEvent(new HashChangeEvent('hashchange')); else location.hash = p; };

export function match(p) {
  for (const [re, name] of routes) { const m = p.match(re); if (m) return { name, params: m.slice(1) }; }
  return null;
}
/** Render the page into `root`. Navigating away aborts in-flight requests of the previous page (stale-request handling). */
export async function navigate(getRoot, onMeta) {
  const my = ++seq;
  // A fresh element per navigation drops every listener the previous page attached.
  let root = getRoot(); const fresh = root.cloneNode(false); root.replaceWith(fresh); root = fresh;
  ctl?.abort(); cleanup.forEach((f) => f()); cleanup = []; ctl = new AbortController();
  const m = match(path()) || { name: 'dashboard', params: [] };
  let page;
  try { page = (await loaders[m.name]()).default; } catch (e) { mount(root, errorState(e, false)); return; }
  if (my !== seq) return;
  onMeta?.(m.name, page);
  root.classList.remove('page-enter'); void root.offsetWidth; root.classList.add('page-enter');
  const reload = () => navigate(getRoot, onMeta);
  const ctx = { root, params: m.params, query: query(), signal: ctl.signal, reload, onCleanup: (f) => cleanup.push(f), isCurrent: () => my === seq };
  try { await page.render(ctx); }
  catch (e) {
    if (isAbort(e) || my !== seq) return;
    mount(root, html`<div class="page-head"><h1>${page.title || 'Error'}</h1></div>${errorState(e)}`);
    root.querySelector('[data-action="retry"]')?.addEventListener('click', reload);
  }
  if (my === seq) { const h = $('h1', root); if (h) { h.setAttribute('tabindex', '-1'); h.focus({ preventScroll: true }); } }
}
