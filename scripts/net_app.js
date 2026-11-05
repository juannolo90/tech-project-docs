/* tech-project-docs · arquitectura.html: dibuja desde el JSON embebido (#spec), permite completar datos y guardarlos en el propio HTML.
   Sin dependencias ni red. Se inserta tal cual en el HTML por scripts/net.py. */
(() => {
const NS = 'http://www.w3.org/2000/svg';
const C = window.CFG;
const ICONS = JSON.parse(document.getElementById('icons').textContent);
let spec = JSON.parse(document.getElementById('spec').textContent);
let mask = false, selFlow = null, paused = false, raf = 0, dirty = false, saveTimer = 0;
const reduce = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
const IPRE = /(?<![\w.])((?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3})(?![\w]|\.\d)/g;
const mt = s => mask ? String(s).replace(IPRE, (m, a) => a.split('.').slice(0, 2).join('.') + '.x.x') : String(s);
const $ = s => document.querySelector(s);

function S(tag, at = {}, ...kids) {
  const e = document.createElementNS(NS, tag);
  for (const k in at) if (at[k] != null) e.setAttribute(k, at[k]);
  kids.flat().forEach(c => e.append(c));
  return e;
}
function H(tag, at = {}, ...kids) {
  const e = document.createElement(tag);
  for (const k in at) {
    if (at[k] == null) continue;
    if (k === 'class') e.className = at[k];
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), at[k]);
    else if (k === 'value') e.value = at[k];
    else e.setAttribute(k, at[k]);
  }
  kids.flat().forEach(c => e.append(c instanceof Node ? c : document.createTextNode(c == null ? '' : c)));
  return e;
}
const clear = e => { while (e.firstChild) e.removeChild(e.firstChild); };
const hopId = h => typeof h === 'string' ? h : h.id;
const hopLabel = h => typeof h === 'string' ? '' : (h.label || '');
const byId = () => Object.fromEntries(spec.nodes.map(n => [n.id, n]));
const wrap = (text, width = 18, max = 3) => {
  const words = String(text).split(/\s+/).filter(Boolean), lines = []; let cur = '';
  for (const w of words) { if (cur && cur.length + 1 + w.length > width) { lines.push(cur); cur = w; } else cur = (cur + ' ' + w).trim(); }
  if (cur) lines.push(cur);
  if (lines.length > max) { lines.length = max; lines[max - 1] = lines[max - 1].slice(0, width - 1) + '…'; }
  return lines.length ? lines : [''];
};

/* ---------------------------------------------------------------- validación (mismas reglas que net.py::check) */
function check() {
  const errs = [], pend = [], nodes = byId();
  const sites = Object.fromEntries(spec.sites.map(s => [s.id, s]));
  const segs = Object.fromEntries((spec.segments || []).map(s => [s.id, s]));
  for (const n of spec.nodes) {
    const kind = n.kind || 'app', site = sites[n.site];
    if (!site) { n.site ? errs.push(`«${n.name}»: sitio '${n.site}' no existe`) : pend.push(`¿En qué sitio está «${n.name}»? (on-prem, AWS, Azure, SAP, SaaS, otro)`); continue; }
    if (n.segment && !segs[n.segment]) errs.push(`«${n.name}»: segmento '${n.segment}' no existe`);
    if (site.kind === 'unknown') pend.push(`¿En qué sitio está «${n.name}»? (hoy figura en «${site.label}»)`);
    if (!['user', 'external', 'saas'].includes(kind) && !['saas', 'internet', 'users'].includes(site.kind) && !(n.ip || n.host)) pend.push(`¿Cuál es la IP u hostname de «${n.name}»?`);
    if (['aws', 'azure', 'gcp', 'onprem'].includes(site.kind) && kind !== 'user' && !C.NET_KINDS.includes(kind) && !n.segment) pend.push(`¿En qué VPC/VNet/subred/VLAN está «${n.name}»?`);
  }
  for (const s of (spec.segments || [])) if (!s.cidr) pend.push(`¿Cuál es el CIDR del segmento «${s.label || s.id}»?`);
  for (const f of spec.flows || []) {
    const ids = (f.hops || []).map(hopId);
    if (ids.some(i => !nodes[i])) continue;
    if (!f.protocol && !(f.hops || []).some(hopLabel)) pend.push(`Flujo ${f.id} «${f.label || ''}»: ¿qué protocolo y puerto usa?`);
    ids.slice(0, -1).forEach((a, j0) => {
      const na = nodes[a], nb = nodes[ids[j0 + 1]];
      if (na.site !== nb.site && !C.NET_KINDS.includes(na.kind) && !C.NET_KINDS.includes(nb.kind) && !((f.via || {})[String(j0 + 1)] || '').trim())
        pend.push(`Flujo ${f.id}: «${na.name}» → «${nb.name}» cruza de sitio; ¿hay firewall, VPN/Direct Connect/ExpressRoute, proxy o balanceador en medio? ¿cuál (nombre/IP)?`);
    });
  }
  for (const q of spec.questions || []) if (!(q.answer || '').trim()) pend.push(q.text);
  (spec.pending || []).forEach(p => pend.push(p));
  return { errs, pend: [...new Set(pend)] };
}

