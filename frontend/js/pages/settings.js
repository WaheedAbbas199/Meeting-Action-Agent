import { html, mount, $, on, raw } from '../dom.js';
import { api } from '../api.js';
import { store, can, role, theme } from '../store.js';
import { pageHead, field, options, tzList, formData } from '../components/common.js';
import { skeletonList, toast, busy, errMsg, openModal, fmtDateTime, statusBadge, emptyState } from '../ui.js';

const ROLES = [['viewer', 'Viewer'], ['member', 'Member'], ['manager', 'Manager'], ['admin', 'Admin'], ['owner', 'Owner']];
const TABS = [['profile', 'Profile'], ['workspace', 'Workspace'], ['team', 'Team & roles'], ['contacts', 'Contacts & consent'], ['reminders', 'Reminder rules'], ['integrations', 'Integrations'], ['notifications', 'Notifications'], ['audit', 'Audit & jobs']];

export default {
  title: 'Settings',
  async render({ root, signal, isCurrent, query }) {
    let tab = query.tab || 'profile';
    const body = () => $('#sbody', root);
    const views = {
      async profile() {
        mount(body(), html`<section class="card stack"><h2>Your profile</h2><dl class="stack-sm"><div><dt class="label">Name</dt><dd class="dd">${store.user.name}</dd></div><div><dt class="label">Email</dt><dd class="dd">${store.user.email}</dd></div><div><dt class="label">Role in ${store.ws.name}</dt><dd class="dd">${role()}</dd></div></dl>
          <div class="field"><span class="label">Appearance</span><div class="seg" role="group" aria-label="Theme"><button data-set-theme="light" aria-pressed="${theme.get() === 'light'}">Light</button><button data-set-theme="dark" aria-pressed="${theme.get() === 'dark'}">Dark</button></div>
          <span class="help">Animations are reduced automatically if your system asks for reduced motion. Only the theme choice is stored in your browser.</span></div></section>`);
        on(body(), 'click', '[data-set-theme]', (e, b) => { theme.set(b.dataset.setTheme); views.profile(); });
      },
      async workspace() {
        const w = await api.w.get('/workspace', { signal }); const s = w.settings || {}, edit = can('admin');
        mount(body(), html`<form id="wsf" class="card stack" novalidate><h2>Workspace</h2>${edit ? '' : html`<div class="callout info">Only admins can change workspace settings.</div>`}
          ${field('w-name', 'Name', html`<input id="w-name" name="name" class="input" value="${w.name}" ${edit ? '' : raw('disabled')} required>`)}
          ${field('w-tz', 'Timezone', html`<select id="w-tz" name="timezone" class="select" ${edit ? '' : raw('disabled')}>${options(tzList().map((z) => [z, z]), w.timezone)}</select>`, 'Quiet hours and deadlines use this timezone.')}
          <div class="grid cols-2">${field('w-qs', 'Quiet hours start', html`<input id="w-qs" name="quiet_start" type="time" class="input" value="${s.quiet_start || ''}" ${edit ? '' : raw('disabled')}>`)}${field('w-qe', 'Quiet hours end', html`<input id="w-qe" name="quiet_end" type="time" class="input" value="${s.quiet_end || ''}" ${edit ? '' : raw('disabled')}>`)}</div>
          <p class="help">Approved messages are held during quiet hours and sent afterwards. Leave both empty to disable.</p>
          ${field('w-ttl', 'Approval expiry (hours)', html`<input id="w-ttl" name="approval_ttl_hours" type="number" min="1" max="168" class="input w-sm" value="${s.approval_ttl_hours || 24}" ${edit ? '' : raw('disabled')}>`)}
          ${edit ? html`<div><button class="btn primary" type="submit">Save workspace</button></div>` : ''}</form>`);
        $('#wsf', root)?.addEventListener('submit', (e) => { e.preventDefault(); const d = formData(e.currentTarget);
          busy(e.submitter, async () => { try { await api.w.patch('/workspace', { name: d.name, timezone: d.timezone, quiet_start: d.quiet_start || '', quiet_end: d.quiet_end || '', approval_ttl_hours: Number(d.approval_ttl_hours) }); toast('Workspace saved'); } catch (er) { toast(errMsg(er), 'error'); } }); });
      },
      async team() {
        const m = await api.w.get('/members', { signal }); const admin = can('admin');
        mount(body(), html`<section class="stack"><div class="row between"><h2>Team & roles</h2>${admin ? html`<button class="btn primary" id="am">Add member</button>` : ''}</div>
          <div class="table-wrap"><table><caption class="sr-only">Members</caption><thead><tr><th scope="col">Person</th><th scope="col">Team</th><th scope="col">Weekly capacity</th><th scope="col">Role</th></tr></thead>
          <tbody>${m.map((x) => html`<tr><td><strong>${x.name}</strong><div class="meta">${x.email}</div></td><td>${x.team || '—'}</td><td>${admin ? html`<label class="sr-only" for="cap-${x.user_id}">Capacity for ${x.name}</label><input id="cap-${x.user_id}" class="input w-sm" type="number" min="1" max="200" data-cap="${x.user_id}" value="${x.weekly_capacity}">` : x.weekly_capacity}</td>
            <td>${admin ? html`<label class="sr-only" for="role-${x.user_id}">Role for ${x.name}</label><select id="role-${x.user_id}" class="select sel-sm" data-role="${x.user_id}">${options(ROLES, x.role)}</select>` : x.role}</td></tr>`)}</tbody></table></div>
          <p class="meta">Roles: viewers read; members create and edit; managers approve items, messages and reassignments; admins manage settings and people; owners can grant ownership.</p></section>`);
        on(body(), 'change', '[data-role]', async (e, s) => { try { await api.w.patch(`/members/${s.dataset.role}`, { role: s.value }); toast('Role updated'); } catch (er) { toast(errMsg(er), 'error'); views.team(); } });
        on(body(), 'change', '[data-cap]', async (e, s) => { try { await api.w.patch(`/members/${s.dataset.cap}`, { weekly_capacity: Number(s.value) }); toast('Capacity updated'); } catch (er) { toast(errMsg(er), 'error'); views.team(); } });
        $('#am', root)?.addEventListener('click', async () => {
          const r = await openModal({ title: 'Add member', body: html`<form id="amf" class="stack" novalidate>${field('am-email', 'Email', html`<input id="am-email" name="email" type="email" class="input" required autofocus>`)}${field('am-name', 'Name (new people)', html`<input id="am-name" name="name" class="input">`)}${field('am-pw', 'Initial password (new people, 10+ characters)', html`<input id="am-pw" name="initial_password" type="password" class="input" autocomplete="new-password">`)}${field('am-role', 'Role', html`<select id="am-role" name="role" class="select">${options(ROLES.slice(0, 4), 'member')}</select>`)}<p class="error-text" id="am-err" role="alert"></p></form>`,
            actions: html`<button class="btn" data-close="cancel">Cancel</button><button class="btn primary" id="am-go">Add</button>`,
            onMount: (box, finish) => $('#am-go', box).addEventListener('click', (e) => busy(e.currentTarget, async () => { const d = formData($('#amf', box)); try { finish(await api.w.post('/members', { ...d, initial_password: d.initial_password || null })); } catch (er) { $('#am-err', box).textContent = errMsg(er); } })) });
          if (r) { toast('Member added'); views.team(); }
        });
      },
      async contacts() {
        const c = await api.w.get('/contacts', { signal }); const edit = can('manager');
        mount(body(), html`<section class="stack"><div class="row between"><h2>Contacts & consent</h2>${edit ? html`<button class="btn primary" id="ac">Add contact</button>` : ''}</div>
          <div class="callout info">Follow-ups can only go to contacts you have marked as authorized (email) or opted in (WhatsApp). Record consent only when you actually have it.</div>
          ${c.length ? html`<div class="table-wrap"><table><caption class="sr-only">Contacts</caption><thead><tr><th scope="col">Name</th><th scope="col">Email</th><th scope="col">WhatsApp</th><th scope="col"><span class="sr-only">Actions</span></th></tr></thead><tbody>${c.map((x) => html`<tr><td>${x.name}</td><td>${x.email || '—'} ${x.email ? statusBadge(x.email_authorized ? 'approved' : 'pending') : ''}</td><td>${x.phone || '—'} ${x.phone ? html`<span class="badge ${x.whatsapp_opt_in ? 'good' : 'warn'}">${x.whatsapp_opt_in ? 'Opted in' : 'No opt-in'}</span>` : ''}</td><td class="right">${edit ? html`<button class="btn sm" data-ec="${x.id}">Edit</button> <button class="btn sm danger" data-dc="${x.id}">Delete</button>` : ''}</td></tr>`)}</tbody></table></div>` : emptyState('No contacts', 'Add the people you may need to follow up with.')}</section>`);
        const form = async (x = {}) => openModal({ title: x.id ? 'Edit contact' : 'Add contact', body: html`<form id="cf" class="stack" novalidate>${field('c-name', 'Name', html`<input id="c-name" name="name" class="input" value="${x.name || ''}" required autofocus>`)}${field('c-email', 'Email', html`<input id="c-email" name="email" type="email" class="input" value="${x.email || ''}">`)}
          <label class="check"><input type="checkbox" name="email_authorized" ${x.email_authorized ? raw('checked') : ''}> This person has agreed to receive email from us</label>${field('c-phone', 'WhatsApp number (international format)', html`<input id="c-phone" name="phone" class="input" placeholder="+923001234567" value="${x.phone || ''}">`)}
          <label class="check"><input type="checkbox" name="whatsapp_opt_in" ${x.whatsapp_opt_in ? raw('checked') : ''}> This person has opted in to WhatsApp messages</label><p class="error-text" id="c-err" role="alert"></p></form>`,
          actions: html`<button class="btn" data-close="cancel">Cancel</button><button class="btn primary" id="c-go">Save</button>`,
          onMount: (box, finish) => $('#c-go', box).addEventListener('click', (e) => busy(e.currentTarget, async () => { const f = $('#cf', box), d = formData(f); const body = { name: d.name, email: d.email || '', phone: d.phone || '', email_authorized: f.email_authorized.checked, whatsapp_opt_in: f.whatsapp_opt_in.checked, user_id: x.user_id ?? null };
            if (!body.name.trim()) { $('#c-err', box).textContent = 'Name is required.'; return; } try { finish(x.id ? await api.w.put(`/contacts/${x.id}`, body) : await api.w.post('/contacts', body)); } catch (er) { $('#c-err', box).textContent = errMsg(er); } })) });
        $('#ac', root)?.addEventListener('click', async () => { if (await form()) { toast('Contact saved'); views.contacts(); } });
        on(body(), 'click', '[data-ec]', async (e, b) => { if (await form(c.find((y) => y.id === Number(b.dataset.ec)))) { toast('Contact saved'); views.contacts(); } });
        on(body(), 'click', '[data-dc]', (e, b) => busy(b, async () => { try { await api.w.del(`/contacts/${b.dataset.dc}`); toast('Contact deleted'); views.contacts(); } catch (er) { toast(errMsg(er), 'error'); } }));
      },
      async reminders() {
        const r = await api.w.get('/reminder-rules', { signal }); const edit = can('manager');
        mount(body(), html`<section class="stack"><h2>Reminder rules</h2><div class="callout info">Rules only create <strong>drafts</strong>. Each one still needs approval before anything is sent. Run them from the Follow-ups page.</div>
          ${r.length ? html`<div class="stack-sm">${r.map((x) => html`<div class="card row between"><span><strong>${x.name}</strong><br><span class="meta">${x.trigger === 'before_due' ? `${x.days} day(s) before the deadline` : `${x.days} day(s) after the deadline`} · ${x.channel}</span></span>${edit ? html`<span class="row"><label class="check"><input type="checkbox" data-en="${x.id}" ${x.enabled ? raw('checked') : ''}> Enabled</label><button class="btn sm danger" data-dr="${x.id}">Delete</button></span>` : statusBadge(x.enabled ? 'approved' : 'draft')}</div>`)}</div>` : emptyState('No rules', 'Add a rule such as “1 day before the deadline”.')}
          ${edit ? html`<form id="rf" class="card row" novalidate>${field('r-name', 'Name', html`<input id="r-name" name="name" class="input" required placeholder="1 day before">`)}${field('r-trig', 'When', html`<select id="r-trig" name="trigger" class="select"><option value="before_due">Before deadline</option><option value="overdue">After deadline</option></select>`)}${field('r-days', 'Days', html`<input id="r-days" name="days" type="number" min="0" max="60" value="1" class="input w-sm">`)}${field('r-ch', 'Channel', html`<select id="r-ch" name="channel" class="select"><option value="email">Email</option><option value="whatsapp">WhatsApp</option></select>`)}<button class="btn primary" type="submit">Add rule</button></form>` : ''}</section>`);
        $('#rf', root)?.addEventListener('submit', (e) => { e.preventDefault(); const d = formData(e.currentTarget); if (!d.name.trim()) return toast('Give the rule a name.', 'error');
          busy(e.submitter, async () => { try { await api.w.post('/reminder-rules', { ...d, days: Number(d.days), enabled: true }); toast('Rule added'); views.reminders(); } catch (er) { toast(errMsg(er), 'error'); } }); });
        on(body(), 'change', '[data-en]', async (e, c) => { const x = r.find((y) => y.id === Number(c.dataset.en)); try { await api.w.put(`/reminder-rules/${x.id}`, { ...x, enabled: c.checked }); toast(c.checked ? 'Rule enabled' : 'Rule disabled'); } catch (er) { toast(errMsg(er), 'error'); views.reminders(); } });
        on(body(), 'click', '[data-dr]', (e, b) => busy(b, async () => { try { await api.w.del(`/reminder-rules/${b.dataset.dr}`); toast('Rule deleted'); views.reminders(); } catch (er) { toast(errMsg(er), 'error'); } }));
      },
      async integrations() {
        const ints = await api.w.get('/integrations', { signal }); const admin = can('admin');
        mount(body(), html`<section class="stack"><h2>Integrations</h2><p class="muted">Credentials live only in server environment variables. They are never shown here or stored in the database.</p>
          <div class="grid cols-2">${ints.map((i) => html`<article class="card stack-sm"><div class="row between"><strong>${{ email: 'Email (Gmail API)', whatsapp: 'WhatsApp Business (Cloud API)', calendar: 'Calendar', ai: 'AI extraction', stt: 'Speech-to-text' }[i.kind]}</strong><span class="badge ${i.ready ? 'good' : 'warn'}">${i.ready ? 'Ready' : 'Not ready'}</span></div>
            <p class="meta">Provider: ${i.provider}</p><p class="muted">${i.message}</p>${['email', 'whatsapp', 'calendar'].includes(i.kind) ? html`<label class="check"><input type="checkbox" data-int="${i.kind}" ${i.enabled ? raw('checked') : ''} ${admin && (i.ready || i.enabled) ? '' : raw('disabled')}> Enabled for this workspace</label>${admin ? '' : html`<span class="meta">Admins only.</span>`}` : ''}</article>`)}</div></section>`);
        on(body(), 'change', '[data-int]', async (e, c) => { try { await api.w.put(`/integrations/${c.dataset.int}`, { enabled: c.checked }); toast(c.checked ? 'Integration enabled' : 'Integration disabled'); } catch (er) { c.checked = !c.checked; toast(errMsg(er), 'error'); } });
      },
      async notifications() {
        mount(body(), html`<section class="card stack"><h2>Notifications</h2><p>In-app notifications (bell icon) are always on for meeting results, approvals needed and follow-up outcomes.</p>
          <p>Quiet hours and timezone for outbound messages are set per workspace on the <a href="#/settings?tab=workspace">Workspace</a> tab.</p><div class="callout warn">Per-person notification channel preferences (for example, email digests) are not implemented yet.</div></section>`);
      },
      async audit() {
        if (!can('admin')) return mount(body(), html`<div class="callout info">Only admins can view the audit log and job health.</div>`);
        const [a, j] = await Promise.all([api.w.get('/audit', { signal }), api.w.get('/jobs', { signal })]);
        mount(body(), html`<section class="stack"><h2>Background jobs</h2><div class="row">${Object.entries(j.counts).map(([k, v]) => html`<span class="badge ${k === 'dead' ? 'bad' : ''}">${k}: ${v}</span>`)}${Object.keys(j.counts).length ? '' : html`<span class="muted">No jobs yet.</span>`}</div>
          ${j.dead.length ? html`<div class="callout bad"><div>${j.dead.map((d) => html`<div>${d.kind} #${d.ref_id}: ${d.error}</div>`)}</div></div>` : ''}
          <h2>Audit log</h2><div class="table-wrap"><table><caption class="sr-only">Audit log</caption><thead><tr><th scope="col">When</th><th scope="col">Who</th><th scope="col">Action</th><th scope="col">Entity</th></tr></thead><tbody>${a.map((x) => html`<tr><td class="nowrap">${fmtDateTime(x.at)}</td><td>${x.actor}</td><td>${x.action}</td><td>${x.entity} ${x.entity_id ?? ''}</td></tr>`)}</tbody></table></div></section>`);
      },
    };
    const draw = async () => {
      mount(root, html`${pageHead('Settings', `${store.ws.name} · your role: ${role()}`)}<div class="tabs" role="tablist" aria-label="Settings sections">${TABS.map(([k, l]) => html`<button class="tab" role="tab" data-tab="${k}" aria-selected="${tab === k}">${l}</button>`)}</div><div id="sbody">${skeletonList(3)}</div>`);
      try { await views[tab](); } catch (e) { if (e.name !== 'AbortError') mount(body(), html`<div class="callout bad" role="alert">${errMsg(e)}</div>`); }
    };
    root.addEventListener('click', (e) => { const t = e.target.closest('[data-tab]'); if (t && t.closest('.tabs')) { tab = t.dataset.tab; draw(); } });
    await draw();
  },
};
