"""Paso 1b · graph.html: visor interactivo del grafo (sin dependencias, sin red) + importador de grafos ya generados.

  tdocs.py graph [graph.json] -o docs               regenera graph.html desde un graph.json existente (no relee el código)
  tdocs.py graph --from graphify-out/graph.json     importa un grafo node-link ya generado (graphify, networkx…) y dibuja su HTML

Reutilizar un grafo existente NO cuesta tokens ni relectura del repo: solo se transforma el JSON.
"""
import collections, json, pathlib
from common import read_json, write, esc

MAX_NODES = 450
PALETTE = ["#2C7BC4", "#E8811A", "#10B981", "#7C3AED", "#EF4444", "#0EA5E9", "#B7791F", "#EC4899", "#14B8A6", "#6366F1", "#84CC16", "#F59E0B"]


def import_nodelink(path):
    """Convierte un grafo node-link (nodes + links|edges) a nuestro esquema mínimo. Tolerante a campos distintos."""
    j = read_json(path)
    raw_nodes = j.get("nodes") or []
    raw_edges = j.get("links") or j.get("edges") or []
    nodes, deg = {}, collections.Counter()
    for n in raw_nodes:
        nid = str(n.get("id") if n.get("id") is not None else n.get("label", len(nodes)))
        comm = n.get("community", n.get("group", n.get("cluster")))
        nodes[nid] = {"id": nid, "label": str(n.get("label") or n.get("name") or nid), "lang": str(n.get("file_type") or n.get("type") or n.get("lang") or ""),
                      "file": str(n.get("source_file") or n.get("file") or n.get("path") or ""), "loc": int(n.get("loc") or 0),
                      "community": str(comm) if comm is not None else "(sin comunidad)"}
    edges = []
    for e in raw_edges:
        a, b = e.get("source", e.get("from")), e.get("target", e.get("to"))
        if a is None or b is None:
            continue
        a, b = str(a), str(b)
        if a in nodes and b in nodes and a != b:
            edges.append({"from": a, "to": b, "rel": str(e.get("relation") or e.get("label") or "")})
            deg[a] += 1
            deg[b] += 1
    for n in nodes.values():
        n["degree"] = deg[n["id"]]
    return {"root": pathlib.Path(path).resolve().parent.parent.name, "nodes": list(nodes.values()), "edges": edges, "imported_from": str(path)}


def prepare(graph):
    nodes = sorted(graph["nodes"], key=lambda n: -n.get("degree", 0))
    cut = len(nodes) > MAX_NODES
    nodes = nodes[:MAX_NODES]
    ids = {n["id"] for n in nodes}
    comms = collections.Counter(n.get("community", "(raíz)") for n in nodes)
    order = [c for c, _ in comms.most_common()]
    col = {c: PALETTE[i % len(PALETTE)] for i, c in enumerate(order)}
    data = {"nodes": [{"id": n["id"], "l": n.get("label") or n["id"].split("/")[-1], "c": order.index(n.get("community", "(raíz)")),
                       "d": n.get("degree", 0), "g": n.get("lang", ""), "loc": n.get("loc", 0), "f": n.get("file") or n["id"]} for n in nodes],
            "edges": [{"a": e["from"], "b": e["to"]} for e in graph["edges"] if e["from"] in ids and e["to"] in ids],
            "comms": [{"n": c, "color": col[c], "k": comms[c]} for c in order]}
    return data, cut, len(graph["nodes"])


