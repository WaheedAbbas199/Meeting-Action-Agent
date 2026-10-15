import { html, mount, $, $$, on, debounce } from './dom.js';
import { api, isAbort } from './api.js';
import { store, setSession, clearSession, theme, sidebar, can, role } from './store.js';
import { navigate, go, path, match } from './router.js';
import { icon } from './icons.js';
import { initials, relTime, toast, errorState } from './ui.js';

theme.set(theme.get());
const app = $('#app');
const NAV = [
  ['dashboard', 'Dashboard', 'home'], ['meetings', 'Meetings', 'mic'], ['tasks', 'Tasks', 'tasks'], ['risks', 'Risks & blockers', 'alert'], ['decisions', 'Decisions', 'scale'],
  ['planner', 'Next meeting', 'calendar'], ['memory', 'Meeting memory', 'brain'], ['workload', 'Team workload', 'users'], ['followups', 'Follow-ups', 'mail'],
  ['approvals', 'Approvals', 'shield'], ['analytics', 'Analytics', 'chart'], ['settings', 'Settings', 'settings'],
];
const TITLES = Object.fromEntries(NAV.map(([k, l]) => [k, l]));
let shellEl = null, removeListeners = [];

function announce(text) { const a = $('#route-announcer'); if (a) a.textContent = text; }

async function boot() {
  if (store.token) {
    try { setSession(await api.get('/api/auth/me')); }
    catch (e) {
      if (e.status === 401 || e.status === 403) clearSession(); // only a rejected session signs the user out
      else { mount(app, errorState(e)); $('[data-action="retry"]', app)?.addEventListener('click', boot); return; } // network/server trouble keeps the session
    }
  }
  if (!store.token || !store.ws) { if (path() !== '/login') location.hash = '/login'; return renderLogin(); }
  if (path() === '/login') location.hash = '/dashboard';
  renderShell();
}
async function renderLogin() {
  shellEl = null; removeListeners.forEach((f) => f()); removeListeners = [];
  mount(app, html`<main id="view" class="page-enter"></main>`);
  document.title = 'Sign in · Meeting Action Agent';
  await navigate(() => $('#view'), null);
}
window.addEventListener('auth:expired', () => { clearSession(); toast('Your session expired. Sign in again.', 'info'); location.hash = '/login'; boot(); });
window.addEventListener('app:signed-in', () => boot());
window.addEventListener('hashchange', () => {
  if (!store.token) { if (path() !== '/login') location.hash = '/login'; return renderLogin(); }
  if (!shellEl) return boot();
  closeMenus(); $('.shell')?.classList.remove('nav-open'); $('.scrim')?.remove();
  navigate(() => $('#view'), setMeta);
});

function setMeta(name) {
  $$('.nav a').forEach((a) => (a.dataset.route === name || (name === 'meeting' && a.dataset.route === 'meetings') ? a.setAttribute('aria-current', 'page') : a.removeAttribute('aria-current')));
  const label = TITLES[name] || (name === 'meeting' ? 'Meeting' : 'Meeting Action Agent');
  document.title = `${label} · Meeting Action Agent`; announce(`${label} page loaded`);
}

