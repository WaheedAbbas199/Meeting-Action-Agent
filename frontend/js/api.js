import { store } from './store.js';

export class ApiError extends Error {
  constructor(status, detail) { super(typeof detail === 'string' ? detail : 'Request failed'); this.status = status; this.detail = detail; }
}
function describe(detail) {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((d) => `${(d.loc || []).slice(1).join('.')}: ${d.msg}`.replace(/^: /, '')).join('; ');
  return 'Something went wrong';
}
async function request(method, path, { body, form, signal, timeout = 25000 } = {}) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(new DOMException('Timed out', 'TimeoutError')), timeout);
  if (signal) signal.addEventListener('abort', () => ctl.abort(signal.reason), { once: true });
  const headers = {};
  if (store.token) headers.Authorization = `Bearer ${store.token}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  let res;
  try {
    res = await fetch(path, { method, headers, body: form || (body !== undefined ? JSON.stringify(body) : undefined), signal: ctl.signal });
  } catch (e) {
    if (e.name === 'AbortError' && signal?.aborted) throw e; // navigation: caller ignores
    if (e.name === 'AbortError' || e.name === 'TimeoutError') throw new ApiError(0, 'The request timed out. Check your connection and try again.');
    throw new ApiError(0, 'Cannot reach the server. Check your connection and try again.');
  } finally { clearTimeout(timer); }
  if (res.status === 204) return null;
  let data = null;
  try { data = await res.json(); } catch { /* non-JSON error body */ }
  if (!res.ok) {
    if (res.status === 401 && store.token) window.dispatchEvent(new CustomEvent('auth:expired'));
    throw new ApiError(res.status, describe(data?.detail) || res.statusText);
  }
  return data;
}
const w = (p) => `/api/w/${store.wid}${p}`;
export const api = {
  get: (p, o) => request('GET', p, o), post: (p, body, o) => request('POST', p, { body: body ?? {}, ...o }),
  put: (p, body, o) => request('PUT', p, { body, ...o }), patch: (p, body, o) => request('PATCH', p, { body, ...o }),
  del: (p, o) => request('DELETE', p, o), upload: (p, form, o) => request('POST', p, { form, timeout: 120000, ...o }),
  w: {
    get: (p, o) => request('GET', w(p), o), post: (p, body, o) => request('POST', w(p), { body: body ?? {}, ...o }),
    put: (p, body, o) => request('PUT', w(p), { body, ...o }), patch: (p, body, o) => request('PATCH', w(p), { body, ...o }),
    del: (p, o) => request('DELETE', w(p), o), upload: (p, form, o) => request('POST', w(p), { form, timeout: 120000, ...o }),
  },
};
export const isAbort = (e) => e?.name === 'AbortError';
