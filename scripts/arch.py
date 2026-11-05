"""Paso 3 · Arquitectura: architecture.json -> .drawio (editable, con iconos por componente) + .svg de vista previa."""
import collections
from common import (load_theme, read_json, write, esc, wrap, icon_uri, svg_open, svg_text, svg_title, polyline, edge_style,
                    Drawio, ICON_SOURCES, MONO)

COLW, ROWH, X0, Y0 = 190, 150, 110, 120
TOP_PAD, SIDE_PAD, BOT_PAD = 60, 24, 24


NO_SITE_ICONS = {"user", "users", "browser"}


def extra_line(n):
    """Segunda línea bajo el rol: sitio · IP/host (si se conocen)."""
    bits = [n.get("site"), n.get("ip") or n.get("host")]
    return " · ".join(str(b) for b in bits if b)


def check(spec):
    """Preguntas que el agente debe hacer al usuario cuando el spec no trae el dato (nunca se inventa)."""
    q = []
    nodes = {n["id"]: n for n in spec.get("nodes", [])}
    for n in spec.get("nodes", []):
        if n.get("icon", "box") in NO_SITE_ICONS:
            continue
        if not n.get("site"):
            q.append(f"¿En qué sitio/servidor corre «{n['name']}»? (on-prem, AWS, Azure, SAP, SaaS u otro)")
        if not (n.get("ip") or n.get("host")):
            q.append(f"¿Cuál es la IP u hostname de «{n['name']}»? (si es un servicio gestionado, la URL/endpoint)")
    for e in spec.get("edges", []):
        a, b = nodes.get(e["from"]), nodes.get(e["to"])
        if not a or not b:
            continue
        if not e.get("label") and e.get("kind", "internal") in ("primary", "dashed", "risk"):
            q.append(f"¿Cómo se llama la integración/interfaz entre «{a['name']}» y «{b['name']}» (iFlow, API, job, cola, archivo) y qué protocolo/puerto usa?")
    seen, out = set(), []
    for x in q:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def layout(spec):
    """Rangos por dependencia -> columnas. Cada grupo de primer nivel ocupa su propia banda horizontal (sin solapes)."""
    nodes = {n["id"]: n for n in spec["nodes"]}
    rank = {k: 0 for k in nodes}
    n = max(len(nodes), 1)
    es = [(e["from"], e["to"]) for e in spec.get("edges", []) if e["from"] in nodes and e["to"] in nodes and e["from"] != e["to"]]
    for _ in range(n):
        ch = False
        for s_, t_ in es:
            if rank[t_] < rank[s_] + 1 and rank[s_] + 1 < n:
                rank[t_] = rank[s_] + 1
                ch = True
        if not ch:
            break
    groups = {g["id"]: g for g in spec.get("groups", [])}

    def top_group(gid):
        seen = set()
        while gid in groups and groups[gid].get("parent") in groups and gid not in seen:
            seen.add(gid)
            gid = groups[gid]["parent"]
        return gid if gid in groups else None
    tops = [g["id"] for g in spec.get("groups", []) if g["id"] == top_group(g["id"])]
    band_key = lambda nd: top_group(nd.get("group")) if nd.get("group") else None
    bands = ([None] if any(band_key(nd) is None for nd in spec["nodes"]) else []) + tops
    sub = collections.defaultdict(int)
    nsub = collections.defaultdict(int)
    placed = []
    for nd in spec["nodes"]:
        b = bands.index(band_key(nd)) if band_key(nd) in bands else 0
        col = nd.get("col", rank[nd["id"]])
        r = nd.get("row", sub[(b, col)])
        sub[(b, col)] = max(sub[(b, col)], r) + 1
        nsub[b] = max(nsub[b], r + 1)
        placed.append((nd, b, col, r))
    offs, y = {}, Y0
    for b in range(len(bands)):
        offs[b] = y
        y += (max(nsub[b], 1) - 1) * ROWH + 215
    for nd, b, col, r in placed:
        nd["_cx"] = nd["x"] if "x" in nd else X0 + col * COLW
        nd["_top"] = nd["y"] if "y" in nd else offs[b] + r * ROWH
    return nodes


