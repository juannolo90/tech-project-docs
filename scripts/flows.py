"""Paso 2 · Flujos de operación: flows.json -> SVG por flujo, flows.html y flows.md (Mermaid).

Tipos: "flowchart" (nodos start|process|decision|end|io) y "sequence" (actores + mensajes).
"""
import collections
from common import (load_theme, read_json, write, esc, wrap, svg_open, svg_text, svg_title, polyline, edge_style)

NW, NH, DH, GAPX, GAPY = 168, 52, 78, 40, 60


def ranks(nodes, edges):
    ids = [n["id"] for n in nodes]
    out = collections.defaultdict(list)
    for e in edges:
        out[e["from"]].append(e["to"])
    state, back = {}, set()

    def dfs(u):
        state[u] = 1
        for v in out[u]:
            if state.get(v) == 1:
                back.add((u, v))
            elif v not in state:
                dfs(v)
        state[u] = 2
    for i in ids[:1] + ids:
        if i not in state:
            dfs(i)
    r = {i: 0 for i in ids}
    for _ in range(len(ids)):
        ch = False
        for e in edges:
            if (e["from"], e["to"]) in back:
                continue
            if r[e["to"]] < r[e["from"]] + 1:
                r[e["to"]] = r[e["from"]] + 1
                ch = True
        if not ch:
            break
    return r, back


def flowchart_svg(f, t):
    nodes, edges = f["nodes"], f.get("edges", [])
    r, back = ranks(nodes, edges)
    byr = collections.defaultdict(list)
    for n in nodes:
        byr[r[n["id"]]].append(n)
    maxk = max(len(v) for v in byr.values())
    W = max(640, maxk * (NW + GAPX) + 160)
    pos = {}
    y = 90
    for rk in sorted(byr):
        k = len(byr[rk])
        hrow = max(DH if n.get("kind") == "decision" else NH for n in byr[rk])
        for i, n in enumerate(byr[rk]):
            cx = W / 2 + (i - (k - 1) / 2) * (NW + GAPX)
            pos[n["id"]] = (cx, y + hrow / 2, DH if n.get("kind") == "decision" else NH)
        y += hrow + GAPY
    H = y + 20
    o = [svg_open(W, H, t), svg_title(f.get("title", f["id"]), f.get("description", ""), t, W)]
    for e in edges:
        a, b = pos.get(e["from"]), pos.get(e["to"])
        if not a or not b:
            continue
        col, dash, mk = edge_style(e.get("kind", "internal"), t)
        if (e["from"], e["to"]) in back:
            left = b[0] < W / 2 - 1 or (b[0] <= min(p_[0] for p_ in pos.values() if abs(p_[1] - b[1]) < 2) + 1 and b[0] < max(p_[0] for p_ in pos.values()) - 1)
            if left:
                xr = min(p_[0] for p_ in pos.values()) - NW / 2 - 30
                pts = [(a[0] - NW / 2, a[1]), (xr, a[1]), (xr, b[1]), (b[0] - NW / 2 - 4, b[1])]
            else:
                xr = max(p_[0] for p_ in pos.values()) + NW / 2 + 30
                pts = [(a[0] + NW / 2, a[1]), (xr, a[1]), (xr, b[1]), (b[0] + NW / 2 + 4, b[1])]
            dash = "5 5"
        elif abs(a[0] - b[0]) < 2:
            pts = [(a[0], a[1] + a[2] / 2), (b[0], b[1] - b[2] / 2 - 4)]
        else:
            ym = b[1] - b[2] / 2 - GAPY / 2
            pts = [(a[0], a[1] + a[2] / 2), (a[0], ym), (b[0], ym), (b[0], b[1] - b[2] / 2 - 4)]
        o.append(polyline(pts, col, dash, mk))
        if e.get("label"):
            if len(pts) == 2:
                lx, ly, an = pts[0][0] + 8, (pts[0][1] + pts[1][1]) / 2 + 3, "start"
            else:
                lx, ly, an = (pts[1][0] + pts[2][0]) / 2, pts[1][1] - 6, "middle"
                if len(pts) == 4 and pts[1][0] == pts[2][0]:
                    lx, ly, an = pts[1][0] + (8 if pts[1][0] > W / 2 else -8), (pts[1][1] + pts[2][1]) / 2, "start" if pts[1][0] > W / 2 else "end"
            o.append(svg_text(lx, ly, e["label"], 10, 600, t["naranjo"], an, mono=True, halo=t["paper"]))
    for n in nodes:
        cx, cy, h = pos[n["id"]]
        kind = n.get("kind", "process")
        lines = wrap(n["label"], 22, 3)
        if kind in ("start", "end"):
            fill, stroke, tc = (t["azul"], t["azul"], "#fff") if kind == "start" else (t["verde"], t["verde"], "#fff")
            o.append(f'<rect x="{cx-NW/2}" y="{cy-h/2}" width="{NW}" height="{h}" rx="{h/2}" fill="{fill}" stroke="{stroke}"/>')
        elif kind == "decision":
            tc = t["azul"]
            o.append(f'<polygon points="{cx},{cy-h/2} {cx+NW/2},{cy} {cx},{cy+h/2} {cx-NW/2},{cy}" fill="#fff" stroke="{t["naranjo"]}" stroke-width="2"/>')
        elif kind == "io":
            tc = t["azul"]
            o.append(f'<polygon points="{cx-NW/2+12},{cy-h/2} {cx+NW/2},{cy-h/2} {cx+NW/2-12},{cy+h/2} {cx-NW/2},{cy+h/2}" fill="{t["gris_light"]}" stroke="{t["azul_med"]}"/>')
        elif kind == "risk":
            tc = t["rojo"]
            o.append(f'<rect x="{cx-NW/2}" y="{cy-h/2}" width="{NW}" height="{h}" rx="8" fill="#fff" stroke="{t["rojo"]}" stroke-width="1.8"/>')
        else:
            tc = t["azul"]
            o.append(f'<rect x="{cx-NW/2}" y="{cy-h/2}" width="{NW}" height="{h}" rx="8" fill="#fff" stroke="{t["azul_med"]}" stroke-width="1.5"/>')
        y0 = cy - (len(lines) - 1) * 7 + 4
        for i, ln in enumerate(lines):
            o.append(svg_text(cx, y0 + i * 14, ln, 11.5, 600, tc))
    o.append("</svg>")
    return "".join(o), W, H


