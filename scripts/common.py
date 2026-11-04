"""Utilidades compartidas: tema, iconos, SVG y escritor draw.io. Solo librería estándar."""
import base64, json, os, pathlib, urllib.request
from xml.sax.saxutils import escape as _esc, quoteattr

DEFAULT_THEME = {
    "azul": "#1B3A5C", "azul_med": "#2C5282", "naranjo": "#E8811A",
    "gris": "#64748B", "gris_light": "#F1F5F9", "verde": "#10B981",
    "rojo": "#EF4444", "paper": "#FFFFFF", "tile_border": "#CBD5E1",
}
SANS = "Inter, Helvetica, Arial, sans-serif"
MONO = "'JetBrains Mono', Consolas, 'Courier New', monospace"


def load_theme(path=None):
    t = dict(DEFAULT_THEME)
    p = path or os.environ.get("TDOCS_THEME")
    if p and os.path.exists(p):
        t.update(json.load(open(p, encoding="utf-8")))
    return t


def esc(s):
    return _esc(str(s), {'"': "&quot;"})


def wrap(text, width=18, max_lines=3):
    words, lines, cur = str(text).split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][: width - 1] + "…"
    return lines or [""]


def human(n):
    if n is None:
        return "—"
    n = float(n)
    for unit, div in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if abs(n) >= div:
            return f"{n/div:.1f}{unit}".replace(".0", "")
    return str(int(n))


def human_bytes(n):
    if n is None:
        return "—"
    n = float(n)
    for unit, div in (("TB", 1e12), ("GB", 1e9), ("MB", 1e6), ("KB", 1e3)):
        if n >= div:
            return f"{n/div:.1f} {unit}".replace(".0 ", " ")
    return f"{int(n)} B"


# ------------------------------------------------------------------ iconos
ALIASES = {
    "node": "nodejs", "node.js": "nodejs", "ts": "typescript", "js": "javascript",
    "postgres": "postgresql", "pg": "postgresql", "sqlserver": "microsoftsqlserver",
    "mssql": "microsoftsqlserver", "sql-server": "microsoftsqlserver", "mongo": "mongodb",
    "k8s": "kubernetes", "gh": "github", "gcp": "googlecloud", "py": "python",
    "dotnet": "dot-net", "csharp": "csharp", "golang": "go", "vue": "vuejs",
    "next": "nextjs", "express": "express", "mysql2": "mysql", "react": "react",
}
_G = {
    "database": '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
    "server": '<rect x="3" y="3" width="18" height="7" rx="1.5"/><rect x="3" y="14" width="18" height="7" rx="1.5"/><path d="M7 6.5h.01M7 17.5h.01"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7"/>',
    "users": '<circle cx="9" cy="8" r="3.5"/><path d="M2 20c0-3.8 3-6 7-6s7 2.2 7 6"/><path d="M16 4.6a3.5 3.5 0 0 1 0 6.8M18 14c2.4.6 4 2.4 4 5"/>',
    "queue": '<rect x="3" y="4" width="18" height="4" rx="1"/><rect x="3" y="10" width="18" height="4" rx="1"/><rect x="3" y="16" width="18" height="4" rx="1"/>',
    "cache": '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>',
    "cloud": '<path d="M7 18a5 5 0 1 1 1-9.9A6 6 0 0 1 19.5 11 3.5 3.5 0 0 1 18 18z"/>',
    "api": '<path d="M8 4c-2 0-3 1-3 3v3c0 1.2-.8 2-2 2 1.2 0 2 .8 2 2v3c0 2 1 3 3 3M16 4c2 0 3 1 3 3v3c0 1.2.8 2 2 2-1.2 0-2 .8-2 2v3c0 2-1 3-3 3"/>',
    "file": '<path d="M6 2h8l5 5v15H6z"/><path d="M14 2v5h5M9 13h7M9 17h7"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "browser": '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="M2 9h20M6 6.5h.01M9 6.5h.01"/>',
    "gear": '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9 7 7M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1"/>',
    "box": '<path d="M12 2 21 7v10l-9 5-9-5V7z"/><path d="M3 7l9 5 9-5M12 12v10"/>',
    "lock": '<rect x="4" y="10" width="16" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>',
    "mail": '<rect x="2" y="5" width="20" height="14" rx="2"/><path d="m2 7 10 7 10-7"/>',
    "plug": '<path d="M9 2v6M15 2v6M6 8h12v4a6 6 0 0 1-12 0zM12 18v4"/>',
    "refresh": '<path d="M20 11a8 8 0 0 0-14-4L4 9M4 4v5h5M4 13a8 8 0 0 0 14 4l2-2M20 20v-5h-5"/>',
    "chart": '<path d="M4 20V10M10 20V4M16 20v-8M22 20H2"/>',
}