def group_boxes(spec, nodes):
    groups = {g["id"]: g for g in spec.get("groups", [])}

    def depth(g):
        d = 0
        while groups[g].get("parent") in groups:
            g = groups[g]["parent"]
            d += 1
        return d
    order = sorted(groups, key=lambda g: -depth(g))
    boxes = {}
    for gid in order:
        xs0, ys0, xs1, ys1 = [], [], [], []
        for nd in spec["nodes"]:
            if nd.get("group") == gid:
                xs0.append(nd["_cx"] - 66 - SIDE_PAD); xs1.append(nd["_cx"] + 66 + SIDE_PAD)
                ys0.append(nd["_top"] - TOP_PAD); ys1.append(nd["_top"] + 104 + BOT_PAD)
        for cid, b in boxes.items():
            if groups[cid].get("parent") == gid:
                xs0.append(b[0] - SIDE_PAD); xs1.append(b[0] + b[2] + SIDE_PAD)
                ys0.append(b[1] - 44); ys1.append(b[1] + b[3] + BOT_PAD)
        if xs0:
            boxes[gid] = [min(xs0), min(ys0), max(xs1) - min(xs0), max(ys1) - min(ys0)]
    return groups, boxes


def route(a, b, slot=0, n_in=1):
    """Rutas ortogonales. Entre filas/bandas: baja por la columna del origen y entra por un canal sobre el destino
    (desfasado por `slot` para que flechas al mismo destino no se superpongan)."""
    sx, sy, tx, ty = a["_cx"], a["_top"], b["_cx"], b["_top"]
    off = 6 * slot
    dx = (slot - (n_in - 1) / 2) * 16
    if abs(ty - sy) < 5:
        if tx > sx:
            return "h", [(sx + 36, sy + 30), (tx - 36, ty + 30)]
        return "h", [(sx - 36, sy + 30), (tx + 36, ty + 30)]
    if abs(tx - sx) < 5:
        if ty > sy:
            return "vd", [(sx, sy + 108), (tx, ty - 6)]
        return "vu", [(sx, sy - 6), (tx, ty + 108)]
    if ty > sy:
        ch = ty - 24 + off
        return "down", [(sx, sy + 108), (sx, ch), (tx + dx, ch), (tx + dx, ty - 6)]
    ch = sy - 24 + off
    return "up", [(sx, sy - 6), (sx, ch), (tx + dx, ch), (tx + dx, ty + 108)]


def label_pos(pts):
    best, bl = 0, -1
    for i in range(len(pts) - 1):
        l = abs(pts[i + 1][0] - pts[i][0]) + abs(pts[i + 1][1] - pts[i][1])
        if l > bl:
            best, bl = i, l
    (x1, y1), (x2, y2) = pts[best], pts[best + 1]
    if abs(y1 - y2) < 1:
        return (x1 + x2) / 2, y1 - 8, "middle"
    return x1 + 8, (y1 + y2) / 2 + 3, "start"


def size(spec, boxes):
    w = max([n["_cx"] + 90 for n in spec["nodes"]] + [b[0] + b[2] for b in boxes.values()] + [600]) + 40
    h = max([n["_top"] + 130 for n in spec["nodes"]] + [b[1] + b[3] for b in boxes.values()] + [300]) + 40
    return int(w), int(h)