/* ---------------------------------------------------------------- layout */
class Box {
  constructor(id, label, kind, depth, cidr, detail, cols) { Object.assign(this, { id, label, kind, depth, cidr, detail, cols, nodes: [], kids: [], x: 0, y: 0, w: 0, h: 0 }); }
  header() { return this.depth === 0 ? 46 : 40; }
  measure() {
    this.kids.forEach(k => k.measure());
    const n = this.nodes.length;
    this.ncols = Math.max(this.cols || (this.depth === 0 ? Math.min(n, 2) : Math.min(n, 3)), 1);
    const rows = n ? Math.ceil(n / this.ncols) : 0;
    const nw = n ? this.ncols * C.CELLW : 0; this.nh = rows * C.CELLH;
    const kw = Math.max(0, ...this.kids.map(k => k.w));
    this.w = Math.max(nw, kw, 190) + 2 * C.PAD;
    this.h = this.header() + this.nh + this.kids.reduce((a, k) => a + k.h, 0) + 12 * this.kids.length + C.PAD;
  }
  place(x, y, w, pos) {
    this.x = x; this.y = y; if (w) this.w = w;
    const n = this.nodes.length, nw = Math.min(n, this.ncols) * C.CELLW, ox = x + (this.w - nw) / 2;
    this.nodes.forEach((nd, i) => pos.set(nd.id, { cx: ox + (i % this.ncols) * C.CELLW + C.CELLW / 2, ty: y + this.header() + Math.floor(i / this.ncols) * C.CELLH + 6 }));
    let cy = y + this.header() + this.nh + (this.kids.length ? 12 : 0);
    for (const k of this.kids) { k.place(x + C.PAD, cy, this.w - 2 * C.PAD, pos); cy += k.h + 12; }
  }
}
function layout() {
  const sites = new Map(), segs = new Map(), pos = new Map();
  spec.sites.forEach(s => sites.set(s.id, new Box(s.id, s.label || s.id, s.kind || 'unknown', 0, '', s.detail || '', s.cols)));
  (spec.segments || []).forEach(s => segs.set(s.id, new Box(s.id, s.label || s.id, s.kind || 'subnet', 1, s.cidr || '', s.detail || '', s.cols)));
  (spec.segments || []).forEach(s => { const b = segs.get(s.id), par = segs.get(s.parent) || sites.get(s.site); if (par && par !== b) { b.parent = par; par.kids.push(b); } });
  const dep = (b, g = 0) => b.parent && g < 20 ? dep(b.parent, g + 1) + 1 : 0;
  segs.forEach(b => { b.depth = Math.max(1, dep(b)); });
  for (const n of spec.nodes) {
    let holder = segs.get(n.segment); if (!holder || !holder.parent) holder = sites.get(n.site);
    if (!holder) { if (!sites.has('_unknown')) sites.set('_unknown', new Box('_unknown', 'Sitio por confirmar', 'unknown', 0, '', '', null)); holder = sites.get('_unknown'); }
    holder.nodes.push(n);
  }
  const tops = [...sites.values()].filter(t => t.nodes.length || t.kids.length || t.id !== '_unknown');
  tops.forEach(t => t.measure());
  let x = 30, H0 = Math.max(260, ...tops.map(t => t.h));
  for (const t of tops) { t.place(x, 0, t.w, pos); x += t.w + C.GAP; }
  return { tops, pos, W: x - C.GAP + 30, H: H0 };
}
function route(a, b, idx, topsX, chanBase) {
  const ax = a.cx, ay = a.ty + 30, bx = b.cx, by = b.ty + 30, off = ((idx % 7) - 3) * 6;
  if (Math.abs(ax - bx) < C.CELLW * 1.25) { const gx = Math.max(ax, bx) + 78 + off; return [[ax + 34, ay], [gx, ay], [gx, by], [bx + 34, by]]; }
  const idxOf = x => Math.max(0, ...topsX.map((v, i) => v <= x ? i : -1));
  if (Math.abs(idxOf(ax) - idxOf(bx)) <= 1) {
    if (bx > ax) { const mx = (ax + 34 + bx - 34) / 2 + off; return [[ax + 34, ay], [mx, ay], [mx, by], [bx - 34, by]]; }
    const mx = (ax - 34 + bx + 34) / 2 + off; return [[ax - 34, ay], [mx, ay], [mx, by], [bx + 34, by]];
  }
  const cy = chanBase - 10 * idx; return [[ax, a.ty], [ax, cy], [bx, cy], [bx, b.ty - 4]];
}
function pointAt(pts, frac) {
  const segs = pts.slice(0, -1).map((p, i) => [p, pts[i + 1], Math.abs(pts[i + 1][0] - p[0]) + Math.abs(pts[i + 1][1] - p[1])]);
  const want = segs.reduce((a, s) => a + s[2], 0) * frac; let acc = 0;
  for (const [p, q, l] of segs) { if (acc + l >= want && l) { const t = (want - acc) / l; return [p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t]; } acc += l; }
  return pts[pts.length - 1];
}