def generic_svg(name, theme):
    body = _G.get(name, _G["box"])
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{theme["azul"]}" '
            f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{body}</svg>')


ICON_SOURCES = {}  # nombre -> origen (para créditos)


def _cache_dir():
    d = pathlib.Path(os.environ.get("TDOCS_CACHE", pathlib.Path.home() / ".cache" / "tech-project-docs")) / "icons"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "tech-project-docs"})
    with urllib.request.urlopen(req, timeout=8) as r:
        return r.read()


def icon_svg_bytes(name, theme, icons_dir=None):
    """Devuelve (bytes, mime). Orden: icons_dir → caché → red (devicon/svgl) → pictograma genérico."""
    key = ALIASES.get(name.lower(), name.lower())
    if icons_dir:
        for ext, mime in (("svg", "image/svg+xml"), ("png", "image/png"), ("webp", "image/webp")):
            for n in (name, key):
                p = pathlib.Path(icons_dir) / f"{n}.{ext}"
                if p.exists():
                    ICON_SOURCES[name] = "local"
                    return p.read_bytes(), mime
    if key in _G:
        ICON_SOURCES[name] = "generic"
        return generic_svg(key, theme).encode(), "image/svg+xml"
    cached = _cache_dir() / f"{key}.svg"
    if cached.exists():
        ICON_SOURCES[name] = "cache"
        return cached.read_bytes(), "image/svg+xml"
    if not os.environ.get("TDOCS_OFFLINE"):
        urls = [
            ("devicon", f"https://raw.githubusercontent.com/devicons/devicon/master/icons/{key}/{key}-original.svg"),
            ("devicon", f"https://raw.githubusercontent.com/devicons/devicon/master/icons/{key}/{key}-plain.svg"),
            ("svgl", f"https://svgl.app/library/{key}.svg"),
        ]
        for src, url in urls:
            try:
                data = _fetch(url)
                if b"<svg" in data[:2000].lower() or b"<svg" in data.lower():
                    cached.write_bytes(data)
                    ICON_SOURCES[name] = src
                    return data, "image/svg+xml"
            except Exception:
                continue
    ICON_SOURCES[name] = "generic"
    return generic_svg("box", theme).encode(), "image/svg+xml"


def icon_uri(name, theme, icons_dir=None):
    data, mime = icon_svg_bytes(name or "box", theme, icons_dir)
    return f"data:{mime};base64," + base64.b64encode(data).decode()


# ------------------------------------------------------------------ SVG
def svg_open(w, h, theme):
    t = theme
    marks = ""
    for cid, col in (("a", t["naranjo"]), ("b", t["azul_med"]), ("c", t["rojo"]), ("d", t["gris"])):
        marks += (f'<marker id="ar-{cid}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" '
                  f'orient="auto"><path d="M0 0L10 5L0 10z" fill="{col}"/></marker>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}" font-family="{SANS}"><defs>{marks}'
            f'<pattern id="grid" width="24" height="24" patternUnits="userSpaceOnUse">'
            f'<path d="M24 0H0V24" fill="none" stroke="{t["gris_light"]}" stroke-width="1"/></pattern></defs>'
            f'<rect width="{w}" height="{h}" fill="{t["paper"]}"/><rect width="{w}" height="{h}" fill="url(#grid)"/>')


