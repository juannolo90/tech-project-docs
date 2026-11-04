"""Paso 4 · Modelo entidad-relación con volúmenes y proyección de crecimiento.

Entrada: erd.json. Salida: modelo-datos.drawio, modelo-datos.svg, volumenes.md y modelo-datos.mmd (Mermaid).
Regla: los volúmenes salen de mediciones reales o de supuestos EXPLÍCITOS (campo volume.source). Nunca se inventan.
"""
import math
from common import (load_theme, read_json, write, esc, svg_open, svg_text, svg_title, Drawio, human, human_bytes, MONO)

HORIZONS = [6, 12, 24, 36]
ROW_H, HEAD_H, VOL_H = 20, 30, 20
WARN_BYTES = 10e9


def project(vol, months):
    if not vol or vol.get("rows") is None:
        return None
    r0 = float(vol["rows"])
    if vol.get("growth_pct_month") is not None:
        return r0 * (1 + float(vol["growth_pct_month"]) / 100.0) ** months
    if vol.get("rows_per_month") is not None:
        return r0 + float(vol["rows_per_month"]) * months
    return r0


def size_of(vol, rows):
    if rows is None or not vol or vol.get("avg_row_bytes") is None:
        return None
    return rows * float(vol["avg_row_bytes"])


def vol_line(e):
    v = e.get("volume")
    if not v or v.get("rows") is None:
        return "volumen: sin medir"
    g = (f" · +{v['growth_pct_month']}%/mes" if v.get("growth_pct_month") is not None
         else f" · +{human(v['rows_per_month'])}/mes" if v.get("rows_per_month") is not None else "")
    src = f" [{v['source']}]" if v.get("source") else ""
    return f"≈{human(v['rows'])} filas{g}{src}"


def relations(spec):
    names = {e["name"] for e in spec["entities"]}
    rel = []
    for r in spec.get("relations", []):
        rel.append((r["from"].split(".")[0], r["to"].split(".")[0], r.get("card", "N:1"), r["from"], r["to"]))
    seen = {(a, b) for a, b, *_ in rel}
    for e in spec["entities"]:
        for c in e.get("columns", []):
            if c.get("fk") and c["fk"].split(".")[0] in names:
                tgt = c["fk"].split(".")[0]
                if (e["name"], tgt) not in seen:
                    rel.append((e["name"], tgt, "N:1", f"{e['name']}.{c['name']}", c["fk"]))
                    seen.add((e["name"], tgt))
    return rel


def box_size(e):
    cols = e.get("columns", [])
    longest = max([len(e["name"]) + 2, len(vol_line(e))] + [len(c["name"]) + len(c.get("type", "")) + 8 for c in cols])
    return max(230, int(longest * 7.2) + 28), HEAD_H + VOL_H + ROW_H * max(len(cols), 1) + 8


def order_entities(spec):
    ents = {e["name"]: e for e in spec["entities"]}
    adj = {n: [] for n in ents}
    for a_, b_, *_ in relations(spec):
        if a_ in adj and b_ in adj and a_ != b_:
            adj[a_].append(b_)
            adj[b_].append(a_)
    deg = {n: len(set(v)) for n, v in adj.items()}
    seen, order = set(), []

    def dfs(n):
        seen.add(n)
        order.append(n)
        for m in sorted(set(adj[n]), key=lambda x: deg[x]):
            if m not in seen:
                dfs(m)
    starts = sorted((n for n in ents if deg[n] > 0), key=lambda n: (deg[n], list(ents).index(n)))
    for n in starts + [n for n in ents if deg[n] == 0]:
        if n not in seen:
            dfs(n)
    return [ents[n] for n in order]


GUT = 38


def layout(spec):
    ents = order_entities(spec)
    ncol = min(4, max(1, math.ceil(math.sqrt(len(ents)))))
    sizes = {e["name"]: box_size(e) for e in ents}
    rows = [ents[i:i + ncol] for i in range(0, len(ents), ncol)]
    colw = [max(sizes[r[j]["name"]][0] for r in rows if j < len(r)) for j in range(ncol)]
    colx, x = [], 30
    for w in colw:
        colx.append(x)
        x += w + 2 * GUT + 14
    rowh = [max(sizes[e["name"]][1] for e in r) for r in rows]
    rowy, y = [], 90
    for h in rowh:
        rowy.append(y)
        y += h + 2 * GUT + 14
    pos, grid = {}, {}
    for ri, r in enumerate(rows):
        for ci, e in enumerate(r):
            pos[e["name"]] = (colx[ci], rowy[ri], colw[ci], sizes[e["name"]][1])
            grid[e["name"]] = (ri, ci)
    gyb = [rowy[r] + rowh[r] + GUT for r in range(len(rows))]                 # pasillo bajo la fila r
    gya = [rowy[r] - GUT for r in range(len(rows))]                            # pasillo sobre la fila r
    gxr = [colx[c] + colw[c] + GUT for c in range(ncol)]                       # pasillo a la derecha de la columna c
    W = colx[-1] + colw[-1] + 40
    return pos, W, y - GUT, {"grid": grid, "gyb": gyb, "gya": gya, "gxr": gxr, "rowy": rowy}