/* ---------------------------------------------------------------- dibujo SVG */
let legs = [];  // {fid, j, pts, el}
function drawDiagram() {
  const box = $('#svgbox'); clear(box);
  const { tops, pos, W, H: H0 } = layout();
  const flows = (spec.flows || []).filter(f => (f.hops || []).every(h => byId()[hopId(h)]) && (f.hops || []).length >= 2);
  const top = 70 + Math.min(flows.length, 12) * 10 + 30, cvH = H0 + top + 40;
  const svg = S('svg', { class: 'net', width: W, height: cvH, viewBox: `0 0 ${W} ${cvH}` });
  const defs = S('defs');
  for (const k in C.FLOW_STYLE) defs.append(S('marker', { id: 'm-' + k, viewBox: '0 0 10 10', refX: 9, refY: 5, markerWidth: 7, markerHeight: 7, orient: 'auto-start-reverse' }, S('path', { d: 'M0 0L10 5L0 10z', fill: C.FLOW_STYLE[k][0] })));
  svg.append(defs);
  const g = S('g', { transform: `translate(0,${top})` }); svg.append(g);
  const hdr = S('g', { class: 'hdr' });
  const txt = (x, y, s, size, cls, weight, anchor = 'middle') => S('text', { x, y, 'font-size': size, 'font-weight': weight || 400, class: cls, 'text-anchor': anchor }, s);
  const drawBox = (b, col0) => {
    const dash = (C.SITE_DASH.includes(b.kind) && b.depth === 0) || b.depth > 1 || b.kind === 'dmz';
    const col = b.kind === 'dmz' ? '#EF4444' : col0;
    g.append(S('rect', { x: b.x, y: b.y, width: b.w, height: b.h, rx: b.depth === 0 ? 12 : 8, fill: b.depth === 0 ? col : 'var(--panel)', 'fill-opacity': b.depth === 0 ? .09 : .55, stroke: col, 'stroke-width': b.depth === 0 ? 1.8 : 1.2, 'stroke-dasharray': dash ? '6 5' : null }));
    let tx = b.x + 12;
    if (b.depth === 0) { g.append(S('image', { href: ICONS[C.SITE_ICON[b.kind] || 'box'] || ICONS.box, x: tx, y: b.y + 9, width: 20, height: 20 })); tx += 28; }
    hdr.append(txt(tx, b.y + 24, b.label, 13, 'ink', 700, 'start'));
    const sub = [b.cidr ? mt(b.cidr) : null, b.detail ? mt(b.detail) : null].filter(Boolean).join(' · ');
    if (sub) hdr.append(txt(tx, b.y + 39, sub, 10, 'muted mono', 400, 'start'));
    b.kids.forEach(k => drawBox(k, col0));
  };
  tops.forEach(t => drawBox(t, C.SITE_COLOR[t.kind] || '#64748B'));
  const topsX = tops.map(t => t.x);
  legs = [];
  flows.forEach((f, idx) => {
    const col = (C.FLOW_STYLE[f.kind || 'interno'] || C.FLOW_STYLE.interno)[0], dash = (C.FLOW_STYLE[f.kind || 'interno'] || C.FLOW_STYLE.interno)[1];
    const ids = f.hops.map(hopId);
    ids.slice(0, -1).forEach((a, j) => {
      const pts = route(pos.get(a), pos.get(ids[j + 1]), idx, topsX, -20);
      const ps = pts.map(p => p.join(',')).join(' ');
      const main = S('polyline', { class: 'main', points: ps, stroke: col, 'stroke-width': 1.8, 'stroke-linejoin': 'round', 'stroke-dasharray': dash || null, 'marker-end': `url(#m-${f.kind || 'interno'})`, fill: 'none' });
      const pkt = S('polyline', { class: 'pkt', points: ps, stroke: '#fff', fill: 'none' });
      const leg = S('g', { class: 'flow leg', 'data-f': f.id, 'data-j': j + 1 }, main, pkt);
      leg.addEventListener('click', () => selectFlow(f.id));
      g.append(leg);
      legs.push({ fid: f.id, j: j + 1, pts, el: leg, main, col });
    });
    const first = legs.find(l => l.fid === f.id), [bx, by] = pointAt(first.pts, .3 + (idx % 4) * .13);
    const badge = S('g', { class: 'badge', 'data-f': f.id }, S('circle', { cx: bx, cy: by, r: 10, fill: col, stroke: '#fff', 'stroke-width': 1.5 }), S('text', { x: bx, y: by + 3.6, 'font-size': 10, 'text-anchor': 'middle' }, f.id));
    badge.addEventListener('click', () => selectFlow(f.id));
    g.append(badge);
  });
  g.append(hdr);
  const flowsOf = id => flows.filter(f => f.hops.map(hopId).includes(id)).map(f => f.id).join(' ');
  for (const n of spec.nodes) {
    const p = pos.get(n.id); if (!p) continue;
    const kind = n.kind || 'app', net = C.NET_KINDS.includes(kind), dark = n.tile === 'dark';
    const ng = S('g', { class: 'node', 'data-n': n.id, 'data-flows': flowsOf(n.id) });
    ng.append(S('rect', { x: p.cx - 30, y: p.ty, width: 60, height: 60, rx: net ? 30 : 12, fill: dark ? '#1B3A5C' : 'var(--tile)', stroke: net ? '#EF4444' : (dark ? '#1B3A5C' : 'var(--tileb)'), 'stroke-width': net ? 1.8 : 1, 'stroke-dasharray': net ? '4 3' : null }));
    ng.append(S('image', { href: ICONS[n.icon || 'box'] || ICONS.box, x: p.cx - 17, y: p.ty + 13, width: 34, height: 34 }));
    let y = p.ty + 76;
    for (const ln of wrap(n.name, 21, 2)) { ng.append(txt(p.cx, y, ln, 12.5, 'ink', 600)); y += 14; }
    if (n.role) { ng.append(txt(p.cx, y + 1, wrap(mt(n.role), 28, 1)[0], 9.5, 'muted mono')); y += 13; }
    const ip = n.ip || n.host, port = n.port ? ':' + n.port : '';
    if (ip || !['user', 'external', 'saas'].includes(kind)) ng.append(txt(p.cx, y + 1, ip ? mt(ip) + port : 'IP por confirmar', 10, ip ? 'ink mono' : 'unk', ip ? 600 : 400));
    g.append(ng);
  }
  svg.append(S('circle', { id: 'pk', r: 7, class: 'pk', cx: -50, cy: -50 }));
  box.append(svg);
  applySel();
}

