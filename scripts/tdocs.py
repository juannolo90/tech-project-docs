#!/usr/bin/env python3
"""tech-project-docs · CLI único.

  tdocs.py analyze <repo> -o docs          1) grafo del proyecto (+ IPs/hosts/segmentos detectados; --mask-ips)
  tdocs.py flows   [spec] -o docs          2) flujos de operación
  tdocs.py arch    [spec] -o docs          3) arquitectura (.drawio + .svg)
  tdocs.py net-init [graph] -o spec        3b) borrador de red (sitios, segmentos, IPs) desde el grafo
  tdocs.py net     [spec] -o docs          3b) arquitectura de red HTML interactiva (+ .svg, pendientes)
  tdocs.py erd     [spec] -o docs          4) modelo ER con volúmenes
  tdocs.py png     -o docs                 renderiza los .svg a .png (requiere playwright) para revisarlos
  tdocs.py index   -o docs                 arma docs/README.md
"""
import sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))


def png(args):
    import argparse
    ap = argparse.ArgumentParser(prog="tdocs png")
    ap.add_argument("-o", "--out", default="docs")
    ap.add_argument("--scale", type=float, default=2)
    a = ap.parse_args(args)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright no está instalado: pip install playwright && python3 -m playwright install chromium")
        return 1
    svgs = sorted(pathlib.Path(a.out).rglob("*.svg"))
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(device_scale_factor=a.scale)
        for s in svgs:
            pg.goto(s.resolve().as_uri())
            dims = pg.evaluate("(()=>{const e=document.documentElement;return [e.width.baseVal.value,e.height.baseVal.value]})()")
            pg.set_viewport_size({"width": int(dims[0]), "height": int(dims[1])})
            pg.screenshot(path=str(s.with_suffix(".png")))
            print("png", s.with_suffix(".png"))
        b.close()


def index(args):
    import argparse
    from common import write
    ap = argparse.ArgumentParser(prog="tdocs index")
    ap.add_argument("-o", "--out", default="docs")
    ap.add_argument("--title", default="Documentación del proyecto tecnológico")
    a = ap.parse_args(args)
    out = pathlib.Path(a.out)
    L = [f"# {a.title}\n"]
    rep = out / "00-grafo" / "GRAPH_REPORT.md"
    sections = [("00-grafo", "Entendimiento del proyecto (grafo)"), ("01-flujos", "Flujos de operación"),
                ("02-arquitectura", "Arquitectura"), ("03-modelo-datos", "Modelo de datos y volúmenes")]
    for d, name in sections:
        p = out / d
        if not p.exists():
            continue
        L.append(f"\n## {name}\n")
        for f in sorted(p.iterdir()):
            if f.suffix == ".png" and (f.with_suffix(".svg")).exists():
                L.append(f"![{f.stem}]({d}/{f.name})\n")
        for f in sorted(p.iterdir()):
            if f.suffix in (".drawio", ".md", ".html", ".json", ".mmd"):
                L.append(f"- [{f.name}]({d}/{f.name})")
    L.append("\n---\nGenerado con [tech-project-docs](https://github.com/juannolo90/tech-project-docs).")
    write(out / "README.md", "\n".join(L) + "\n")
    print(f"OK índice → {out}/README.md")


def main():
    for s in (sys.stdout, sys.stderr):  # Windows: evita UnicodeEncodeError con cp1252
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    cmds = {"analyze": lambda a: __import__("analyze").main(a), "flows": lambda a: __import__("flows").main(a),
            "arch": lambda a: __import__("arch").main(a), "net": lambda a: __import__("net").main(a),
            "net-init": lambda a: __import__("net").main_init(a), "erd": lambda a: __import__("erd").main(a), "png": png, "index": index}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        print(__doc__)
        sys.exit(1)
    sys.exit(cmds[sys.argv[1]](sys.argv[2:]) or 0)


if __name__ == "__main__":
    main()