def to_svg(spec, theme, icons_dir=None):
    nodes = layout(spec)
    groups, boxes = group_boxes(spec, nodes)
    W, H = size(spec, boxes)
    t = theme
    o = [svg_open(W, H + 40, t), svg_title(spec.get("title", "Arquitectura"), spec.get("subtitle", ""), t, W)]
    for gid, g in groups.items():
        if gid not in boxes:
            continue
        x, y, w, h = boxes[gid]
        dash = ' stroke-dasharray="6 5"' if g.get("style") == "dashed" else ""
        col = t["gris"] if g.get("style") == "dashed" else t["azul_med"]
        fill = "rgba(241,245,249,.7)"
        o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{fill}" stroke="{col}" stroke-width="1.5"{dash}/>')
        lx = x + 12
        if g.get("icon"):
            o.append(f'<image href="{icon_uri(g["icon"], t, icons_dir)}" x="{lx}" y="{y+10}" width="16" height="16"/>')
            lx += 22
        o.append(svg_text(lx, y + 23, g.get("label", gid), 12, 600, t["azul"] if g.get("style") != "dashed" else t["gris"], "start"))
    slots = collections.Counter()
    n_in = collections.Counter(e["to"] for e in spec.get("edges", []))
    for e in spec.get("edges", []):
        a, b = nodes.get(e["from"]), nodes.get(e["to"])
        if not a or not b:
            continue
        kind_, pts = route(a, b, slots[e["to"]], n_in[e["to"]])
        slots[e["to"]] += 1
        col, dash, mk = edge_style(e.get("kind", "internal"), t)
        o.append(polyline(pts, col, dash, mk))
        if e.get("label"):
            if kind_ in ("down", "up"):
                lx, ly, anc = pts[0][0] + 8, pts[0][1] + (42 if kind_ == "down" else -14), "start"
            else:
                lx, ly, anc = label_pos(pts)
            o.append(svg_text(lx, ly, e["label"], 10, 400, col, anc, mono=True, halo=t["paper"]))
    for n in spec["nodes"]:
        cx, top = n["_cx"], n["_top"]
        dark = n.get("tile") == "dark"
        o.append(f'<rect x="{cx-30}" y="{top}" width="60" height="60" rx="12" fill="{t["azul"] if dark else "#fff"}" stroke="{t["azul"] if dark else t["tile_border"]}"/>')
        o.append(f'<image href="{icon_uri(n.get("icon", "box"), t, icons_dir)}" x="{cx-17}" y="{top+13}" width="34" height="34"/>')
        for i, ln in enumerate(wrap(n["name"], 20, 2)):
            o.append(svg_text(cx, top + 78 + i * 15, ln, 13, 600, t["azul"]))
        base_y = top + 78 + 15 * len(wrap(n["name"], 20, 2)) + 3
        if n.get("role"):
            o.append(svg_text(cx, base_y, n["role"], 10, 400, t["gris"], mono=True))
            base_y += 12
        if extra_line(n):
            o.append(svg_text(cx, base_y, extra_line(n), 10, 600, t["azul_med"], mono=True))
    ly = H + 8
    for i, (lab, kind) in enumerate([("flujo principal", "primary"), ("interno", "internal"), ("batch / externo", "dashed")]):
        col, dash, _ = edge_style(kind, t)
        x0 = 24 + i * 190
        o.append(polyline([(x0, ly), (x0 + 34, ly)], col, dash))
        o.append(svg_text(x0 + 42, ly + 4, lab, 10, 400, t["gris"], "start", mono=True))
    o.append("</svg>")
    return "".join(o)