CSS = """
:root{--ink:#1B3A5C;--muted:#64748B;--bg:#F8FAFC;--panel:#FFFFFF;--line:#E2E8F0}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--ink:#E6EDF6;--muted:#9AA9BC;--bg:#0F1722;--panel:#16202E;--line:#243247}}
*{box-sizing:border-box}html,body{height:100%;margin:0}body{background:var(--bg);color:var(--ink);font:13px/1.45 Inter,Helvetica,Arial,sans-serif;display:flex;flex-direction:column}
header{padding:12px 16px;display:flex;gap:12px;align-items:center;flex-wrap:wrap;border-bottom:1px solid var(--line)}h1{font-size:16px;margin:0}
input{border:1px solid var(--line);background:var(--panel);color:var(--ink);border-radius:8px;padding:6px 10px;font:inherit;min-width:220px}
.hint{color:var(--muted)}.wrap{flex:1;display:flex;min-height:0}#c{flex:1;display:block;cursor:grab;min-width:0}
aside{width:290px;border-left:1px solid var(--line);background:var(--panel);padding:12px;overflow:auto}
aside h2{font-size:12px;margin:12px 0 6px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
.lg{display:flex;gap:8px;align-items:center;padding:3px 4px;border-radius:6px;cursor:pointer}.lg:hover{background:var(--bg)}.lg.off{opacity:.35}
.dot{width:11px;height:11px;border-radius:50%;flex:none}code{font-family:Consolas,monospace;font-size:12px;word-break:break-all}
ul{margin:4px 0;padding-left:16px}li{margin:2px 0}
@media(max-width:760px){.wrap{flex-direction:column}aside{width:auto;max-height:36%;border-left:0;border-top:1px solid var(--line)}}
"""
JS = r"""
const D=JSON.parse(document.getElementById('d').textContent);const cv=document.getElementById('c'),cx=cv.getContext('2d');
const css=getComputedStyle(document.documentElement);let W=0,H=0,dpr=window.devicePixelRatio||1;
function size(){const r=cv.getBoundingClientRect();W=r.width;H=r.height;cv.width=W*dpr;cv.height=H*dpr;}
const N=D.nodes.map((n,i)=>({...n,i,x:(Math.random()-.5)*600,y:(Math.random()-.5)*600,vx:0,vy:0,r:4+Math.sqrt(n.d)*2.2,on:true}));
const byId=Object.fromEntries(N.map(n=>[n.id,n]));const E=D.edges.map(e=>({a:byId[e.a],b:byId[e.b]}));
const adj=N.map(()=>new Set());E.forEach(e=>{adj[e.a.i].add(e.b.i);adj[e.b.i].add(e.a.i)});
let tx=0,ty=0,k=1,sel=null,hov=null,drag=null,alpha=1,off=new Set(),q='';
function tick(){if(alpha<.01)return;const n=N.length;
 for(let i=0;i<n;i++){const a=N[i];if(!a.on)continue;for(let j=i+1;j<n;j++){const b=N[j];if(!b.on)continue;let dx=a.x-b.x,dy=a.y-b.y,d2=dx*dx+dy*dy+.01;if(d2>90000)continue;const f=1400/d2;dx*=f;dy*=f;a.vx+=dx;a.vy+=dy;b.vx-=dx;b.vy-=dy}}
 for(const e of E){if(!e.a.on||!e.b.on)continue;const dx=e.b.x-e.a.x,dy=e.b.y-e.a.y,d=Math.sqrt(dx*dx+dy*dy)+.01,f=(d-70)*.012;e.a.vx+=dx/d*f;e.a.vy+=dy/d*f;e.b.vx-=dx/d*f;e.b.vy-=dy/d*f}
 for(const a of N){a.vx-=a.x*.0025;a.vy-=a.y*.0025;if(a===drag)continue;a.x+=a.vx*alpha;a.y+=a.vy*alpha;a.vx*=.82;a.vy*=.82}
 alpha*=.992}
const hl=()=>{const s=new Set();if(sel!=null){s.add(sel.i);adj[sel.i].forEach(x=>s.add(x))}return s};
function draw(){cx.setTransform(dpr,0,0,dpr,0,0);cx.clearRect(0,0,W,H);cx.translate(W/2+tx,H/2+ty);cx.scale(k,k);
 const h=hl(),dim=sel!=null||q;const m=n=>!q||n.l.toLowerCase().includes(q)||n.f.toLowerCase().includes(q);
 cx.lineWidth=1/k;for(const e of E){if(!e.a.on||!e.b.on)continue;const act=sel&&(e.a===sel||e.b===sel);cx.strokeStyle=act?css.getPropertyValue('--ink'):'rgba(120,135,155,'+(dim?.12:.35)+')';cx.lineWidth=(act?2:1)/k;cx.beginPath();cx.moveTo(e.a.x,e.a.y);cx.lineTo(e.b.x,e.b.y);cx.stroke()}
 for(const n of N){if(!n.on)continue;const a=(!dim)||h.has(n.i)||(q&&m(n))?1:.15;cx.globalAlpha=a;cx.fillStyle=D.comms[n.c].color;cx.beginPath();cx.arc(n.x,n.y,n.r,0,7);cx.fill();
  if(n===sel||n===hov){cx.lineWidth=2/k;cx.strokeStyle=css.getPropertyValue('--ink');cx.stroke()}}
 cx.globalAlpha=1;cx.font=(11/k)+'px sans-serif';cx.fillStyle=css.getPropertyValue('--ink');cx.textAlign='center';
 for(const n of N){if(!n.on)continue;if(n===sel||n===hov||h.has(n.i)&&sel||(k>1.4&&n.d>1)||(q&&m(n)))cx.fillText(n.l,n.x,n.y-n.r-3/k)}}
let fitted=false;function loop(){if(!fitted){size();if(W>50&&H>50){fit();fitted=true}}tick();draw();requestAnimationFrame(loop)}
const pos=e=>{const r=cv.getBoundingClientRect();return[(e.clientX-r.left-W/2-tx)/k,(e.clientY-r.top-H/2-ty)/k]};
const pick=e=>{const[x,y]=pos(e);let b=null,bd=1e9;for(const n of N){if(!n.on)continue;const d=Math.hypot(n.x-x,n.y-y);if(d<n.r+3/k&&d<bd){b=n;bd=d}}return b};
let pan=null;cv.onmousedown=e=>{const n=pick(e);if(n){drag=n;alpha=.4}else pan=[e.clientX-tx,e.clientY-ty]};
window.onmousemove=e=>{if(drag){[drag.x,drag.y]=pos(e);alpha=Math.max(alpha,.2)}else if(pan){tx=e.clientX-pan[0];ty=e.clientY-pan[1]}else{hov=pick(e);cv.style.cursor=hov?'pointer':'grab'}};
window.onmouseup=e=>{if(drag){drag=null}else if(pan){const moved=Math.abs(e.clientX-pan[0]-tx)+Math.abs(e.clientY-pan[1]-ty);pan=null}};
cv.onclick=e=>{const n=pick(e);sel=n===sel?null:n;info()};
cv.onwheel=e=>{e.preventDefault();const f=e.deltaY<0?1.12:.89;const[x,y]=pos(e);k=Math.min(6,Math.max(.2,k*f));const r=cv.getBoundingClientRect();tx=e.clientX-r.left-W/2-x*k;ty=e.clientY-r.top-H/2-y*k};
function info(){const el=document.getElementById('info');el.textContent='';if(!sel){el.append('Haz clic en un nodo para ver sus conexiones.');return}
 const h=document.createElement('div');const c=document.createElement('code');c.textContent=sel.f;h.append(c);el.append(h);
 const m=document.createElement('p');m.className='hint';m.textContent=[sel.g,sel.loc?sel.loc+' líneas':'',sel.d+' conexiones'].filter(Boolean).join(' · ');el.append(m);
 const ul=document.createElement('ul');[...adj[sel.i]].forEach(i=>{const li=document.createElement('li');li.textContent=N[i].l;li.style.cursor='pointer';li.onclick=()=>{sel=N[i];info()};ul.append(li)});el.append(ul)}
const lg=document.getElementById('lg');D.comms.forEach((c,i)=>{const d=document.createElement('div');d.className='lg';const s=document.createElement('span');s.className='dot';s.style.background=c.color;
 const t=document.createElement('span');t.textContent=c.n+' ('+c.k+')';d.append(s,t);d.onclick=()=>{off.has(i)?off.delete(i):off.add(i);d.classList.toggle('off',off.has(i));N.forEach(n=>n.on=!off.has(n.c));alpha=.5};lg.append(d)});
document.getElementById('q').oninput=e=>{q=e.target.value.trim().toLowerCase()};
function fit(){let x0=1e9,y0=1e9,x1=-1e9,y1=-1e9;N.forEach(n=>{x0=Math.min(x0,n.x);x1=Math.max(x1,n.x);y0=Math.min(y0,n.y);y1=Math.max(y1,n.y)});
 const w=Math.max(x1-x0,50),h=Math.max(y1-y0,50);k=Math.min(2,Math.max(.2,Math.min(W/(w+80),H/(h+80))));tx=-((x0+x1)/2)*k;ty=-((y0+y1)/2)*k}
addEventListener('resize',size);size();info();for(let i=0;i<260;i++)tick();loop();
"""


