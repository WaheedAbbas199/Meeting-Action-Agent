import { html, mount, $ } from '../dom.js';
import { api } from '../api.js';
import { store, setSession } from '../store.js';
import { icon } from '../icons.js';
import { busy, errMsg } from '../ui.js';
import { field, localTz } from '../components/common.js';

export default {
  title: 'Sign in',
  async render({ root }) {
    let mode = 'login';
    const draw = (error = '') => {
      mount(root, html`<div class="auth">
        <section class="auth-art" aria-hidden="false"><div class="row"><span class="brand-mark">${icon('check')}</span><strong>Meeting Action Agent</strong></div>
          <div><h1>Meetings end. Commitments shouldn’t.</h1><p>Turn conversations into evidence-backed decisions and tasks, track every commitment, and follow up through human-approved email and WhatsApp.</p></div>
          <ul class="auth-points list-reset"><li>${icon('shield')} Every AI item links to the exact words that support it</li><li>${icon('tasks')} Nothing becomes a task until a person approves it</li><li>${icon('mail')} Nothing is sent externally without an approval</li></ul><div class="orb"></div></section>
        <section class="auth-form"><div class="auth-card"><div><h2 id="auth-title">${mode === 'login' ? 'Welcome back' : 'Create your workspace'}</h2><p class="muted">${mode === 'login' ? 'Sign in to continue.' : 'Set up an account and a first workspace.'}</p></div>
          ${error ? html`<div class="callout bad" role="alert" id="auth-err">${error}</div>` : ''}
          <form id="authform" class="stack" novalidate aria-labelledby="auth-title">
            ${mode === 'register' ? html`${field('a-name', 'Your name', html`<input id="a-name" name="name" class="input" autocomplete="name" required>`)}${field('a-ws', 'Workspace name', html`<input id="a-ws" name="workspace_name" class="input" required>`)}` : ''}
            ${field('a-email', 'Email', html`<input id="a-email" name="email" type="email" class="input" autocomplete="email" required autofocus>`)}
            ${field('a-pw', 'Password', html`<input id="a-pw" name="password" type="password" class="input" autocomplete="${mode === 'login' ? 'current-password' : 'new-password'}" minlength="10" required>`, mode === 'register' ? 'At least 10 characters.' : '')}
            <button class="btn primary" type="submit">${mode === 'login' ? 'Sign in' : 'Create account'}</button>
          </form>
          <p class="muted">${mode === 'login' ? 'New here?' : 'Already have an account?'} <a href="#/login" id="swap">${mode === 'login' ? 'Create an account' : 'Sign in'}</a></p></div></section></div>`);
      $('#swap', root).addEventListener('click', (e) => { e.preventDefault(); mode = mode === 'login' ? 'register' : 'login'; draw(); });
      $('#authform', root).addEventListener('submit', async (e) => {
        e.preventDefault(); const f = e.currentTarget; const d = Object.fromEntries(new FormData(f));
        if (!d.email || !d.password || (mode === 'register' && (!d.name || !d.workspace_name))) return draw('Fill in all fields.');
        if (mode === 'register' && d.password.length < 10) return draw('Use a password with at least 10 characters.');
        await busy(e.submitter, async () => {
          try {
            const r = mode === 'login' ? await api.post('/api/auth/login', { email: d.email, password: d.password }) : await api.post('/api/auth/register', { ...d, timezone: localTz() });
            store.token = r.token; setSession(r); window.dispatchEvent(new Event('app:signed-in'));
          } catch (er) { draw(errMsg(er)); $('#auth-err')?.focus?.(); }
        });
      });
    };
    draw();
  },
};