function renderShell() {
  const ws = store.ws;
  mount(app, html`
  <div class="shell ${sidebar.collapsed ? 'collapsed' : ''}">
    <aside class="sidebar" id="sidebar" aria-label="Primary">
      <a class="logo" href="#/dashboard"><span class="brand-mark">${icon('check')}</span><span class="label">Meeting Action</span></a>
      <nav class="nav" aria-label="Main navigation">
        ${NAV.map(([k, label, ic]) => html`<a href="#/${k}" data-route="${k}" title="${label}">${icon(ic)}<span class="label">${label}</span>${k === 'approvals' ? html`<span class="nav-badge" id="appr-badge" hidden></span>` : ''}</a>`)}
      </nav>
      <div class="sidebar-foot"><button class="btn ghost sm desktop-only" id="collapse" aria-pressed="${sidebar.collapsed}" aria-label="Collapse sidebar">${icon('chevron')}<span class="label">Collapse</span></button></div>
    </aside>
    <div class="main-col">
      <header class="topbar">
        <button class="btn ghost icon mobile-only" id="open-nav" aria-label="Open navigation" aria-controls="sidebar" aria-expanded="false">${icon('menu')}</button>
        <div class="search rel" role="search">${icon('search')}<label class="sr-only" for="gsearch">Search tasks, meetings and decisions</label>
          <input id="gsearch" class="input" type="search" role="combobox" aria-autocomplete="list" placeholder="Search tasks, meetings, decisions…" autocomplete="off" aria-controls="gresults" aria-expanded="false"><div id="gresults" class="search-results" hidden></div></div>
        <div class="topbar-right">
          <div class="rel desktop-only"><button class="btn sm" id="ws-btn" aria-haspopup="menu" aria-expanded="false">${ws.name}${ws.is_demo ? html` <span class="demo-badge">Demo data</span>` : ''}</button><div id="ws-menu" class="menu" role="menu" hidden></div></div>
          <button class="btn ghost icon" id="theme-btn" aria-label="Switch to ${theme.get() === 'dark' ? 'light' : 'dark'} theme">${icon(theme.get() === 'dark' ? 'sun' : 'moon')}</button>
          <div class="rel"><button class="btn ghost icon" id="notif-btn" aria-label="Notifications" aria-haspopup="true" aria-expanded="false">${icon('bell')}<span class="dot-badge" id="notif-count" hidden></span></button><div id="notif-menu" class="menu notif-menu" hidden></div></div>
          <div class="rel"><button class="btn ghost icon" id="prof-btn" aria-label="Account menu" aria-haspopup="menu" aria-expanded="false"><span class="avatar">${initials(store.user.name)}</span></button>
            <div id="prof-menu" class="menu" role="menu" hidden><div class="menu-title">${store.user.name}</div><div class="menu-title muted">${store.user.email} · ${role()}</div><hr>
              <div class="mobile-only"><div class="menu-title">Workspace</div>${store.workspaces.map((w) => html`<button role="menuitem" data-ws="${w.id}">${w.name}</button>`)}<hr></div>
              <button role="menuitem" id="signout">${icon('logout')} Sign out</button></div></div>
        </div>
      </header>
      <main id="view" class="content" aria-live="off"></main>
    </div>
  </div>`);
  shellEl = $('.shell');
  wireShell();
  navigate(() => $('#view'), setMeta);
  refreshBadges(); const t = setInterval(refreshBadges, 30000); removeListeners.push(() => clearInterval(t));
}

function closeMenus() {
  $$('.menu').forEach((m) => { m.hidden = true; });
  $$('[aria-haspopup]').forEach((b) => b.setAttribute('aria-expanded', 'false'));
  const r = $('#gresults'); if (r) r.hidden = true;
}
function toggleMenu(btn, menu) {
  const open = menu.hidden; closeMenus(); menu.hidden = !open; btn.setAttribute('aria-expanded', String(open));
  if (open) menu.querySelector('button, a')?.focus();
}