/* ---------------------------------------------------------------- selección + animación */
function applySel() {
  const svg = $('#svgbox svg'); if (!svg) return;
  svg.classList.toggle('sel', !!selFlow);
  svg.querySelectorAll('.leg,.badge').forEach(e => e.classList.toggle('on', e.dataset.f === selFlow));
  svg.querySelectorAll('.node').forEach(e => e.classList.toggle('on', !!selFlow && (' ' + e.dataset.flows + ' ').includes(' ' + selFlow + ' ')));
  document.querySelectorAll('.chip[data-f]').forEach(e => e.classList.toggle('on', e.dataset.f === selFlow));
  $('#allchip').classList.toggle('on', !selFlow);
  document.querySelectorAll('.flowdetail').forEach(e => e.classList.toggle('on', e.dataset.f === selFlow));
  $('#all').style.display = selFlow ? 'none' : 'block';
  $('#player').style.display = selFlow ? 'flex' : 'none';
  startPlayer();
}
function selectFlow(id) { selFlow = (selFlow === id) ? null : id; applySel(); }
function startPlayer() {
  cancelAnimationFrame(raf);
  const pk = $('#pk'), cap = $('#cap'); if (!pk) return;
  pk.style.opacity = 0;
  const L = legs.filter(l => l.fid === selFlow);
  svgLegs(null);
  if (!selFlow || !L.length) { cap.textContent = ''; return; }
  const nodes = byId(), f = spec.flows.find(x => x.id === selFlow);
  const ids = f.hops.map(hopId);
  let i = 0, t0 = performance.now(), hold = 0;
  const caption = j => { const a = nodes[ids[j]], b = nodes[ids[j + 1]], lab = hopLabel(f.hops[j + 1]) || f.protocol || ''; cap.textContent = `Salto ${f.id}.${j + 1} de ${L.length} · ${a.name} → ${b.name}${lab ? ' · ' + lab : ''}${(f.via || {})[String(j + 1)] ? ' · vía ' + mt(f.via[String(j + 1)]) : ''}`; };
  const frame = t => {
    raf = requestAnimationFrame(frame);
    if (paused || reduce) { if (reduce) { svgLegs(null); pk.style.opacity = 0; caption(0); } return; }
    if (hold) { if (t < hold) return; hold = 0; i = 0; t0 = t; }
    const leg = L[i], len = leg.main.getTotalLength(), dur = Math.max(800, len * 3.4), p = Math.min(1, (t - t0) / dur);
    const e = p < .5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2;
    const [x, y] = pointAt(leg.pts, e);
    pk.setAttribute('cx', x); pk.setAttribute('cy', y); pk.setAttribute('fill', leg.col); pk.style.opacity = 1;
    svgLegs(leg); caption(i);
    if (p >= 1) { i++; t0 = t; if (i >= L.length) { hold = t + 1100; pk.style.opacity = 0; } }
  };
  raf = requestAnimationFrame(frame);
}
function svgLegs(active) { legs.forEach(l => l.el.classList.toggle('act', l === active)); }

