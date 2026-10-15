// Tiny safe-by-default templating: every interpolated value is HTML-escaped unless wrapped by html``/raw().
class Safe { constructor(s) { this.s = s; } toString() { return this.s; } }
const MAP = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
export const esc = (v) => String(v).replace(/[&<>"']/g, (c) => MAP[c]);
function render(v) {
  if (v == null || v === false || v === true) return '';
  if (v instanceof Safe) return v.s;
  if (Array.isArray(v)) return v.map(render).join('');
  return esc(v);
}
export function html(strings, ...vals) {
  let out = '';
  strings.forEach((s, i) => { out += s; if (i < vals.length) out += render(vals[i]); });
  return new Safe(out);
}
export const raw = (s) => new Safe(String(s));
/** CSP forbids inline style attributes, so dynamic values travel in data-* and are applied through the CSSOM. */
export function hydrate(root) {
  root.querySelectorAll('[data-i]').forEach((n) => n.style.setProperty('--i', n.dataset.i));
  root.querySelectorAll('[data-scale]').forEach((n) => { n.style.transform = `scaleX(${n.dataset.scale})`; });
  root.querySelectorAll('.stagger').forEach((n) => [...n.children].forEach((c, i) => c.style.setProperty('--i', i)));
}
export const mount = (el, safe) => { el.innerHTML = safe instanceof Safe ? safe.s : esc(safe); hydrate(el); return el; };
export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
/** Event delegation: on(root, 'click', '[data-action]', (e, target) => ...) */
export function on(root, type, selector, handler) {
  const fn = (e) => { const t = e.target.closest(selector); if (t && root.contains(t)) handler(e, t); };
  root.addEventListener(type, fn);
  return () => root.removeEventListener(type, fn);
}
export const debounce = (fn, ms = 250) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
export function stagger(root) { [...root.children].forEach((c, i) => c.style.setProperty('--i', i)); }