def route(a, b, pos, info):
    ax, ay, aw, ah = pos[a]
    bx, by, bw, bh = pos[b]
    (r1, c1), (r2, c2) = info["grid"][a], info["grid"][b]
    acx, bcx = ax + aw / 2, bx + bw / 2
    if r1 == r2:
        if abs(c1 - c2) == 1:
            y = info["rowy"][r1] + HEAD_H / 2
            return [(ax + aw, y), (bx, y)] if c2 > c1 else [(ax, y), (bx + bw, y)]
        g = info["gya"][r1]
        return [(acx, ay), (acx, g), (bcx, g), (bcx, by)]
    if r2 > r1:
        g1, g2 = info["gyb"][r1], info["gya"][r2]
        if r2 == r1 + 1:
            g2 = g1 = info["gyb"][r1]
            return [(acx, ay + ah), (acx, g1), (bcx, g1), (bcx, by)] if acx != bcx else [(acx, ay + ah), (bcx, by)]
        gx = info["gxr"][c1]
        return [(acx, ay + ah), (acx, g1), (gx, g1), (gx, g2), (bcx, g2), (bcx, by)]
    g1, g2 = info["gya"][r1], info["gyb"][r2]
    if r1 == r2 + 1:
        return [(acx, ay), (acx, g1), (bcx, g1), (bcx, by + bh)] if acx != bcx else [(acx, ay), (bcx, by + bh)]
    gx = info["gxr"][c1]
    return [(acx, ay), (acx, g1), (gx, g1), (gx, g2), (bcx, g2), (bcx, by + bh)]


def end_label(p, q):
    """Posición de la etiqueta 1/N junto al extremo p (q = siguiente punto del trazado)."""
    if abs(p[0] - q[0]) < 1:
        return p[0] + 8, p[1] + (14 if q[1] > p[1] else -6)
    return p[0] + (6 if q[0] > p[0] else -12), p[1] - 6


def table_rows(spec):
    rows = []
    for e in spec["entities"]:
        v = e.get("volume")
        if not v or v.get("rows") is None:
            rows.append((e["name"], None, [None] * len(HORIZONS), None, None, v))
            continue
        r0 = float(v["rows"])
        proj = [project(v, m) for m in HORIZONS]
        rows.append((e["name"], r0, proj, size_of(v, r0), size_of(v, proj[-1]), v))
    return rows