/* ---------------------------------------------------------------- tablas de la vista diagrama */
function ipText(n) { const ip = n.ip || n.host; return ip ? mt(ip) + (n.port ? ':' + n.port : '') : ''; }
function whereOf(n) {
  const s = spec.sites.find(x => x.id === n.site), g = (spec.segments || []).find(x => x.id === n.segment);
  return [s && s.label, g && g.label].filter(Boolean).join(' › ');
}
function drawTables() {
  const nodes = byId(), flows = spec.flows || [];
  const chips = $('#chips'); clear(chips);
  flows.forEach(f => {
    const col = (C.FLOW_STYLE[f.kind || 'interno'] || C.FLOW_STYLE.interno)[0];
    chips.append(H('button', { class: 'chip', 'data-f': f.id, onclick: () => selectFlow(f.id) }, H('span', { class: 'dot', style: `background:${col}` }), `${f.id} · ${f.label || ''}`));
  });
  const all = $('#all'); clear(all);
  const t = H('table', {}, H('tr', {}, ['#', 'Flujo', 'Tipo', 'Integración', 'Protocolo', 'Recorrido'].map(x => H('th', {}, x))));
  flows.forEach(f => {
    const ids = (f.hops || []).map(hopId).filter(i => nodes[i]);
    t.append(H('tr', {}, H('td', {}, H('b', {}, f.id)), H('td', {}, f.label || ''), H('td', {}, C.FLOW_LABEL[f.kind || 'interno'] || ''), H('td', {}, f.integration || '—'), H('td', { class: 'mono' }, f.protocol || '—'), H('td', {}, ids.map(i => nodes[i].name).join(' → '))));
  });
  all.append(t, H('p', { class: 'hint' }, 'Haz clic en un flujo (botón, línea o número) para resaltarlo y verlo en movimiento.'));
  const det = $('#details'); clear(det);
  flows.forEach(f => {
    const ids = (f.hops || []).map(hopId); if (ids.some(i => !nodes[i])) return;
    const tb = H('table', {}, H('tr', {}, ['Salto', 'Origen', 'IP origen', 'Destino', 'IP destino', 'Puerto / protocolo', 'Vía'].map(x => H('th', {}, x))));
    ids.slice(0, -1).forEach((a, j) => {
      const na = nodes[a], nb = nodes[ids[j + 1]];
      tb.append(H('tr', {}, H('td', {}, `${f.id}.${j + 1}`), H('td', {}, na.name, H('br'), H('span', { class: 'hint' }, whereOf(na))), H('td', { class: 'mono' }, ipText(na) || 'por confirmar'),
        H('td', {}, nb.name, H('br'), H('span', { class: 'hint' }, whereOf(nb))), H('td', { class: 'mono' }, ipText(nb) || 'por confirmar'), H('td', { class: 'mono' }, hopLabel(f.hops[j + 1]) || f.protocol || '—'), H('td', {}, mt((f.via || {})[String(j + 1)] || '') || '—')));
    });
    const d = H('div', { class: 'flowdetail', 'data-f': f.id }, H('h3', {}, `${f.id} · ${f.label || ''}${f.integration ? ' — ' + f.integration : ''}`), tb);
    if (f.note) d.append(H('p', { class: 'hint' }, f.note));
    det.append(d);
  });
  const inv = $('#inv'); clear(inv);
  const it = H('table', {}, H('tr', {}, ['Sitio › Segmento', 'CIDR', 'Componentes'].map(x => H('th', {}, x))));
  const groups = new Map();
  spec.nodes.forEach(n => { const k = (n.site || '') + '|' + (n.segment || ''); if (!groups.has(k)) groups.set(k, []); groups.get(k).push(n); });
  groups.forEach(ns => { const sg = (spec.segments || []).find(x => x.id === ns[0].segment); it.append(H('tr', {}, H('td', {}, whereOf(ns[0]) || '— sin sitio —'), H('td', { class: 'mono' }, sg && sg.cidr ? mt(sg.cidr) : ''), H('td', {}, ns.map(n => n.name).join(', ')))); });
  inv.append(it);
  const { errs, pend } = check();
  $('#tabform').textContent = 'Completar datos' + (pend.length ? ` (${pend.length})` : ' ✓');
  const pe = $('#pend'); clear(pe);
  if (errs.length) pe.append(H('p', { class: 'hint', style: 'color:#EF4444' }, 'Errores: ' + errs.join(' · ')));
  if (pend.length) {
    pe.append(H('h2', {}, `Pendientes por confirmar (${pend.length})`), H('ol', { class: 'q' }, pend.map(p => H('li', {}, mt(p)))),
      H('p', {}, H('button', { class: 'btn', onclick: () => showTab('form') }, 'Completar datos →')));
  } else pe.append(H('p', {}, '✓ Sin pendientes: todos los datos de red están completos.'));
  $('#pendsec').style.display = '';
}