function wireShell() {
  const sh = $('.shell');
  $('#collapse').addEventListener('click', (e) => { sidebar.collapsed = !sh.classList.contains('collapsed'); sh.classList.toggle('collapsed', sidebar.collapsed); e.currentTarget.setAttribute('aria-pressed', String(sidebar.collapsed)); });
  $('#open-nav').addEventListener('click', (e) => {
    const open = !sh.classList.contains('nav-open'); sh.classList.toggle('nav-open', open); e.currentTarget.setAttribute('aria-expanded', String(open));
    $('.scrim')?.remove(); if (open) { const s = document.createElement('div'); s.className = 'scrim'; s.addEventListener('click', () => { sh.classList.remove('nav-open'); s.remove(); e.currentTarget.setAttribute('aria-expanded', 'false'); }); sh.append(s); $('.nav a').focus(); }
  });
  $('#theme-btn').addEventListener('click', (e) => {
    const next = theme.get() === 'dark' ? 'light' : 'dark'; theme.set(next);
    e.currentTarget.setAttribute('aria-label', `Switch to ${next === 'dark' ? 'light' : 'dark'} theme`); mount(e.currentTarget, icon(next === 'dark' ? 'sun' : 'moon'));
  });
  // workspace switcher
  const wsMenu = $('#ws-menu');
  mount(wsMenu, html`<div class="menu-title">Switch workspace</div>${store.workspaces.map((w) => html`<button role="menuitemradio" aria-checked="${w.id === store.ws.id}" data-ws="${w.id}" ${w.id === store.ws.id ? 'aria-selected="true"' : ''}>${w.name} <span class="meta">· ${w.role}</span></button>`)}`);
  $('#ws-btn').addEventListener('click', (e) => toggleMenu(e.currentTarget, wsMenu));
  $('#prof-btn').addEventListener('click', (e) => toggleMenu(e.currentTarget, $('#prof-menu')));
  const pick = (e, b) => { const id = Number(b.dataset.ws); if (id !== store.ws.id) { store.wid = id; store.ws = store.workspaces.find((w) => w.id === id); renderShell(); toast(`Switched to ${store.ws.name}`, 'info', 2500); } else closeMenus(); };
  on($('.topbar'), 'click', '[data-ws]', pick);
  $('#signout').addEventListener('click', () => { clearSession(); removeListeners.forEach((f) => f()); location.hash = '/login'; boot(); });
  // notifications
  $('#notif-btn').addEventListener('click', async (e) => { toggleMenu(e.currentTarget, $('#notif-menu')); await loadNotifs(); });
  on($('#notif-menu'), 'click', '[data-readall]', async () => { try { await api.w.post('/notifications/read-all'); await refreshBadges(); await loadNotifs(); } catch (er) { toast(er.message, 'error'); } });
  // search
  const input = $('#gsearch'), box = $('#gresults'); let sctl = null;
  const run = debounce(async () => {
    const q = input.value.trim(); if (q.length < 2) { box.hidden = true; input.setAttribute('aria-expanded', 'false'); return; }
    sctl?.abort(); sctl = new AbortController();
    try {
      const r = await api.w.get(`/search?q=${encodeURIComponent(q)}`, { signal: sctl.signal });
      const rows = [...r.tasks.map((t) => [`#/tasks?open=${t.id}`, `Task · ${t.title}`]), ...r.meetings.map((m) => [`#/meetings/${m.id}`, `Meeting · ${m.title}`]), ...r.decisions.map((d) => ['#/decisions', `Decision · ${d.text}`])];
      mount(box, rows.length ? html`${rows.map(([h, l]) => html`<a href="${h}">${l}</a>`)}` : html`<div class="meta pad">No matches for “${q}”.</div>`);
      box.hidden = false; input.setAttribute('aria-expanded', 'true');
    } catch (e) { if (!isAbort(e)) { mount(box, html`<div class="meta">${e.message}</div>`); box.hidden = false; } }
  }, 250);
  input.addEventListener('input', run);
  input.addEventListener('keydown', (e) => { if (e.key === 'Escape') { box.hidden = true; input.blur(); } if (e.key === 'ArrowDown') { box.querySelector('a')?.focus(); e.preventDefault(); } });
  box.addEventListener('click', () => { box.hidden = true; input.value = ''; });
  document.addEventListener('click', (e) => { if (!e.target.closest('.rel') && !e.target.closest('.menu')) closeMenus(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeMenus(); });
}

async function loadNotifs() {
  const m = $('#notif-menu'); if (!m) return;
  try {
    const r = await api.w.get('/notifications');
    mount(m, html`<div class="menu-title row between"><span>Notifications</span>${r.unread ? html`<button class="btn ghost sm" data-readall>Mark all read</button>` : ''}</div>
      ${r.items.length ? r.items.map((n) => html`<a href="${n.link || '#/dashboard'}">${!n.read ? html`<span class="risk-dot medium" aria-label="Unread"></span>` : ''}<span class="grow">${n.text}<br><span class="meta">${relTime(n.created_at)}</span></span></a>`) : html`<div class="meta pad">You’re all caught up.</div>`}`);
  } catch (e) { mount(m, html`<div class="meta pad">${e.message}</div>`); }
}
async function refreshBadges() {
  if (!store.token || !store.ws) return;
  try {
    const n = await api.w.get('/notifications'); const c = $('#notif-count');
    if (c) { c.hidden = !n.unread; c.textContent = n.unread > 9 ? '9+' : n.unread; }
    if (can('manager')) {
      const a = await api.w.get('/approvals?status=pending'); const b = $('#appr-badge');
      if (b) { b.hidden = !a.length; b.textContent = a.length; }
    }
  } catch { /* badges are best-effort */ }
}
window.addEventListener('app:badges', refreshBadges);
boot();
