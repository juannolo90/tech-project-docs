"""Paso 3b · Arquitectura de red y despliegue: network.json -> arquitectura.html (interactivo, editable, flujos animados) + arquitectura-red.svg + arquitectura-red-pendientes.md.

Muestra DÓNDE vive cada componente (sitio: on-prem / AWS / Azure / SAP / SaaS / Internet), en qué SEGMENTO (VPC, VNet, subred,
VLAN, CIDR), con qué IP/puerto, y por qué elementos de red pasa cada flujo (firewall, gateway, VPN, balanceador, proxy…).
Lo que falta se lista como «pendiente por confirmar» (el agente debe PREGUNTARLO al usuario, nunca inventarlo).

Subcomandos (vía tdocs.py):  net-init  (borrador desde graph.json)  ·  net  (renderiza)
"""
import collections, copy, json, pathlib, re
from common import load_theme, read_json, write, esc, wrap, icon_uri, ICON_SOURCES, MONO, SANS

IP4 = re.compile(r"(?<![\w.])((?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3})(?![\w]|\.\d)")
CELLW, CELLH, PAD, GAP = 170, 138, 18, 120
SITE_COLOR = {"aws": "#E8811A", "azure": "#2C7BC4", "sap": "#0A6ED1", "onprem": "#B7791F", "saas": "#6366F1", "gcp": "#2E7D32",
              "internet": "#94A3B8", "users": "#C2410C", "unknown": "#EF4444"}
SITE_DASH = {"internet", "unknown"}
SITE_ICON = {"aws": "amazonwebservices", "azure": "azure", "sap": "sap", "onprem": "server", "saas": "cloud", "gcp": "googlecloud",
             "internet": "cloud", "users": "users", "unknown": "box"}
NET_KINDS = {"network", "firewall", "gateway", "vpn", "lb", "proxy", "router", "dns"}
FLOW_STYLE = {  # kind -> (color, dash)
    "principal": ("#E8811A", ""), "interno": ("#2C5282", ""), "batch": ("#2C5282", "7 5"), "externo": ("#7C3AED", "7 5"),
    "referencia": ("#64748B", "2 5"), "riesgo": ("#EF4444", "7 5"),
}
FLOW_LABEL = {"principal": "flujo principal", "interno": "interno", "batch": "batch / programado", "externo": "hacia externo",
              "referencia": "referencia", "riesgo": "riesgo"}


def mask_ip(ip):
    p = ip.split(".")
    return f"{p[0]}.{p[1]}.x.x"


def mask_text(s):
    return IP4.sub(lambda m: mask_ip(m.group(1)), s)


# ------------------------------------------------------------------ modelo
def hop_id(h):
    return h if isinstance(h, str) else h["id"]


def hop_label(h):
    return "" if isinstance(h, str) else h.get("label", "")


def check(spec):
    """Devuelve (errores, pendientes). Los pendientes son PREGUNTAS para el usuario."""
    errs, pend = [], []
    nodes = {n["id"]: n for n in spec.get("nodes", [])}
    sites = {s["id"]: s for s in spec.get("sites", [])}
    segs = {s["id"]: s for s in spec.get("segments", [])}
    for n in nodes.values():
        nm = n["name"]
        kind = n.get("kind", "app")
        site = sites.get(n.get("site"))
        if not site:
            errs.append(f"nodo «{nm}»: sitio '{n.get('site')}' no existe en sites") if n.get("site") else \
                pend.append(f"¿En qué sitio está «{nm}»? (on-prem, AWS, Azure, SAP, SaaS, otro)")
            continue
        if n.get("segment") and n["segment"] not in segs:
            errs.append(f"nodo «{nm}»: segmento '{n['segment']}' no existe")
        if site.get("kind") == "unknown":
            pend.append(f"¿En qué sitio está «{nm}»? (hoy figura en «{site.get('label')}»)")
        if kind not in ("user", "external", "saas") and site.get("kind") not in ("saas", "internet", "users") and not (n.get("ip") or n.get("host")):
            pend.append(f"¿Cuál es la IP u hostname de «{nm}»?")
        if site.get("kind") in ("aws", "azure", "gcp", "onprem") and kind != "user" and kind not in NET_KINDS and not n.get("segment"):
            pend.append(f"¿En qué VPC/VNet/subred/VLAN está «{nm}»?")
    for s in segs.values():
        if not s.get("cidr"):
            pend.append(f"¿Cuál es el CIDR del segmento «{s.get('label', s['id'])}»?")
        if s.get("site") not in sites:
            errs.append(f"segmento «{s.get('label', s['id'])}»: sitio '{s.get('site')}' no existe")
    for f in spec.get("flows", []):
        ids = [hop_id(h) for h in f.get("hops", [])]
        miss = [i for i in ids if i not in nodes]
        if miss:
            errs.append(f"flujo {f['id']}: nodos inexistentes {miss}")
            continue
        if len(ids) < 2:
            errs.append(f"flujo {f['id']}: necesita al menos 2 nodos en hops")
        if not f.get("protocol") and not any(hop_label(h) for h in f.get("hops", [])):
            pend.append(f"Flujo {f['id']} «{f.get('label', '')}»: ¿qué protocolo y puerto usa?")
        for j, (a, b) in enumerate(zip(ids, ids[1:]), 1):
            na, nb = nodes[a], nodes[b]
            via = ((f.get("via") or {}).get(str(j)) or "").strip()
            if na.get("site") != nb.get("site") and na.get("kind") not in NET_KINDS and nb.get("kind") not in NET_KINDS and not via:
                pend.append(f"Flujo {f['id']}: «{na['name']}» → «{nb['name']}» cruza de sitio; ¿hay firewall, VPN/Direct Connect/ExpressRoute, "
                            f"proxy o balanceador en medio? ¿qué reglas lo permiten?")
    pend += [q["text"] for q in spec.get("questions", []) if not (q.get("answer") or "").strip()]
    pend += [p for p in spec.get("pending", [])]
    seen, out = set(), []
    for p in pend:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return errs, out