/* ---------------------------------------------------------------- formulario */
function field(label, value, on, opts = {}) {
  const inp = H('input', { type: 'text', value: value || '', placeholder: opts.ph || '', class: opts.req && !(value || '').toString().trim() ? 'miss' : '' });
  inp.addEventListener('input', () => { on(inp.value.trim()); inp.classList.toggle('miss', !!opts.req && !inp.value.trim()); });
  return inp;
}
function select(options, value, on) {
  const s = H('select', {}, options.map(o => H('option', { value: o[0] }, o[1])));
  s.value = value || ''; s.addEventListener('change', () => on(s.value)); return s;
}
function changed(structural) { dirty = true; drawTables(); drawDiagram(); if (structural) drawForm(); autosave(); }
function drawForm() {
  const f = $('#form'); clear(f);
  if (C.locked) { f.append(H('p', { class: 'hint' }, 'Esta copia se generó con --mask-ips: es de solo lectura. Genera una copia sin enmascarar para completar datos.')); return; }
  const nid = () => { let i = 1; while (spec.nodes.some(n => n.id === 'n' + i)) i++; return 'n' + i; };
  const sitesOpt = [['', '— sin definir —'], ...spec.sites.map(s => [s.id, s.label || s.id])];
  /* Sitios */
  f.append(H('h2', {}, '1 · Sitios (dónde corre cada cosa)'));
  const ts = H('table', { class: 'ft' }, H('tr', {}, ['Nombre', 'Tipo', 'Detalle (región / cuenta / ciudad)', ''].map(x => H('th', {}, x))));
  spec.sites.forEach((s, i) => ts.append(H('tr', {}, H('td', {}, field('', s.label, v => { s.label = v; changed(false); })),
    H('td', {}, select(C.SITE_KINDS.map(k => [k, k]), s.kind || 'unknown', v => { s.kind = v; changed(true); })),
    H('td', {}, field('', s.detail, v => { s.detail = v; changed(false); }, { ph: 'sa-east-1 · cuenta prod' })),
    H('td', {}, H('button', { class: 'x', title: 'Quitar', onclick: () => { if (spec.nodes.some(n => n.site === s.id) && !confirm('Hay componentes en este sitio. ¿Quitarlo igual?')) return; spec.sites.splice(i, 1); changed(true); } }, '✕')))));
  f.append(ts, H('button', { class: 'btn', onclick: () => { let k = 1; while (spec.sites.some(s => s.id === 's' + k)) k++; spec.sites.push({ id: 's' + k, label: 'Nuevo sitio', kind: 'unknown' }); changed(true); } }, '+ Sitio'));
  /* Segmentos */
  f.append(H('h2', {}, '2 · Segmentos de red (VPC / VNet / subred / VLAN)'));
  const tg = H('table', { class: 'ft' }, H('tr', {}, ['Nombre', 'Sitio', 'Dentro de', 'Tipo', 'CIDR', ''].map(x => H('th', {}, x))));
  (spec.segments = spec.segments || []).forEach((g, i) => tg.append(H('tr', {}, H('td', {}, field('', g.label, v => { g.label = v; changed(false); })),
    H('td', {}, select(sitesOpt, g.site, v => { g.site = v; changed(true); })),
    H('td', {}, select([['', '— (raíz del sitio) —'], ...spec.segments.filter(x => x !== g).map(x => [x.id, x.label || x.id])], g.parent, v => { g.parent = v || undefined; changed(true); })),
    H('td', {}, select(C.SEG_KINDS.map(k => [k, k]), g.kind || 'subnet', v => { g.kind = v; changed(false); })),
    H('td', {}, field('', g.cidr, v => { g.cidr = v; changed(false); }, { req: true, ph: '10.20.4.0/24' })),
    H('td', {}, H('button', { class: 'x', onclick: () => { spec.nodes.forEach(n => { if (n.segment === g.id) n.segment = ''; }); spec.segments.splice(i, 1); changed(true); } }, '✕')))));
  f.append(tg, H('button', { class: 'btn', onclick: () => { let k = 1; while (spec.segments.some(s => s.id === 'g' + k)) k++; spec.segments.push({ id: 'g' + k, label: 'Nuevo segmento', site: (spec.sites[0] || {}).id, kind: 'subnet', cidr: '' }); changed(true); } }, '+ Segmento'));
  /* Componentes */
  f.append(H('h2', {}, '3 · Componentes: sitio, segmento y dirección exacta'));
  f.append(H('p', { class: 'hint' }, 'Rojo = falta. Pon la IP exacta (o el hostname/URL si es un servicio gestionado) y el puerto. Los cambios se ven al instante en el diagrama.'));
  const tc = H('table', { class: 'ft' }, H('tr', {}, ['Componente', 'Tipo', 'Sitio', 'Segmento', 'IP exacta', 'Host / URL', 'Puerto', 'Detalle', ''].map(x => H('th', {}, x))));
  spec.nodes.forEach((n, i) => {
    const isNet = C.NET_KINDS.includes(n.kind), needIp = !['user', 'external', 'saas'].includes(n.kind || 'app');
    const segOpts = [['', '—'], ...spec.segments.filter(g => g.site === n.site).map(g => [g.id, g.label || g.id])];
    tc.append(H('tr', {}, H('td', {}, field('', n.name, v => { n.name = v; changed(false); })),
      H('td', {}, select(C.KINDS.map(k => [k, k]), n.kind || 'app', v => { n.kind = v; changed(true); })),
      H('td', {}, select(sitesOpt, n.site, v => { n.site = v; if (!spec.segments.some(g => g.id === n.segment && g.site === v)) n.segment = ''; changed(true); })),
      H('td', {}, select(segOpts, n.segment, v => { n.segment = v; changed(false); })),
      H('td', {}, field('', n.ip, v => { n.ip = v; changed(false); }, { req: needIp && !n.host, ph: '10.20.4.22' })),
      H('td', {}, field('', n.host, v => { n.host = v; changed(false); }, { ph: 'api.interno / https://…' })),
      H('td', { class: 'num' }, field('', n.port, v => { n.port = v ? (isNaN(+v) ? v : +v) : undefined; changed(false); }, { ph: '443' })),
      H('td', {}, field('', n.role, v => { n.role = v; changed(false); }, { ph: 'rol / tecnología' })),
      H('td', {}, H('button', { class: 'x', onclick: () => { spec.nodes.splice(i, 1); spec.flows = (spec.flows || []).filter(fl => !fl.hops.map(hopId).includes(n.id)); changed(true); } }, '✕'))));
  });
  f.append(tc, H('button', { class: 'btn', onclick: () => { spec.nodes.push({ id: nid(), name: 'Nuevo componente', icon: 'box', site: '', kind: 'app' }); changed(true); } }, '+ Componente'));
  /* Flujos */
  f.append(H('h2', {}, '4 · Flujos e integraciones: nombre, puerto y elementos de red en el camino'));
  const nodes = byId();
  (spec.flows || []).forEach(fl => {
    const ids = fl.hops.map(hopId); if (ids.some(i => !nodes[i])) return;
    const card = H('div', { class: 'fcard' }, H('div', { class: 'frow' }, H('b', {}, `Flujo ${fl.id}`), field('', fl.label, v => { fl.label = v; changed(false); }, { ph: 'descripción' }),
      field('', fl.integration, v => { fl.integration = v; changed(false); }, { ph: 'Nombre de la integración (iFlow, API, job…)' }),
      field('', fl.protocol, v => { fl.protocol = v; changed(false); }, { req: !fl.protocol && !fl.hops.some(hopLabel), ph: 'Protocolo y puerto (HTTPS 443)' })));
    ids.slice(0, -1).forEach((a, j0) => {
      const na = nodes[a], nb = nodes[ids[j0 + 1]], cross = na.site !== nb.site && !C.NET_KINDS.includes(na.kind) && !C.NET_KINDS.includes(nb.kind);
      const viaV = (fl.via || {})[String(j0 + 1)] || '';
      card.append(H('div', { class: 'frow hop' }, H('span', { class: 'hint' }, `${fl.id}.${j0 + 1}  ${na.name} → ${nb.name}`),
        field('', hopLabel(fl.hops[j0 + 1]), v => { const h = fl.hops[j0 + 1]; fl.hops[j0 + 1] = typeof h === 'string' ? { id: h, label: v } : { ...h, label: v }; changed(false); }, { ph: 'puerto de este salto (opcional)' }),
        field('', viaV, v => { fl.via = fl.via || {}; v ? fl.via[String(j0 + 1)] = v : delete fl.via[String(j0 + 1)]; changed(false); }, { req: cross, ph: cross ? '¿Firewall / VPN / proxy en medio? nombre o IP' : 'elemento de red en medio (opcional)' })));
    });
    f.append(card);
  });
  /* Preguntas generales */
  f.append(H('h2', {}, '5 · Preguntas generales'));
  spec.questions = spec.questions || [];
  spec.questions.forEach(q => { const ta = H('textarea', { rows: 2, placeholder: 'Respuesta…' }); ta.value = q.answer || ''; ta.addEventListener('input', () => { q.answer = ta.value; dirty = true; autosave(); drawTables(); });
    f.append(H('div', { class: 'qa' }, H('label', {}, q.text), ta)); });
  f.append(H('button', { class: 'btn', onclick: () => { const t = prompt('Escribe la pregunta:'); if (t) { spec.questions.push({ id: 'q' + Date.now(), text: t, answer: '' }); changed(true); } } }, '+ Pregunta'));
}