def sequence_svg(f, t):
    actors, msgs = f["actors"], f.get("messages", [])
    step = 190
    W = max(640, 100 + len(actors) * step)
    xs = {a["id"]: 100 + i * step for i, a in enumerate(actors)}
    H = 130 + len(msgs) * 52 + 40
    o = [svg_open(W, H, t), svg_title(f.get("title", f["id"]), f.get("description", ""), t, W)]
    for a in actors:
        x = xs[a["id"]]
        o.append(f'<line x1="{x}" y1="124" x2="{x}" y2="{H-24}" stroke="{t["gris"]}" stroke-dasharray="4 5"/>')
        o.append(f'<rect x="{x-70}" y="84" width="140" height="40" rx="8" fill="{t["azul"]}"/>')
        for i, ln in enumerate(wrap(a["label"], 18, 2)):
            o.append(svg_text(x, 108 + i * 13 - (6 if len(wrap(a["label"], 18, 2)) > 1 else 0), ln, 12, 600, "#fff"))
    for i, m in enumerate(msgs):
        y = 160 + i * 52
        x1, x2 = xs[m["from"]], xs[m["to"]]
        ret = m.get("kind") == "return"
        col, dash = (t["azul_med"], "5 5") if ret else (t["naranjo"], "")
        mk = "ar-b" if ret else "ar-a"
        if x1 == x2:
            o.append(polyline([(x1, y - 8), (x1 + 44, y - 8), (x1 + 44, y + 10), (x1 + 3, y + 10)], col, dash, mk))
            o.append(svg_text(x1 + 52, y + 3, f"{i+1}. {m['label']}", 11, 400, t["azul"], "start"))
        else:
            d = 4 if x2 > x1 else -4
            o.append(polyline([(x1 + d, y), (x2 - d, y)], col, dash, mk))
            o.append(svg_text((x1 + x2) / 2, y - 8, f"{i+1}. {m['label']}", 11, 400, t["azul"], halo=t["paper"]))
    o.append("</svg>")
    return "".join(o), W, H


def mermaid(f):
    if f.get("type") == "sequence":
        L = ["sequenceDiagram"]
        for a in f["actors"]:
            L.append(f"  participant {a['id']} as {a['label']}")
        for m in f.get("messages", []):
            L.append(f"  {m['from']}{'-->>' if m.get('kind') == 'return' else '->>'}{m['to']}: {m['label']}")
        return "\n".join(L)
    L = ["flowchart TD"]
    shape = {"start": ("([", "])"), "end": ("([", "])"), "decision": ("{", "}"), "io": ("[/", "/]"), "risk": ("[", "]")}
    for n in f["nodes"]:
        a, b = shape.get(n.get("kind", "process"), ("[", "]"))
        L.append(f"  {n['id']}{a}\"{n['label']}\"{b}")
    for e in f.get("edges", []):
        L.append(f"  {e['from']} -->{'|' + e['label'] + '|' if e.get('label') else ''} {e['to']}")
    return "\n".join(L)


def main(args):
    import argparse
    ap = argparse.ArgumentParser(prog="tdocs flows")
    ap.add_argument("spec", nargs="?", default="docs/spec/flows.json")
    ap.add_argument("-o", "--out", default="docs")
    ap.add_argument("--theme")
    a = ap.parse_args(args)
    spec, t = read_json(a.spec), load_theme(a.theme)
    base = f"{a.out}/01-flujos"
    html, md = [], [f"# {spec.get('title', 'Flujos de operación')}\n"]
    for f in spec["flows"]:
        svg, W, H = (sequence_svg if f.get("type") == "sequence" else flowchart_svg)(f, t)
        write(f"{base}/flujo-{f['id']}.svg", svg)
        html.append(f'<section><h2>{esc(f.get("title", f["id"]))}</h2><p>{esc(f.get("description", ""))}</p>{svg}</section>')
        md += [f"## {f.get('title', f['id'])}\n", f.get("description", "") + "\n", f"![{f['id']}](flujo-{f['id']}.svg)\n",
               "<details><summary>Mermaid</summary>\n\n```mermaid\n" + mermaid(f) + "\n```\n</details>\n"]
    write(f"{base}/flujos.html", f'<!doctype html><meta charset="utf-8"><title>Flujos</title><body style="font-family:Inter,Arial;margin:24px;color:{t["azul"]}">'
          + "".join(html) + "</body>")
    write(f"{base}/flujos.md", "\n".join(md))
    print(f"OK flujos: {len(spec['flows'])} → {base}/")