def build_html(graph, title=None):
    data, cut, total = prepare(graph)
    t = title or f"Grafo · {graph.get('root', 'proyecto')}"
    note = (f"Se muestran los {MAX_NODES} nodos de mayor conexión de {total}. Filtra por comunidad o usa el buscador." if cut else f"{total} nodos · {len(data['edges'])} conexiones")
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return (f'<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(t)}</title>'
            f"<style>{CSS}</style></head><body><header><h1>{esc(t)}</h1><input id=\"q\" placeholder=\"Buscar archivo o módulo…\">"
            f'<span class="hint">{esc(note)} · rueda = zoom · arrastra = mover</span></header>'
            f'<div class="wrap"><canvas id="c"></canvas><aside><h2>Selección</h2><div id="info"></div><h2>Comunidades (clic para ocultar)</h2><div id="lg"></div></aside></div>'
            f'<script id="d" type="application/json">{payload}</script><script>{JS}</script></body></html>')


def write_html(graph, out_dir):
    p = pathlib.Path(out_dir) / "00-grafo" / "graph.html"
    write(p, build_html(graph))
    return p


def main(args):
    import argparse
    ap = argparse.ArgumentParser(prog="tdocs graph")
    ap.add_argument("graph", nargs="?", default="docs/00-grafo/graph.json")
    ap.add_argument("-o", "--out", default="docs")
    ap.add_argument("--from", dest="src", help="grafo node-link ya generado (p. ej. graphify-out/graph.json)")
    a = ap.parse_args(args)
    g = import_nodelink(a.src) if a.src else read_json(a.graph)
    if a.src:
        dest = pathlib.Path(a.out) / "00-grafo" / "graph.json"
        if not dest.exists():  # no pisa el grafo propio (trae rutas, env, red…)
            write(dest, json.dumps(g, indent=2, ensure_ascii=False))
    p = write_html(g, a.out)
    print(f"OK graph.html ({len(g['nodes'])} nodos, {len(g['edges'])} aristas) → {p}  [sin releer el código]")
