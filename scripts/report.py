"""Paso 6 · documentacion.html: TODO lo generado en un solo HTML autocontenido, en pestañas o en modo presentación (diapositivas).

  tdocs.py report -o docs [--title "…"] [--mask-ips]

Pestañas: Resumen · Grafo · Flujos · Arquitectura · Red · Datos y volúmenes · Pendientes.
Las secciones que no se generaron aparecen deshabilitadas (no se inventa contenido). Navegación: clic, ← → y tecla P = presentación.
"""
import base64, html as H, json, pathlib, re
from common import esc, write, read_json

IP4 = re.compile(r"(?<![\w.])((?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3})(?![\w]|\.\d)")


def b64(path, mime):
    return f"data:{mime};base64," + base64.b64encode(pathlib.Path(path).read_bytes()).decode()


def img(path, alt):
    return f'<img class="dia" alt="{esc(alt)}" src="{b64(path, "image/svg+xml")}">'


def iframe(path, title):
    doc = pathlib.Path(path).read_text(encoding="utf-8")
    return f'<iframe class="fr" title="{esc(title)}" srcdoc="{H.escape(doc, quote=True)}"></iframe>'


def md_table(md):
    """Convierte las tablas y listas simples de nuestros .md a HTML (sin dependencias)."""
    out, rows, lst = [], [], []

    def flush_t():
        if rows:
            head, body = rows[0], rows[2:]
            out.append("<table><tr>" + "".join(f"<th>{esc(c)}</th>" for c in head) + "</tr>"
                       + "".join("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in r) + "</tr>" for r in body) + "</table>")
            rows.clear()

    def flush_l():
        if lst:
            out.append("<ol>" + "".join(f"<li>{esc(x)}</li>" for x in lst) + "</ol>")
            lst.clear()
    fence = False
    for ln in md.splitlines():
        if ln.startswith("```"):
            fence = not fence
            continue
        if fence:
            continue
        if ln.startswith("|"):
            flush_l()
            rows.append([c.strip() for c in ln.strip().strip("|").split("|")])
            continue
        flush_t()
        m = re.match(r"\s*(?:\d+\.|-)\s+(.*)", ln)
        if m:
            lst.append(m.group(1))
            continue
        flush_l()
        if ln.startswith("#"):
            out.append(f"<h3>{esc(ln.lstrip('# ').strip())}</h3>")
        elif ln.strip() and not ln.startswith(">"):
            out.append(f"<p>{esc(ln.strip())}</p>")
        elif ln.startswith(">"):
            out.append(f'<p class="hint">{esc(ln.lstrip("> ").strip())}</p>')
    flush_t()
    flush_l()
    return "".join(out)


def sec_resumen(d, title):
    g = d / "00-grafo" / "graph.json"
    L = [f"<h2>{esc(title)}</h2>"]
    if g.exists():
        j = read_json(g)
        langs = ", ".join(f"{k} ({v:,} líneas)" for k, v in sorted(j.get("languages", {}).items(), key=lambda x: -x[1])[:5])
        nh = j.get("network_hints") or {}
        facts = [("Archivos de código", len(j.get("nodes", []))), ("Dependencias internas", len(j.get("edges", []))),
                 ("Puntos de entrada", len(j.get("entry_points", []))), ("Rutas / tools expuestas", len(j.get("routes", []))),
                 ("Componentes sugeridos", len(j.get("suggested_components", []))), ("Tablas (DDL)", len(j.get("schema_ddl", []))),
                 ("Tablas referenciadas en código", len(j.get("tables_referenced_in_code", []))), ("IPs / hosts detectados", len(nh.get("ips", [])) + len(nh.get("hosts", [])))]
        L.append('<div class="kpis">' + "".join(f'<div class="kpi"><b>{v}</b><span>{esc(k)}</span></div>' for k, v in facts) + "</div>")
        if langs:
            L.append(f"<p>Lenguajes: {esc(langs)}</p>")
        if j.get("entry_points"):
            L.append("<h3>Puntos de entrada</h3><ul>" + "".join(f"<li><code>{esc(e)}</code></li>" for e in j["entry_points"][:12]) + "</ul>")
    L.append("<h3>Contenido</h3><ul>" + "".join(f"<li>{n}</li>" for n in ("Grafo del código", "Flujos de operación", "Arquitectura", "Red y despliegue", "Modelo de datos y volúmenes", "Pendientes por confirmar")) + "</ul>")
    L.append('<p class="hint">Usa las pestañas, las flechas ← → o la tecla <b>P</b> para presentar como diapositivas.</p>')
    return "".join(L)


def build(out_dir, title, mask):
    d = pathlib.Path(out_dir)
    tabs = []  # (id, nombre, html|None)
    tabs.append(("resumen", "Resumen", sec_resumen(d, title)))
    gh = d / "00-grafo" / "graph.html"
    tabs.append(("grafo", "Grafo", iframe(gh, "Grafo") if gh.exists() else None))
    fl = sorted((d / "01-flujos").glob("flujo-*.svg")) if (d / "01-flujos").exists() else []
    meta = {}
    sp = d / "spec" / "flows.json"
    if sp.exists():
        try:
            meta = {f["id"]: f for f in read_json(sp).get("flows", [])}
        except Exception:
            pass
    if fl:
        parts = []
        for f in fl:
            fid = f.stem.replace("flujo-", "")
            m = meta.get(fid, {})
            parts.append(f'<div class="card"><h3>{esc(m.get("title", fid))}</h3><p class="hint">{esc(m.get("description", ""))}</p>{img(f, m.get("title", fid))}</div>')
        tabs.append(("flujos", "Flujos", "".join(parts)))
    else:
        tabs.append(("flujos", "Flujos", None))
    ar = d / "02-arquitectura" / "arquitectura.svg"
    tabs.append(("arq", "Arquitectura", img(ar, "Arquitectura") if ar.exists() else None))
    rd = d / "02-arquitectura" / "red.html"
    tabs.append(("red", "Red", iframe(rd, "Red y despliegue") if rd.exists() else None))
    mo = d / "03-modelo-datos" / "modelo-datos.svg"
    if mo.exists():
        vm = d / "03-modelo-datos" / "volumenes.md"
        extra = ""
        if vm.exists():
            extra = '<div class="card">' + md_table(vm.read_text(encoding="utf-8")) + "</div>"
        tabs.append(("datos", "Datos y volúmenes", img(mo, "Modelo de datos") + extra))
    else:
        tabs.append(("datos", "Datos y volúmenes", None))
    pend = []
    for f, lab in (("02-arquitectura/arquitectura-pendientes.md", "Arquitectura"), ("02-arquitectura/red-pendientes.md", "Red")):
        p = d / f
        if p.exists():
            items = [re.sub(r"^\d+\.\s*", "", x) for x in p.read_text(encoding="utf-8").splitlines() if re.match(r"\d+\.", x)]
            if items:
                pend.append(f'<div class="card"><h3>{lab}</h3><ol>' + "".join(f"<li>{esc(i)}</li>" for i in items) + "</ol></div>")
    spec = d / "spec" / "erd.json"
    if spec.exists():
        try:
            miss = [e["name"] for e in read_json(spec).get("entities", []) if not (e.get("volume") or {}).get("rows") and (e.get("volume") or {}).get("rows_per_month") is None]
            if miss:
                pend.append('<div class="card"><h3>Volúmenes</h3><p>Sin medir ni supuesto: ' + esc(", ".join(miss))
                            + '. Ejecuta <code>consultas-volumen.sql</code> (solo lectura) o indica una tasa diaria.</p></div>')
        except Exception:
            pass
    tabs.append(("pend", f"Pendientes{' (' + str(len(pend)) + ')' if pend else ''}", "".join(pend) or '<p>Sin pendientes registrados.</p>'))
    return tabs


CSS = """
:root{--ink:#1B3A5C;--muted:#64748B;--bg:#F1F5F9;--panel:#FFFFFF;--line:#E2E8F0;--accent:#E8811A}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--ink:#E6EDF6;--muted:#9AA9BC;--bg:#0B121C;--panel:#16202E;--line:#243247}}
*{box-sizing:border-box}html,body{height:100%;margin:0}body{background:var(--bg);color:var(--ink);font:14px/1.5 Inter,Helvetica,Arial,sans-serif;display:flex;flex-direction:column}
header{display:flex;align-items:center;gap:14px;padding:10px 18px;background:var(--panel);border-bottom:1px solid var(--line);flex-wrap:wrap}
h1{font-size:16px;margin:0 8px 0 0}nav{display:flex;gap:4px;flex-wrap:wrap;flex:1}
nav button{border:0;background:none;color:var(--muted);font:inherit;padding:7px 12px;border-radius:8px;cursor:pointer}nav button:hover{background:var(--bg)}
nav button.on{background:var(--ink);color:var(--panel)}nav button:disabled{opacity:.35;cursor:not-allowed}
.pbtn{border:1px solid var(--line);background:var(--panel);color:var(--ink);border-radius:8px;padding:6px 12px;cursor:pointer;font:inherit}
main{flex:1;min-height:0;position:relative}.pane{display:none;height:100%;overflow:auto;padding:18px 22px}.pane.on{display:block}
.pane.fill{padding:0}.fr{width:100%;height:100%;border:0;display:block;background:var(--bg)}
.dia{max-width:100%;height:auto;display:block;margin:0 auto 14px;background:#fff;border:1px solid var(--line);border-radius:10px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:0 0 14px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:12px 0}.kpi{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px}
.kpi b{display:block;font-size:24px}.kpi span{color:var(--muted);font-size:12px}
table{border-collapse:collapse;width:100%;font-size:12.5px}th,td{text-align:left;padding:5px 8px;border-bottom:1px solid var(--line)}th{color:var(--muted)}
h2{margin:0 0 6px}h3{margin:10px 0 4px}.hint{color:var(--muted);font-size:12px}code{font-family:Consolas,monospace}
footer{display:none;padding:6px 18px;color:var(--muted);font-size:12px;justify-content:space-between}
body.present header nav button{font-size:13px}body.present footer{display:flex}body.present .pane{padding:28px 36px}body.present .pane:not(.fill) h2{font-size:30px}
"""
JS = """
const T=[...document.querySelectorAll('nav button[data-t]')];let cur=0;
function show(i){if(T[i].disabled)return;cur=i;T.forEach((b,k)=>b.classList.toggle('on',k===i));document.querySelectorAll('.pane').forEach((p,k)=>p.classList.toggle('on',k===i));
 document.getElementById('pg').textContent=(i+1)+' / '+T.length;location.hash=T[i].dataset.t}
function step(d){let i=cur;do{i=(i+d+T.length)%T.length}while(T[i].disabled);show(i)}
T.forEach((b,i)=>b.onclick=()=>show(i));
function pres(){document.body.classList.toggle('present');if(document.body.classList.contains('present')&&document.documentElement.requestFullscreen)document.documentElement.requestFullscreen().catch(()=>{});
 else if(document.fullscreenElement)document.exitFullscreen()}
document.getElementById('pbtn').onclick=pres;
addEventListener('keydown',e=>{if(e.target.tagName==='INPUT')return;if(e.key==='ArrowRight')step(1);else if(e.key==='ArrowLeft')step(-1);else if(e.key==='p'||e.key==='P')pres();else if(e.key==='Escape'&&document.body.classList.contains('present'))document.body.classList.remove('present')});
const h=location.hash.slice(1);const k=T.findIndex(b=>b.dataset.t===h&&!b.disabled);show(k>=0?k:0);
"""


def render(out_dir, title, mask):
    tabs = build(out_dir, title, mask)
    nav = "".join(f'<button data-t="{i}"{"" if c else " disabled"} title="{"" if c else "no generado"}">{esc(n)}</button>' for i, n, c in tabs)
    panes = "".join(f'<section class="pane{" fill" if i in ("grafo", "red") else ""}">{c or ""}</section>' for i, n, c in tabs)
    h = (f'<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title>'
         f'<style>{CSS}</style></head><body><header><h1>{esc(title)}</h1><nav>{nav}</nav><button class="pbtn" id="pbtn" title="Tecla P">▶ Presentar</button></header>'
         f'<main>{panes}</main><footer><span>{esc(title)}</span><span id="pg"></span></footer><script>{JS}</script></body></html>')
    return IP4.sub(lambda m: ".".join(m.group(1).split(".")[:2]) + ".x.x", h) if mask else h


def main(args):
    import argparse
    ap = argparse.ArgumentParser(prog="tdocs report")
    ap.add_argument("-o", "--out", default="docs")
    ap.add_argument("--title", default="Documentación del proyecto tecnológico")
    ap.add_argument("--mask-ips", action="store_true")
    a = ap.parse_args(args)
    html = render(a.out, a.title, a.mask_ips)
    p = pathlib.Path(a.out) / "documentacion.html"
    write(p, html)
    miss = [n for i, n, c in build(a.out, a.title, a.mask_ips) if not c]
    print(f"OK documentación → {p}" + (f" · secciones sin generar: {', '.join(miss)}" if miss else ""))