def svg_text(x, y, s, size=12, weight=400, fill="#000", anchor="middle", mono=False, italic=False, halo=None):
    fam = f' font-family="{MONO}"' if mono else ""
    it = ' font-style="italic"' if italic else ""
    h = f' stroke="{halo}" stroke-width="4" paint-order="stroke" stroke-linejoin="round"' if halo else ""
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-weight="{weight}" fill="{fill}" '
            f'text-anchor="{anchor}"{fam}{it}{h}>{esc(s)}</text>')


def svg_title(title, subtitle, theme, w):
    out = svg_text(24, 34, title, 20, 700, theme["azul"], "start")
    if subtitle:
        out += svg_text(24, 54, subtitle, 11, 400, theme["gris"], "start")
    return out


def edge_style(kind, theme):
    """kind: primary | internal | dashed | risk -> (color, dash, marker)"""
    return {
        "primary": (theme["naranjo"], "", "ar-a"),
        "internal": (theme["azul_med"], "", "ar-b"),
        "dashed": (theme["azul_med"], "5 5", "ar-b"),
        "risk": (theme["rojo"], "5 5", "ar-c"),
    }.get(kind, (theme["azul_med"], "", "ar-b"))


def polyline(points, color, dash="", marker=None, width=1.6):
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    d = f' stroke-dasharray="{dash}"' if dash else ""
    m = f' marker-end="url(#{marker})"' if marker else ""
    return f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="{width}"{d}{m} stroke-linejoin="round"/>'


# ------------------------------------------------------------------ draw.io
class Drawio:
    def __init__(self):
        self.cells, self._n = [], 1

    def _id(self, p):
        self._n += 1
        return f"{p}{self._n}"

    def vertex(self, value, style, x, y, w, h, parent="1"):
        cid = self._id("v")
        self.cells.append(
            f'<mxCell id="{cid}" value={quoteattr(value)} style={quoteattr(style)} vertex="1" parent="{parent}">'
            f'<mxGeometry x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}" as="geometry"/></mxCell>')
        return cid

    def edge(self, src, tgt, style, value=""):
        cid = self._id("e")
        self.cells.append(
            f'<mxCell id="{cid}" value={quoteattr(value)} style={quoteattr(style)} edge="1" parent="1" '
            f'source="{src}" target="{tgt}"><mxGeometry relative="1" as="geometry"/></mxCell>')
        return cid

    def line(self, x1, y1, x2, y2, style):
        cid = self._id("l")
        self.cells.append(
            f'<mxCell id="{cid}" value="" style={quoteattr(style)} edge="1" parent="1"><mxGeometry relative="1" as="geometry">'
            f'<mxPoint x="{x1:.0f}" y="{y1:.0f}" as="sourcePoint"/><mxPoint x="{x2:.0f}" y="{y2:.0f}" as="targetPoint"/>'
            f'</mxGeometry></mxCell>')

    def save(self, path, name, w, h):
        xml = (f'<mxfile host="app.diagrams.net"><diagram id="{esc(name)}" name={quoteattr(name)}>'
               f'<mxGraphModel dx="1100" dy="700" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" '
               f'fold="1" page="1" pageScale="1" pageWidth="{int(w)}" pageHeight="{int(h)}" math="0" shadow="0">'
               f'<root><mxCell id="0"/><mxCell id="1" parent="0"/>' + "".join(self.cells) +
               '</root></mxGraphModel></diagram></mxfile>')
        import xml.dom.minidom as m
        m.parseString(xml)  # valida que el XML sea correcto
        pathlib.Path(path).write_text(xml, encoding="utf-8")


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write(path, text):
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p
