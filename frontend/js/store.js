// Session state. Only the auth token (sessionStorage, cleared when the tab closes) and UI prefs are persisted.
const S = {
  get token() { return sessionStorage.getItem('maa.token'); },
  set token(v) { v ? sessionStorage.setItem('maa.token', v) : sessionStorage.removeItem('maa.token'); },
  get wid() { return Number(sessionStorage.getItem('maa.wid')) || null; },
  set wid(v) { v ? sessionStorage.setItem('maa.wid', v) : sessionStorage.removeItem('maa.wid'); },
  user: null,
  workspaces: [],
  ws: null,
  pendingApprovals: 0,
};
const RANK = { viewer: 0, member: 1, manager: 2, admin: 3, owner: 4 };
export const store = S;
export const role = () => S.ws?.role || 'viewer';
export const can = (r) => RANK[role()] >= RANK[r];
export function setSession(payload) {
  S.user = payload.user; S.workspaces = payload.workspaces;
  S.ws = S.workspaces.find((w) => w.id === S.wid) || S.workspaces[0] || null;
  S.wid = S.ws ? S.ws.id : null;
}
export function clearSession() { S.token = null; S.wid = null; S.user = null; S.workspaces = []; S.ws = null; }
export const theme = {
  get() { return localStorage.getItem('maa.theme') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'); },
  set(v) { localStorage.setItem('maa.theme', v); document.documentElement.dataset.theme = v; },
};
export const sidebar = {
  get collapsed() { return localStorage.getItem('maa.sidebar') === '1'; },
  set collapsed(v) { localStorage.setItem('maa.sidebar', v ? '1' : '0'); },
};