def to_svg(spec, theme):
    t = theme
    pos, W, Hd, info = layout(spec)
    tr = table_rows(spec)
    th = 34 + 26 * (len(tr) + 1) + 30
    W = max(W, 880)
    H = Hd + th + 20
    o = [svg_open(W, H, t), svg_title(spec.get("title", "Modelo de datos"), spec.get("subtitle", ""), t, W)]
    # relaciones debajo de las cajas, por pasillos libres
    for a_, b_, card, fa, fb in relations(spec):
        if a_ not in pos or b_ not in pos or a_ == b_:
            continue
        pts = route(a_, b_, pos, info)
        o.append(f'<polyline points="{" ".join(f"{x:.0f},{y:.0f}" for x, y in pts)}" fill="none" stroke="{t["azul_med"]}" stroke-width="1.5" stroke-linejoin="round"/>')
        many, one = card.split(":")
        l1, l2 = end_label(pts[0], pts[1]), end_label(pts[-1], pts[-2])
        o.append(svg_text(l1[0], l1[1], many, 11, 700, t["naranjo"], mono=True, halo=t["paper"]))
        o.append(svg_text(l2[0], l2[1], one, 11, 700, t["naranjo"], mono=True, halo=t["paper"]))
    for e in spec["entities"]:
        x, y, w, h = pos[e["name"]]
        o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="#fff" stroke="{t["azul_med"]}" stroke-width="1.5"/>')
        o.append(f'<path d="M{x} {y+8}a8 8 0 0 1 8-8h{w-16}a8 8 0 0 1 8 8v{HEAD_H-8}h-{w}z" fill="{t["azul"]}"/>')
        o.append(svg_text(x + 12, y + 20, e["name"], 13, 700, "#fff", "start"))
        o.append(f'<rect x="{x}" y="{y+HEAD_H}" width="{w}" height="{VOL_H}" fill="{t["gris_light"]}"/>')
        o.append(svg_text(x + 12, y + HEAD_H + 14, vol_line(e), 10, 400, t["gris"], "start", mono=True))
        for i, c in enumerate(e.get("columns", [])):
            cy = y + HEAD_H + VOL_H + 15 + i * ROW_H
            badge = "PK" if c.get("pk") else "FK" if c.get("fk") else ""
            if badge:
                o.append(svg_text(x + 10, cy, badge, 9, 700, t["naranjo"] if c.get("pk") else t["azul_med"], "start", mono=True))
            o.append(svg_text(x + 34, cy, c["name"], 11, 600 if c.get("pk") else 400, t["azul"], "start", italic=bool(c.get("inferred"))))
            o.append(svg_text(x + w - 10, cy, c.get("type", ""), 10, 400, t["gris"], "end", mono=True))
    # tabla de crecimiento
    ty = Hd + 10
    o.append(svg_text(24, ty + 8, "Volúmenes y proyección de crecimiento", 14, 700, t["azul"], "start"))
    heads = ["Entidad", "Hoy", "+6 m", "+12 m", "+24 m", "+36 m", "Tamaño hoy", "Tamaño +36 m"]
    xs = [24, 270, 350, 430, 510, 590, 690, 800]
    ty += 22
    o.append(f'<rect x="20" y="{ty}" width="{W-40}" height="24" fill="{t["azul"]}" rx="4"/>')
    for hx, hd in zip(xs, heads):
        o.append(svg_text(hx + 4, ty + 16, hd, 10, 700, "#fff", "start", mono=True))
    for i, (n, r0, proj, s0, s36, v) in enumerate(tr):
        yy = ty + 26 + i * 26
        if i % 2 == 0:
            o.append(f'<rect x="20" y="{yy}" width="{W-40}" height="26" fill="{t["gris_light"]}"/>')
        o.append(svg_text(xs[0] + 4, yy + 17, n, 11, 600, t["azul"], "start"))
        vals = [human(r0)] + [human(p) for p in proj] + [human_bytes(s0), human_bytes(s36)]
        for k, (hx, val) in enumerate(zip(xs[1:], vals)):
            col = t["gris"]
            if k == 6 and s36 is not None and s36 > WARN_BYTES:
                col = t["rojo"]
            if k == 3 and r0 and proj[2] and proj[2] / r0 > 3:
                col = t["naranjo"]
            o.append(svg_text(hx + 4, yy + 17, val, 11, 400, col, "start", mono=True))
    o.append(svg_text(24, H - 8, "Naranjo = crece >3× en 24 m · Rojo = >10 GB a +36 m · [fuente] indica si el dato es medido o estimado · cursiva = columna inferida", 9, 400, t["gris"], "start", mono=True))
    o.append("</svg>")
    return "".join(o)


