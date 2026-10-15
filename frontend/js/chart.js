import { html, raw, esc } from './dom.js';

/** Accessible grouped bar chart (SVG) with a visually-hidden data table as text alternative. */
export function barChart({ labels, series, title, height = 180 }) {
  const W = 560, H = height, pad = { l: 28, r: 8, t: 8, b: 24 };
  const max = Math.max(1, ...series.flatMap((s) => s.values));
  const nice = Math.max(1, Math.ceil(max / 4) * 4);
  const iw = W - pad.l - pad.r, ih = H - pad.t - pad.b;
  const gw = iw / labels.length, bw = Math.min(22, (gw - 8) / series.length);
  let g = '';
  for (let i = 0; i <= 4; i++) {
    const y = pad.t + ih - (ih * i) / 4;
    g += `<line class="grid-line" x1="${pad.l}" x2="${W - pad.r}" y1="${y}" y2="${y}"/><text x="${pad.l - 6}" y="${y + 3}" text-anchor="end">${(nice * i) / 4}</text>`;
  }
  let n = 0;
  labels.forEach((lb, i) => {
    series.forEach((s, j) => {
      const v = s.values[i], h = (ih * v) / nice;
      const x = pad.l + i * gw + (gw - bw * series.length) / 2 + j * bw;
      g += `<rect class="bar-grow ${s.cls}" data-i="${n++}" x="${x}" y="${pad.t + ih - h}" width="${bw - 2}" height="${h}" rx="3"><title>${esc(s.name)} ${esc(lb)}: ${v}</title></rect>`;
    });
    g += `<text x="${pad.l + i * gw + gw / 2}" y="${H - 6}" text-anchor="middle">${esc(lb)}</text>`;
  });
  const table = `<table class="sr-only"><caption>${esc(title)}</caption><thead><tr><th>Period</th>${series.map((s) => `<th>${esc(s.name)}</th>`).join('')}</tr></thead><tbody>${labels.map((l, i) => `<tr><td>${esc(l)}</td>${series.map((s) => `<td>${s.values[i]}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
  return html`<figure class="fig"><svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${title}">${raw(g)}</svg>${raw(table)}
    <figcaption class="legend">${series.map((s) => html`<span><i class="${s.cls}"></i>${s.name}</span>`)}</figcaption></figure>`;
}
export function meter(value, max, over = false, label = 'Progress') {
  const r = max > 0 ? Math.min(1, value / max) : 0;
  return html`<div class="meter ${over ? 'over' : ''}" role="meter" aria-label="${label}" aria-valuenow="${value}" aria-valuemin="0" aria-valuemax="${max}"><i data-scale="${r}"></i></div>`;
}