/* ---------------------------------------------------------------- guardado */
const KEY = 'tdocs-arq:' + (spec.title || '');
function autosave() { clearTimeout(saveTimer); saveTimer = setTimeout(() => { try { localStorage.setItem(KEY, JSON.stringify(spec)); } catch (e) {} setStatus('Borrador guardado en este navegador (aún no en el archivo)'); }, 400); }
function setStatus(t) { $('#status').textContent = t; }
function cleanSpec() { const s = JSON.parse(JSON.stringify(spec)); s.savedAt = new Date().toISOString(); return s; }
function download(name, text, mime) { const a = H('a', { href: URL.createObjectURL(new Blob([text], { type: mime })), download: name }); document.body.append(a); a.click(); a.remove(); }
async function saveHtml() {
  const s = cleanSpec(); spec.savedAt = s.savedAt;
  $('#spec').textContent = JSON.stringify(s).replace(/<\//g, '<\\/');
  const banner = $('#draftbar'); const was = banner.style.display; banner.style.display = 'none';
  const html = '<!doctype html>\n' + document.documentElement.outerHTML; banner.style.display = was;
  try {
    if (window.showSaveFilePicker) {
      const h = await showSaveFilePicker({ suggestedName: 'arquitectura.html', types: [{ description: 'HTML', accept: { 'text/html': ['.html'] } }] });
      const w = await h.createWritable(); await w.write(html); await w.close();
      setStatus('Guardado en ' + h.name + ' ✓ (los datos quedan dentro del HTML)');
    } else { download('arquitectura.html', html, 'text/html'); setStatus('Descargado arquitectura.html con tus datos ✓ (reemplaza el original)'); }
    dirty = false; try { localStorage.removeItem(KEY); } catch (e) {}
  } catch (e) { if (e && e.name !== 'AbortError') { download('arquitectura.html', html, 'text/html'); setStatus('Descargado arquitectura.html con tus datos ✓'); } }
}
function exportJson() { download('network.json', JSON.stringify(cleanSpec(), null, 2), 'application/json'); setStatus('network.json exportado: pásaselo a la skill (docs/spec/network.json) y ejecuta «tdocs net»'); }

/* ---------------------------------------------------------------- pestañas / arranque */
function showTab(t) {
  document.querySelectorAll('.tabv').forEach(e => e.classList.toggle('on', e.dataset.v === t));
  document.querySelectorAll('.tabs button').forEach(b => b.classList.toggle('on', b.dataset.v === t));
  if (t === 'form') drawForm();
}
function init() {
  $('#title').textContent = spec.title || 'Arquitectura';
  $('#sub').textContent = spec.subtitle || '';
  if (spec.env) { $('#env').textContent = spec.env; $('#env').style.display = ''; }
  document.title = spec.title || 'Arquitectura';
  $('#allchip').onclick = () => { selFlow = null; applySel(); };
  $('#pause').onclick = () => { paused = !paused; $('#pause').textContent = paused ? '▶ Reanudar' : '⏸ Pausar'; };
  $('#replay').onclick = () => { startPlayer(); };
  document.querySelectorAll('.tabs button').forEach(b => b.onclick = () => showTab(b.dataset.v));
  if (C.locked) { $('#mask').style.display = 'none'; $('#savebar').style.display = 'none'; } else {
    $('#mask').onclick = () => { mask = !mask; $('#mask').classList.toggle('on', mask); drawTables(); drawDiagram(); };
    $('#savehtml').onclick = saveHtml; $('#savejson').onclick = exportJson;
    $('#discard').onclick = () => { try { localStorage.removeItem(KEY); } catch (e) {} $('#draftbar').style.display = 'none'; };
    try {
      const d = localStorage.getItem(KEY);
      if (d) { $('#draftbar').style.display = 'flex'; $('#restore').onclick = () => { spec = JSON.parse(d); $('#draftbar').style.display = 'none'; drawTables(); drawDiagram(); drawForm(); setStatus('Borrador restaurado'); }; }
    } catch (e) {}
  }
  drawTables(); drawDiagram();
  window.addEventListener('beforeunload', e => { if (dirty && !C.locked) { e.preventDefault(); e.returnValue = ''; } });
  const h = location.hash.slice(1); showTab(h === 'form' ? 'form' : 'diagram');
}
init();
})();