def to_drawio(spec, theme):
    t = theme
    pos, W, Hd, info = layout(spec)
    d = Drawio()
    d.vertex(f'<b><font style="font-size:20px" color="{t["azul"]}">{esc(spec.get("title", "Modelo de datos"))}</font></b><br>'
             f'<font style="font-size:11px" color="{t["gris"]}">{esc(spec.get("subtitle", ""))}</font>',
             "text;html=1;align=left;verticalAlign=top;whiteSpace=wrap;", 20, 10, W - 40, 50)
    ids = {}
    for e in spec["entities"]:
        x, y, w, h = pos[e["name"]]
        cid = d.vertex(f"<b>{esc(e['name'])}</b>",
                       f"swimlane;fontStyle=1;html=1;startSize={HEAD_H};horizontal=1;collapsible=0;fillColor={t['azul']};"
                       f"fontColor=#FFFFFF;strokeColor={t['azul_med']};swimlaneFillColor=#FFFFFF;rounded=1;arcSize=6;fontSize=13;align=left;spacingLeft=10;",
                       x, y, w, h)
        ids[e["name"]] = cid
        d.vertex(esc(vol_line(e)), f"text;html=1;align=left;verticalAlign=middle;fontSize=10;fontFamily=Courier New;fontColor={t['gris']};fillColor={t['gris_light']};spacingLeft=10;",
                 0, HEAD_H, w, VOL_H, parent=cid)
        for i, c in enumerate(e.get("columns", [])):
            badge = "PK " if c.get("pk") else "FK " if c.get("fk") else "   "
            it = "<i>" if c.get("inferred") else ""
            it2 = "</i>" if c.get("inferred") else ""
            col = t["naranjo"] if c.get("pk") else t["azul_med"]
            d.vertex(f'<font color="{col}" face="Courier New" style="font-size:9px"><b>{badge}</b></font> {it}{esc(c["name"])}{it2}'
                     f'<font color="{t["gris"]}" face="Courier New" style="font-size:10px">  {esc(c.get("type", ""))}</font>',
                     f"text;html=1;align=left;verticalAlign=middle;fontSize=11;fontColor={t['azul']};spacingLeft=8;{'fontStyle=2;' if c.get('inferred') else ''}",
                     0, HEAD_H + VOL_H + i * ROW_H, w, ROW_H, parent=cid)
    for a, b, card, fa, fb in relations(spec):
        if a in ids and b in ids:
            d.edge(ids[a], ids[b], f"edgeStyle=entityRelationEdgeStyle;html=1;endArrow=ERone;endFill=0;startArrow=ERmany;startFill=0;strokeColor={t['azul_med']};strokeWidth=1.5;")
    rows = table_rows(spec)
    head = "".join(f'<th align="left" style="padding:3px 10px;background:{t["azul"]};color:#fff">{h}</th>' for h in
                   ["Entidad", "Hoy", "+6 m", "+12 m", "+24 m", "+36 m", "Tamaño hoy", "Tamaño +36 m"])
    body = ""
    for n, r0, proj, s0, s36, v in rows:
        vals = [human(r0)] + [human(p) for p in proj] + [human_bytes(s0), human_bytes(s36)]
        cells = "".join(f'<td style="padding:3px 10px;color:{t["rojo"] if (i == 6 and s36 and s36 > WARN_BYTES) else t["gris"]}">{v}</td>' for i, v in enumerate(vals))
        body += f'<tr><td style="padding:3px 10px;color:{t["azul"]}"><b>{esc(n)}</b></td>{cells}</tr>'
    d.vertex(f'<b><font color="{t["azul"]}" style="font-size:14px">Volúmenes y proyección de crecimiento</font></b><br><br>'
             f'<table cellspacing="0" style="font-family:Courier New;font-size:11px"><tr>{head}</tr>{body}</table>',
             "text;html=1;align=left;verticalAlign=top;whiteSpace=wrap;overflow=fill;", 20, Hd + 10, W - 40, 40 + 26 * (len(rows) + 1))
    return d, W, Hd + 60 + 26 * (len(rows) + 1)


def to_mermaid(spec):
    L = ["erDiagram"]
    for a, b, card, fa, fb in relations(spec):
        L.append(f"  {b} ||--o{{ {a} : \"{fa.split('.')[1] if '.' in fa else ''}\"")
    for e in spec["entities"]:
        L.append(f"  {e['name']} {{")
        for c in e.get("columns", []):
            typ = (c.get("type") or "string").split("(")[0].replace(" ", "_") or "string"
            k = " PK" if c.get("pk") else " FK" if c.get("fk") else ""
            L.append(f"    {typ} {c['name']}{k}")
        L.append("  }")
    return "\n".join(L) + "\n"


def to_md(spec):
    L = [f"# {spec.get('title', 'Modelo de datos')}\n", spec.get("subtitle", ""), "\n## Volúmenes y crecimiento\n",
         "| Entidad | Hoy | +6 m | +12 m | +24 m | +36 m | Tamaño hoy | Tamaño +36 m | Fuente |", "|---|---|---|---|---|---|---|---|---|"]
    for n, r0, proj, s0, s36, v in table_rows(spec):
        L.append(f"| {n} | {human(r0)} | " + " | ".join(human(p) for p in proj) + f" | {human_bytes(s0)} | {human_bytes(s36)} | {(v or {}).get('source', 'sin medir')} |")
    L.append("\n> `sin medir` = falta dato real. Ver `references/volumenes.md` para las consultas de medición por motor.\n")
    L.append("## Diagrama (Mermaid)\n\n```mermaid\n" + to_mermaid(spec) + "```\n")
    return "\n".join(L)


def main(args):
    import argparse
    ap = argparse.ArgumentParser(prog="tdocs erd")
    ap.add_argument("spec", nargs="?", default="docs/spec/erd.json")
    ap.add_argument("-o", "--out", default="docs")
    ap.add_argument("--theme")
    a = ap.parse_args(args)
    spec, theme = read_json(a.spec), load_theme(a.theme)
    base = f"{a.out}/03-modelo-datos"
    write(f"{base}/modelo-datos.svg", to_svg(spec, theme))
    d, W, H = to_drawio(spec, theme)
    d.save(f"{base}/modelo-datos.drawio", "Modelo de datos", W, H)
    write(f"{base}/modelo-datos.mmd", to_mermaid(spec))
    write(f"{base}/volumenes.md", to_md(spec))
    miss = [e["name"] for e in spec["entities"] if not (e.get("volume") or {}).get("rows")]
    print(f"OK modelo de datos: {len(spec['entities'])} entidades → {base}/" + (f" · sin volumen medido: {', '.join(miss)}" if miss else ""))