def to_drawio(spec, theme, icons_dir=None):
    nodes = layout(spec)
    groups, boxes = group_boxes(spec, nodes)
    W, H = size(spec, boxes)
    t = theme
    d = Drawio()
    d.vertex(f'<b><font style="font-size:20px" color="{t["azul"]}">{esc(spec.get("title", "Arquitectura"))}</font></b><br>'
             f'<font style="font-size:11px" color="{t["gris"]}">{esc(spec.get("subtitle", ""))}</font>',
             "text;html=1;align=left;verticalAlign=top;whiteSpace=wrap;", 20, 10, W - 40, 50)
    # padres primero: más grande -> primero
    for gid in sorted(boxes, key=lambda g: -boxes[g][2] * boxes[g][3]):
        g, (x, y, w, h) = groups[gid], boxes[gid]
        dashed = g.get("style") == "dashed"
        col = t["gris"] if dashed else t["azul_med"]
        d.vertex(f'<b>{esc(g.get("label", gid))}</b>',
                 f"rounded=1;arcSize=3;html=1;whiteSpace=wrap;align=left;verticalAlign=top;spacingLeft={34 if g.get('icon') else 12};spacingTop=8;"
                 f"fontSize=12;fillColor={t['gris_light']};strokeColor={col};strokeWidth=1.5;{'dashed=1;' if dashed else ''}fontColor={t['azul']};opacity=90;",
                 x, y + 70, w, h)
        if g.get("icon"):
            d.vertex("", f"shape=image;html=1;image={icon_uri(g['icon'], t, icons_dir)};imageAspect=1;", x + 12, y + 80, 18, 18)
    box, tile = {}, {}
    for n in spec["nodes"]:
        cx, top = n["_cx"], n["_top"] + 70
        box[n["id"]] = d.vertex("", "rounded=0;html=1;fillColor=none;strokeColor=none;", cx - 66, top, 132, 104)
        dark = n.get("tile") == "dark"
        tile[n["id"]] = d.vertex("", f"rounded=1;arcSize=20;html=1;fillColor={t['azul'] if dark else '#FFFFFF'};strokeColor={t['azul'] if dark else t['tile_border']};", cx - 30, top, 60, 60)
        d.vertex("", f"shape=image;html=1;image={icon_uri(n.get('icon', 'box'), t, icons_dir)};imageAspect=1;", cx - 17, top + 13, 34, 34)
        d.vertex(f'<b><font color="{t["azul"]}" style="font-size:13px">{esc(n["name"])}</font></b><br>'
                 f'<font color="{t["gris"]}" style="font-size:10px" face="Courier New">{esc(n.get("role", ""))}</font>'
                 + (f'<br><font color="{t["azul_med"]}" style="font-size:10px" face="Courier New"><b>{esc(extra_line(n))}</b></font>' if extra_line(n) else ""),
                 "text;html=1;align=center;verticalAlign=top;whiteSpace=wrap;spacing=0;", cx - 66, top + 64, 132, 40)
    for e in spec.get("edges", []):
        if e["from"] not in nodes or e["to"] not in nodes:
            continue
        kind, _ = route(nodes[e["from"]], nodes[e["to"]])
        col, dash, _ = edge_style(e.get("kind", "internal"), t)
        base = (f"edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;endArrow=block;endFill=1;strokeColor={col};strokeWidth=1.6;"
                f"{'dashed=1;dashPattern=4 5;' if dash else ''}fontSize=10;fontColor={col};labelBackgroundColor=#FFFFFF;fontFamily=Courier New;")
        if kind == "h":
            fwd = nodes[e["to"]]["_cx"] > nodes[e["from"]]["_cx"]
            c = ("exitX=1;exitY=0.5;exitDx=0;exitDy=0;entryX=0;entryY=0.5;entryDx=0;entryDy=0;" if fwd
                 else "exitX=0;exitY=0.5;exitDx=0;exitDy=0;entryX=1;entryY=0.5;entryDx=0;entryDy=0;")
            s, tg = tile[e["from"]], tile[e["to"]]
        elif kind in ("down", "vd"):
            c = "exitX=0.5;exitY=1;exitDx=0;exitDy=0;entryX=0.5;entryY=0;entryDx=0;entryDy=0;"
            s, tg = box[e["from"]], tile[e["to"]]
        else:
            c = "exitX=0.5;exitY=0;exitDx=0;exitDy=0;entryX=0.5;entryY=1;entryDx=0;entryDy=0;"
            s, tg = tile[e["from"]], box[e["to"]]
        d.edge(s, tg, base + c, e.get("label", ""))
    ly = H + 60
    for i, (lab, kind) in enumerate([("flujo principal", "primary"), ("interno", "internal"), ("batch / externo", "dashed")]):
        col, dash, _ = edge_style(kind, t)
        x0 = 40 + i * 190
        d.line(x0, ly, x0 + 34, ly, f"endArrow=none;html=1;strokeColor={col};strokeWidth=1.6;{'dashed=1;dashPattern=4 5;' if dash else ''}")
        d.vertex(lab, f"text;html=1;align=left;verticalAlign=middle;fontSize=10;fontColor={t['gris']};fontFamily=Courier New;", x0 + 40, ly - 10, 140, 20)
    return d, W, H + 140


def main(args):
    import argparse
    ap = argparse.ArgumentParser(prog="tdocs arch")
    ap.add_argument("spec", nargs="?", default="docs/spec/architecture.json")
    ap.add_argument("-o", "--out", default="docs")
    ap.add_argument("--theme")
    ap.add_argument("--icons-dir")
    a = ap.parse_args(args)
    spec, theme = read_json(a.spec), load_theme(a.theme)
    write(f"{a.out}/02-arquitectura/arquitectura.svg", to_svg(spec, theme, a.icons_dir))
    d, W, H = to_drawio(spec, theme, a.icons_dir)
    d.save(f"{a.out}/02-arquitectura/arquitectura.drawio", "Arquitectura", W, H)
    srcs = ", ".join(sorted(set(ICON_SOURCES.values())))
    print(f"OK arquitectura: {len(spec['nodes'])} componentes → {a.out}/02-arquitectura/ (iconos: {srcs})")
    pend = check(spec)
    md = ["# Pendientes por confirmar (arquitectura)\n"] + ([f"{i}. {x}" for i, x in enumerate(pend, 1)] or ["Sin pendientes."])
    write(f"{a.out}/02-arquitectura/arquitectura-pendientes.md", "\n".join(md) + "\n")
    if pend:
        print(f"\nPENDIENTES POR CONFIRMAR ({len(pend)}): pregúntaselos al usuario antes de dar la arquitectura por terminada:")
        for x in pend:
            print("  ?", x)