# ------------------------------------------------------------------ layout
class Box:
    def __init__(self, id_, label, kind, depth, cidr="", detail="", cols=None):
        self.id, self.label, self.kind, self.depth, self.cidr, self.detail, self.cols = id_, label, kind, depth, cidr, detail, cols
        self.nodes, self.kids = [], []
        self.x = self.y = self.w = self.h = 0

    def header(self):
        return 46 if self.depth == 0 else 40

    def measure(self):
        for k in self.kids:
            k.measure()
        n = len(self.nodes)
        cols = self.cols or (min(n, 2) if self.depth == 0 else min(n, 3))
        self.ncols = max(cols, 1)
        rows = -(-n // self.ncols) if n else 0
        nw, nh = self.ncols * CELLW if n else 0, rows * CELLH
        kw = max([k.w for k in self.kids] + [0])
        self.w = max(nw, kw, 190) + 2 * PAD
        self.h = self.header() + nh + sum(k.h for k in self.kids) + 12 * len(self.kids) + PAD
        self.nh = nh

    def place(self, x, y, w=None):
        self.x, self.y = x, y
        if w:
            self.w = w
        n = len(self.nodes)
        nw = min(n, self.ncols) * CELLW
        ox = x + (self.w - nw) / 2
        for i, nd in enumerate(self.nodes):
            nd["_cx"] = ox + (i % self.ncols) * CELLW + CELLW / 2
            nd["_ty"] = y + self.header() + (i // self.ncols) * CELLH + 6
        cy = y + self.header() + self.nh + (12 if self.kids else 0)
        for k in self.kids:
            k.place(x + PAD, cy, self.w - 2 * PAD)
            cy += k.h + 12


def build(spec):
    sites = {s["id"]: Box(s["id"], s.get("label", s["id"]), s.get("kind", "unknown"), 0, detail=s.get("detail", ""), cols=s.get("cols"))
             for s in spec.get("sites", [])}
    segs = {}
    for s in spec.get("segments", []):
        segs[s["id"]] = Box(s["id"], s.get("label", s["id"]), s.get("kind", "subnet"), 1, s.get("cidr", ""), s.get("detail", ""), s.get("cols"))
    for s in spec.get("segments", []):
        b = segs[s["id"]]
        par = segs.get(s.get("parent")) or sites.get(s.get("site"))
        if par is not None:
            b.depth = (par.depth + 1)
            b.site_kind = None
            par.kids.append(b)
    for n in spec.get("nodes", []):
        holder = segs.get(n.get("segment")) or sites.get(n.get("site"))
        if holder is None:  # sin sitio: va a un sitio «unknown» implícito
            holder = sites.setdefault("_unknown", Box("_unknown", "Sitio por confirmar", "unknown", 0))
        holder.nodes.append(n)
    tops = list(sites.values())
    tops = [t for t in tops if t.nodes or t.kids or t.id != "_unknown"]
    for t in tops:
        t.measure()
    H = max([t.h for t in tops] + [260])
    x = 30
    for t in tops:
        t.place(x, 0, t.w)
        x += t.w + GAP
    return tops, segs, x - GAP + 30, H


# ------------------------------------------------------------------ SVG
CSS = f"""
.net{{font-family:{SANS};}}
.net .ink{{fill:var(--ink)}} .net .muted{{fill:var(--muted)}} .net .mono{{font-family:{MONO}}}
.net .flow{{fill:none;transition:opacity .15s}} .net .badge text{{fill:#fff;font-weight:700}}
.net.sel .flow,.net.sel .badge{{opacity:.10}} .net.sel .flow.on,.net.sel .badge.on{{opacity:1}} .net.sel .flow.on path{{stroke-width:3}}
.net.sel .node{{opacity:.35}} .net.sel .node.on{{opacity:1}}
.net .flow{{cursor:pointer}} .net .badge{{cursor:pointer}}
.net .unk{{fill:#EF4444;font-style:italic}}
.net .pkt{{fill:none;stroke:#fff;stroke-linecap:round;stroke-width:3.4;stroke-dasharray:.1 15;animation:flow 1.1s linear infinite;opacity:.7}}
@keyframes flow{{to{{stroke-dashoffset:-15.1}}}} @media (prefers-reduced-motion:reduce){{.net .pkt{{animation:none}}}}
.net text{{paint-order:stroke;stroke:var(--panel);stroke-width:3.5px;stroke-linejoin:round}} .net .badge text{{stroke:none}}
"""
NETDASH = ' stroke-dasharray="4 3"'
LIGHT = "--ink:#1B3A5C;--muted:#64748B;--panel:#FFFFFF;--tile:#FFFFFF;--tileb:#CBD5E1;--bg:#FFFFFF"


def ipspan(val, mask, fallback="IP por confirmar"):
    if not val:
        return f'<tspan class="unk">{fallback}</tspan>'
    if mask:
        return esc(mask_text(str(val)))
    return f'<tspan class="ip" data-f="{esc(val)}" data-m="{esc(mask_text(str(val)))}">{esc(val)}</tspan>'


def text(x, y, s, size=12, cls="ink", weight=400, anchor="middle", extra=""):
    return f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-weight="{weight}" class="{cls}" text-anchor="{anchor}"{extra}>{s}</text>'


def route(a, b, idx, tops_x, chan_base):
    """Puntos ortogonales entre dos nodos. Mismos sitio/adyacentes: codo por el pasillo; saltos largos: canal superior."""
    ax, ay = a["_cx"], a["_ty"] + 30
    bx, by = b["_cx"], b["_ty"] + 30
    off = ((idx % 7) - 3) * 6
    if abs(ax - bx) < CELLW * 1.25:  # columnas cercanas: pasillo lateral derecho (no cruza etiquetas)
        gx = max(ax, bx) + 78 + off
        return [(ax + 34, ay), (gx, ay), (gx, by), (bx + 34, by)]
    sa = max((i for i, x in enumerate(tops_x) if x <= ax), default=0)
    sb = max((i for i, x in enumerate(tops_x) if x <= bx), default=0)
    if abs(sa - sb) <= 1:
        if bx > ax:
            mx = (ax + 34 + bx - 34) / 2 + off
            return [(ax + 34, ay), (mx, ay), (mx, by), (bx - 34, by)]
        mx = (ax - 34 + bx + 34) / 2 + off
        return [(ax - 34, ay), (mx, ay), (mx, by), (bx + 34, by)]
    cy = chan_base - 10 * idx
    return [(ax, a["_ty"]), (ax, cy), (bx, cy), (bx, b["_ty"] - 4)]


def point_at(pts, frac):
    segs = [(pts[i], pts[i + 1], abs(pts[i + 1][0] - pts[i][0]) + abs(pts[i + 1][1] - pts[i][1])) for i in range(len(pts) - 1)]
    want, acc = sum(l for _, _, l in segs) * frac, 0
    for (x1, y1), (x2, y2), l in segs:
        if acc + l >= want and l:
            t = (want - acc) / l
            return x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
        acc += l
    return pts[-1]


def render_svg(spec, theme, icons_dir, mask, standalone):
    tops, segs, W, H = build(spec)
    nodes = {n["id"]: n for n in spec.get("nodes", [])}
    for n in nodes.values():
        n.setdefault("_cx", 100)
        n.setdefault("_ty", 100)
    flows = spec.get("flows", [])
    top = 70 + min(len(flows), 12) * 10 + 30
    cvH = H + top + 40
    tops_x = [t.x for t in tops]
    o = [f'<svg class="net" xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{cvH:.0f}" viewBox="0 0 {W:.0f} {cvH:.0f}"'
         + (f' style="{LIGHT}"' if standalone else "") + ">"]
    o.append("<style>" + CSS + "</style><defs>")
    for k, (c, _) in FLOW_STYLE.items():
        o.append(f'<marker id="m-{k}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
                 f'<path d="M0 0L10 5L0 10z" fill="{c}"/></marker>')
    o.append("</defs>")
    if standalone:
        o.append(f'<rect width="{W:.0f}" height="{cvH:.0f}" fill="#FFFFFF"/>')
    o.append(f'<g transform="translate(0,{top})">')

    hdr = []

    def draw_box(b, site_col):
        dash = ' stroke-dasharray="6 5"' if (b.kind in SITE_DASH and b.depth == 0) or (b.depth > 1) or b.kind == "dmz" else ""
        col = "#EF4444" if b.kind == "dmz" else site_col
        fo = ".09" if b.depth == 0 else ".55"
        fill = col if b.depth == 0 else "var(--panel)"
        o.append(f'<g class="box"><rect x="{b.x:.1f}" y="{b.y:.1f}" width="{b.w:.1f}" height="{b.h:.1f}" rx="{12 if b.depth == 0 else 8}" '
                 f'fill="{fill}" fill-opacity="{fo}" stroke="{col}" stroke-width="{1.8 if b.depth == 0 else 1.2}"{dash}/>')
        tx = b.x + 12
        if b.depth == 0:
            o.append(f'<image href="{icon_uri(SITE_ICON.get(b.kind, "box"), theme, icons_dir)}" x="{tx}" y="{b.y + 9}" width="20" height="20"/>')
            tx += 28
        hdr.append(text(tx, b.y + 24, esc(b.label), 13, "ink", 700, "start"))
        sub = []
        if b.cidr:
            sub.append(ipspan(b.cidr, mask))
        if b.detail:
            sub.append(esc(mask_text(b.detail) if mask else b.detail))
        if sub:
            hdr.append(text(tx, b.y + 39, " · ".join(sub), 10, "muted mono", 400, "start"))
        o.append("</g>")
        for k in b.kids:
            draw_box(k, site_col)

    for t in tops:
        draw_box(t, SITE_COLOR.get(t.kind, "#64748B"))

    # flujos (debajo de los nodos)
    ch_base = -20
    for idx, f in enumerate(flows):
        ids = [hop_id(h) for h in f.get("hops", [])]
        if any(i not in nodes for i in ids):
            continue
        col, dash = FLOW_STYLE.get(f.get("kind", "interno"), FLOW_STYLE["interno"])
        d = f' stroke-dasharray="{dash}"' if dash else ""
        fid = esc(f["id"])
        o.append(f'<g class="flow" data-f="{fid}">')
        badges = []
        for j, (a, b) in enumerate(zip(ids, ids[1:])):
            pts = route(nodes[a], nodes[b], idx, tops_x, ch_base)
            ps = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
            o.append(f'<polyline points="{ps}" stroke="{col}" stroke-width="1.8" stroke-linejoin="round"{d} marker-end="url(#m-{f.get("kind", "interno")})" fill="none"/>')
            o.append(f'<polyline class="pkt" points="{ps}"/>')
            bx, by = point_at(pts, 0.3 + (idx % 4) * 0.13)
            badges.append((bx, by, col))
        o.append("</g>")
        o.append(f'<g class="badge" data-f="{fid}">' + "".join(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="10" fill="{c}" stroke="#fff" stroke-width="1.5"/>'
            f'<text x="{x:.1f}" y="{y + 3.6:.1f}" font-size="10" text-anchor="middle">{fid}</text>' for x, y, c in badges[:1]) + "</g>")

    o.append('<g class="hdr">' + "".join(hdr) + "</g>")
    # nodos
    for n in spec.get("nodes", []):
        cx, ty = n["_cx"], n["_ty"]
        kind = n.get("kind", "app")
        net = kind in NET_KINDS
        fl = " ".join(esc(f["id"]) for f in flows if n["id"] in [hop_id(h) for h in f.get("hops", [])])
        o.append(f'<g class="node" data-n="{esc(n["id"])}" data-flows="{fl}">')
        dark = n.get("tile") == "dark"
        stroke = "#EF4444" if net else ("#1B3A5C" if dark else "var(--tileb)")
        o.append(f'<rect x="{cx - 30:.1f}" y="{ty:.1f}" width="60" height="60" rx="{30 if net else 12}" fill="{"#1B3A5C" if dark else "var(--tile)"}" '
                 f'stroke="{stroke}" stroke-width="{1.8 if net else 1}"{NETDASH if net else ""}/>')
        o.append(f'<image href="{icon_uri(n.get("icon", "box"), theme, icons_dir)}" x="{cx - 17:.1f}" y="{ty + 13:.1f}" width="34" height="34"/>')
        y = ty + 76
        for ln in wrap(n["name"], 21, 2):
            o.append(text(cx, y, esc(ln), 12.5, "ink", 600))
            y += 14
        if n.get("role"):
            o.append(text(cx, y + 1, esc(wrap(mask_text(n["role"]) if mask else n["role"], 28, 1)[0]), 9.5, "muted mono"))
            y += 13
        ip = n.get("ip") or n.get("host")
        port = f":{n['port']}" if n.get("port") else ""
        if ip or kind not in ("user", "external", "saas"):
            o.append(text(cx, y + 1, ipspan(ip, mask) + (esc(port) if ip else ""), 10, "ink mono", 600))
        o.append("</g>")
    o.append("</g></svg>")
    return "".join(o)


# ------------------------------------------------------------------ HTML (se dibuja en el navegador desde el JSON embebido)
PAGE_CSS = """
:root{--ink:#1B3A5C;--muted:#64748B;--bg:#F8FAFC;--panel:#FFFFFF;--tile:#FFFFFF;--tileb:#CBD5E1;--line:#E2E8F0;--accent:#E8811A}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--ink:#E6EDF6;--muted:#9AA9BC;--bg:#0F1722;--panel:#16202E;--tile:#FFFFFF;--tileb:#475569;--line:#243247}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 Inter,Helvetica,Arial,sans-serif}
header{padding:16px 24px 4px}h1{margin:0;font-size:22px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}header p{margin:2px 0 0;color:var(--muted);font-size:13px}
.tabs{display:flex;gap:4px;padding:8px 24px 0;border-bottom:1px solid var(--line)}
.tabs button{border:0;background:none;color:var(--muted);font:inherit;padding:8px 14px;border-bottom:3px solid transparent;cursor:pointer}
.tabs button.on{color:var(--ink);border-bottom-color:var(--accent);font-weight:600}
.tabv{display:none}.tabv.on{display:block}
.bar{display:flex;flex-wrap:wrap;gap:8px;padding:10px 24px;align-items:center}
.chip,.btn{border:1px solid var(--line);background:var(--panel);color:var(--ink);border-radius:999px;padding:5px 12px;font:inherit;font-size:12.5px;cursor:pointer;display:inline-flex;gap:7px;align-items:center}
.btn{border-radius:8px;margin:6px 0}.btn.pri{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:600}
.chip:hover,.btn:hover{border-color:var(--accent)}.chip.on{background:var(--ink);color:var(--bg);border-color:var(--ink)}
.dot{width:10px;height:10px;border-radius:50%;display:inline-block}.sp{flex:1}
#player{display:none;gap:10px;align-items:center;padding:0 24px 8px;flex-wrap:wrap}#cap{color:var(--muted);font-size:12.5px}
.canvas{overflow:auto;margin:0 24px;border:1px solid var(--line);border-radius:12px;background:var(--panel)}
.canvas svg{display:block;width:100%;min-width:1100px;height:auto}
main{padding:16px 24px 40px;display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(340px,1fr))}
section{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
h2{margin:0 0 8px;font-size:14px}h3{margin:8px 0 4px;font-size:13px}table{border-collapse:collapse;width:100%;font-size:12.5px}
th,td{text-align:left;padding:5px 8px;border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--muted);font-weight:600}
.mono{font-family:'JetBrains Mono',Consolas,monospace;font-size:12px}.q li{margin:4px 0}.q{padding-left:18px;margin:0}
.warn{border-color:#EF4444}.hint{color:var(--muted);font-size:12px}.flowdetail{display:none}.flowdetail.on{display:block}
/* animación de flujos */
.net{font-family:Inter,Helvetica,Arial,sans-serif}.net .ink{fill:var(--ink)}.net .muted{fill:var(--muted)}.net .mono{font-family:'JetBrains Mono',Consolas,monospace}
.net .unk{fill:#EF4444;font-style:italic}.net text{paint-order:stroke;stroke:var(--panel);stroke-width:3.5px;stroke-linejoin:round}.net .badge text{stroke:none;fill:#fff;font-weight:700}
.net .leg,.net .badge{cursor:pointer;transition:opacity .2s}.net .pkt{fill:none;stroke-linecap:round;stroke-width:3.4;stroke-dasharray:.1 15;animation:flow 1.1s linear infinite;opacity:.7}
@keyframes flow{to{stroke-dashoffset:-15.1}}
.net.sel .leg,.net.sel .badge{opacity:.08}.net.sel .leg.on,.net.sel .badge.on{opacity:1}.net.sel .leg.on .main{stroke-width:3}.net.sel .leg.on .pkt{opacity:.95}
.net .leg.act .main{stroke-width:4.2;filter:drop-shadow(0 0 4px currentColor)}.net.sel .node{opacity:.3;transition:opacity .2s}.net.sel .node.on{opacity:1}
.net .pk{stroke:#fff;stroke-width:2.2;opacity:0;pointer-events:none;filter:drop-shadow(0 0 5px rgba(0,0,0,.45))}
@media (prefers-reduced-motion:reduce){.net .pkt{animation:none}}
/* formulario */
#form,#view-help{padding:8px 24px 60px;max-width:1500px}#form h2{margin:22px 0 6px;font-size:15px}
.ft input,.ft select,.fcard input,.qa textarea{width:100%;border:1px solid var(--line);background:var(--bg);color:var(--ink);border-radius:6px;padding:5px 7px;font:inherit;font-size:12.5px}
.ft td{padding:3px 4px}.ft .num{width:80px}input.miss{border-color:#EF4444;background:rgba(239,68,68,.08)}
.x{border:0;background:none;color:var(--muted);cursor:pointer;font-size:14px}.x:hover{color:#EF4444}
.fcard{border:1px solid var(--line);border-radius:10px;padding:8px 10px;margin:8px 0;background:var(--panel)}
.frow{display:grid;grid-template-columns:90px 1.2fr 1.2fr 1fr;gap:8px;align-items:center;margin:4px 0}.frow.hop{grid-template-columns:1.4fr 1fr 1.4fr}
.qa{margin:8px 0}.qa label{display:block;font-weight:600;margin-bottom:3px}.qa textarea{resize:vertical}
#savebar{position:sticky;bottom:0;display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:10px 24px;background:var(--panel);border-top:1px solid var(--line)}
#status{color:var(--muted);font-size:12.5px;flex:1}#draftbar{display:none;gap:10px;align-items:center;padding:8px 24px;background:rgba(232,129,26,.12);border-bottom:1px solid var(--accent)}
"""
CFG_KINDS = ["app", "db", "user", "saas", "external", "firewall", "gateway", "vpn", "lb", "proxy", "router", "dns"]
GENERIC_QUESTIONS = [
    "¿Qué ambiente representa este diagrama (DEV, QA, PRD)? ¿Las IPs cambian entre ambientes?",
    "¿Desde dónde acceden los usuarios (oficina, VPN corporativa, Internet) y por qué dirección o URL?",
    "¿Hay un balanceador, WAF, proxy o API gateway delante de la aplicación? ¿Cuál es su nombre/IP?",
    "¿Cómo se resuelven los nombres (DNS interno, público, hosts)? ¿Hay reglas de firewall relevantes que documentar?",
]
SHELL = """<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Arquitectura</title><style>%(css)s</style></head><body>
<header><h1><span id="title"></span><span class="chip" id="env" style="cursor:default;display:none"></span></h1><p id="sub"></p></header>
<div id="draftbar"><span>Hay un borrador sin guardar en el archivo.</span><button class="btn" id="restore">Restaurar</button><button class="btn" id="discard">Descartar</button></div>
<div class="tabs"><button data-v="diagram" class="on">Diagrama</button><button data-v="form" id="tabform">Completar datos</button></div>
<div class="tabv on" data-v="diagram">
 <div class="bar"><button class="chip on" id="allchip">Todos los flujos</button><span id="chips" style="display:contents"></span><span class="sp"></span><button class="chip" id="mask" title="Oculta los 2 últimos octetos de las IPs (para capturas)">Ocultar IPs</button></div>
 <div id="player"><button class="btn" id="pause">⏸ Pausar</button><button class="btn" id="replay">↻ Repetir</button><span id="cap"></span></div>
 <div class="canvas"><div id="svgbox"></div></div>
 <main>
  <section style="grid-column:1/-1"><h2>Flujos</h2><div id="all"></div><div id="details"></div></section>
  <section><h2>Inventario por sitio y segmento</h2><div id="inv"></div></section>
  <section><h2>Leyenda</h2><div id="legend">%(legend)s</div></section>
  <section class="warn" id="pendsec" style="display:none"><div id="pend"></div></section>
 </main>
</div>
<div class="tabv" data-v="form"><div id="form"></div></div>
<div id="savebar"><button class="btn pri" id="savehtml">💾 Guardar en el HTML</button><button class="btn" id="savejson">⬇ Exportar network.json</button><span id="status">Los cambios se ven al instante. «Guardar en el HTML» deja los datos dentro de este archivo.</span></div>
<script id="spec" type="application/json">%(spec)s</script>
<script id="icons" type="application/json">%(icons)s</script>
<script>window.CFG=%(cfg)s;</script>
<script>%(app)s</script></body></html>"""


def _js_json(obj):
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/").replace("<!--", "<\\!--")


def legend_html():
    rows = []
    for k, (c, d) in FLOW_STYLE.items():
        rows.append(f'<tr><td style="width:60px"><svg width="46" height="8"><line x1="0" y1="4" x2="46" y2="4" stroke="{c}" stroke-width="2.4" stroke-dasharray="{d}"/></svg></td><td>{FLOW_LABEL[k]}</td></tr>')
    rows.append('<tr><td><span style="display:inline-block;border:2px dashed #EF4444;width:18px;height:18px;border-radius:50%"></span></td><td>elemento de red (firewall, VPN, gateway, balanceador, proxy)</td></tr>')
    rows.append('<tr><td><span style="display:inline-block;background:#fff;border:1px solid #94A3B8;width:8px;height:8px;border-radius:50%"></span></td><td>puntos blancos en movimiento = sentido del flujo (al elegir un flujo, un paquete recorre cada salto)</td></tr>')
    return "<table>" + "".join(rows) + "</table>"


def render_html(spec, theme, icons_dir, mask, pend):
    """HTML autocontenido: el diagrama se dibuja en el navegador desde #spec, de modo que los datos que el usuario complete
    (sitio, IP, segmento…) se vean al instante y puedan guardarse DENTRO del mismo archivo."""
    names = {"box"} | {n.get("icon", "box") for n in spec.get("nodes", [])} | {SITE_ICON.get(s.get("kind", "unknown"), "box") for s in spec.get("sites", [])} | set(SITE_ICON.values())
    icons = {nm: icon_uri(nm, theme, icons_dir) for nm in sorted(names)}
    data = copy.deepcopy(spec)
    data.setdefault("questions", [{"id": f"g{i}", "text": t, "answer": ""} for i, t in enumerate(GENERIC_QUESTIONS, 1)])
    cfg = {"CELLW": CELLW, "CELLH": CELLH, "PAD": PAD, "GAP": GAP, "SITE_COLOR": SITE_COLOR, "SITE_DASH": sorted(SITE_DASH), "SITE_ICON": SITE_ICON,
           "NET_KINDS": sorted(NET_KINDS), "FLOW_STYLE": {k: list(v) for k, v in FLOW_STYLE.items()}, "FLOW_LABEL": FLOW_LABEL, "KINDS": CFG_KINDS,
           "SITE_KINDS": list(SITE_COLOR), "SEG_KINDS": ["vpc", "vnet", "subnet", "vlan", "dmz"], "locked": bool(mask)}
    app = (pathlib.Path(__file__).resolve().parent / "net_app.js").read_text(encoding="utf-8")
    out = SHELL % {"css": PAGE_CSS, "legend": legend_html(), "spec": _js_json(data), "icons": _js_json(icons), "cfg": _js_json(cfg), "app": app}
    return mask_text(out) if mask else out


# ------------------------------------------------------------------ borrador desde graph.json
HOST_ICON = {"SQL Server": "microsoftsqlserver", "PostgreSQL": "postgresql", "MySQL": "mysql", "MongoDB": "mongodb", "Redis": "redis",
             "RabbitMQ": "rabbitmq", "Kafka": "apachekafka", "SMTP": "mail", "SAP HANA": "database", "Oracle": "oracle"}
SITE_LABEL = {"aws": "AWS", "azure": "Azure", "sap": "SAP", "gcp": "Google Cloud", "saas": "SaaS"}


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:28] or "x"


def init_spec(graph):
    nh = graph.get("network_hints") or {}
    spec = {"title": f"{graph.get('root', 'Proyecto')} · Arquitectura de red", "subtitle": "BORRADOR deducido del código: confirmar sitios, segmentos e IPs con el usuario",
            "draft": True, "sites": [{"id": "users", "label": "Usuarios", "kind": "users"}, {"id": "unk", "label": "Sitio por confirmar", "kind": "unknown",
                                                                                                 "detail": "on-prem / AWS / Azure / SAP: ¿cuál?"}],
            "segments": [], "nodes": [{"id": "usr", "name": "Usuarios", "icon": "users", "site": "users", "kind": "user"},
                                      {"id": "app", "name": graph.get("root", "Aplicación"), "role": "aplicación", "icon": "server", "site": "unk"}],
            "flows": [], "pending": []}
    ports = [p["port"] for p in nh.get("listen_ports", [])]
    if ports:
        spec["nodes"][1]["port"] = ports[0]
    spec["flows"].append({"id": "1", "label": "Acceso de usuarios", "kind": "principal", "protocol": f"HTTPS {ports[0]}" if ports else "", "hops": ["usr", "app"]})
    sites = {"unk"}
    for h in nh.get("hosts", []):
        sid = h["site_hint"] or "unk"
        if sid not in sites:
            sites.add(sid)
            spec["sites"].append({"id": sid, "label": SITE_LABEL.get(sid, sid), "kind": sid if sid in SITE_COLOR else "unknown"})
        nid = slug(h["host"])
        if any(n["id"] == nid for n in spec["nodes"]):
            continue
        spec["nodes"].append({"id": nid, "name": h.get("service_hint") or h["host"].split(".")[0], "role": h["host"] if h.get("service_hint") else "",
                              "icon": HOST_ICON.get(h.get("service_hint"), "api" if "http" in " ".join(h["schemes"]) else "server"), "site": sid,
                              "host": h["host"], "port": h["port"], "kind": "external" if sid in ("saas", "sap") else "app"})
        spec["flows"].append({"id": str(len(spec["flows"]) + 1), "label": f"Aplicación → {h.get('service_hint') or h['host']}", "kind": "externo" if sid != "unk" else "interno",
                              "protocol": f"{(h['schemes'] or [''])[0].upper()} {h['port']}".strip(), "hops": ["app", nid]})
    for sg in nh.get("segments_detected", []):
        sid = "seg_" + slug(sg["cidr"])
        spec["segments"].append({"id": sid, "site": "unk", "label": f"Segmento {sg['cidr']}", "cidr": sg["cidr"], "kind": "subnet"})
        for ip in sg["ips"]:
            spec["nodes"].append({"id": "ip_" + slug(ip), "name": "Servidor " + ip, "icon": "server", "site": "unk", "segment": sid, "ip": ip, "kind": "app"})
    spec["pending"] += ["Confirmar a qué sitio pertenece cada IP privada detectada (una IP 10.x/172.16-31.x/192.168.x no indica si es on-prem, AWS o Azure).",
                        "¿Hay firewall, VPN/Direct Connect/ExpressRoute, proxy o balanceador entre usuarios, aplicación y base de datos?",
                        "¿Existen ambientes distintos (DEV/QA/PRD) con IPs diferentes? ¿cuál se documenta?"]
    return spec


# ------------------------------------------------------------------ CLI
def main_init(args):
    import argparse
    ap = argparse.ArgumentParser(prog="tdocs net-init")
    ap.add_argument("graph", nargs="?", default="docs/00-grafo/graph.json")
    ap.add_argument("-o", "--out", default="docs/spec/network.json")
    a = ap.parse_args(args)
    if pathlib.Path(a.out).exists():
        print(f"ya existe {a.out}: no lo sobrescribo (bórralo si quieres un borrador nuevo)")
        return 1
    spec = init_spec(read_json(a.graph))
    write(a.out, json.dumps(spec, indent=2, ensure_ascii=False))
    print(f"OK borrador de red → {a.out} ({len(spec['nodes'])} nodos, {len(spec['segments'])} segmentos). Pregunta al usuario lo pendiente y edítalo.")


def main(args):
    import argparse
    ap = argparse.ArgumentParser(prog="tdocs net")
    ap.add_argument("spec", nargs="?", default="docs/spec/network.json")
    ap.add_argument("-o", "--out", default="docs")
    ap.add_argument("--theme")
    ap.add_argument("--icons-dir")
    ap.add_argument("--mask-ips", action="store_true", help="enmascara IPs (a.b.x.x) en TODAS las salidas")
    ap.add_argument("--strict", action="store_true", help="falla (exit 2) si hay pendientes por confirmar")
    a = ap.parse_args(args)
    spec, theme = read_json(a.spec), load_theme(a.theme)
    spec.setdefault("questions", [{"id": f"g{i}", "text": t, "answer": ""} for i, t in enumerate(GENERIC_QUESTIONS, 1)])
    errs, pend = check(spec)
    if errs:
        print("ERRORES en el spec de red:")
        for e in errs:
            print("  -", e)
        return 1
    d = pathlib.Path(a.out) / "02-arquitectura"
    write(d / "arquitectura.html", render_html(spec, theme, a.icons_dir, a.mask_ips, pend))
    svg = render_svg(spec, theme, a.icons_dir, a.mask_ips, True)
    write(d / "arquitectura-red.svg", mask_text(svg) if a.mask_ips else svg)
    md = ["# Pendientes por confirmar (red)\n"] + ([f"{i}. {p}" for i, p in enumerate(pend, 1)] or ["Sin pendientes."])
    write(d / "arquitectura-red-pendientes.md", "\n".join(md) + "\n")
    print(f"OK red: {len(spec.get('sites', []))} sitios, {len(spec.get('segments', []))} segmentos, {len(spec.get('nodes', []))} componentes, "
          f"{len(spec.get('flows', []))} flujos → {d}/arquitectura.html")
    if pend:
        print(f"\nPENDIENTES POR CONFIRMAR ({len(pend)}): pregúntaselos al usuario antes de dar el diagrama por terminado:")
        for p in pend:
            print("  ?", p)
        return 2 if a.strict else 0
