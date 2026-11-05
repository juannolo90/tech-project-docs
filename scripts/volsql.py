"""Paso 4b · Volumetría asistida.

  tdocs.py volsql   [erd.json] --dialect mssql|postgres|mysql|oracle|hana [--days 7]   -> consultas-volumen.sql (SOLO LECTURA)
  tdocs.py volapply resultados.csv [erd.json]                                           -> rellena volume.* en erd.json

Idea: una muestra de N días (por defecto 7) sobre la columna de fecha de cada tabla alcanza para extrapolar la tasa mensual
(filas/día × 30). Sin columna de fecha o sin acceso a la BD, el agente pregunta tasas de negocio («¿cuántos proyectos al día?»)
y las registra como `rows_per_day` con source "supuesto". Nada se inventa.
"""
import csv, json, pathlib, re
from common import read_json, write

DATE_NAME = re.compile(r"(creat|fecha|date|_at$|_dt$|timestamp|insert|registr|ingres|alta)", re.I)
DATE_TYPE = re.compile(r"(date|time)", re.I)
IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")  # evita inyectar SQL desde nombres del spec
NOW = {"mssql": "DATEADD(day,-{d},GETDATE())", "postgres": "now() - interval '{d} days'", "mysql": "NOW() - INTERVAL {d} DAY",
       "oracle": "SYSDATE - {d}", "hana": "ADD_DAYS(CURRENT_TIMESTAMP,-{d})"}


def date_column(entity):
    cols = entity.get("columns", [])
    pref = [c for c in cols if DATE_TYPE.search(c.get("type", "")) and DATE_NAME.search(c["name"])]
    anyd = [c for c in cols if DATE_TYPE.search(c.get("type", ""))]
    byname = [c for c in cols if DATE_NAME.search(c["name"]) and not c.get("fk") and not c.get("pk")]
    for grp in (pref, anyd, byname):
        for c in grp:
            if IDENT.match(c["name"]):
                return c["name"]
    return None


def build_sql(spec, dialect, days):
    if dialect not in NOW:
        raise SystemExit(f"dialecto no soportado: {dialect} (usa {', '.join(NOW)})")
    out = [f"-- tech-project-docs · volumetría ({dialect}) · SOLO LECTURA: únicamente SELECT/COUNT.",
           f"-- Ejecútalo con un usuario de solo lectura (idealmente en una réplica o fuera de horario) y pega el resultado.",
           f"-- Columnas: tabla, filas_total, filas_{days}d, desde, hasta, columna_fecha\n"]
    parts, skipped = [], []
    since = NOW[dialect].format(d=days)
    for e in spec.get("entities", []):
        t = e["name"]
        if not IDENT.match(t):
            skipped.append(t)
            continue
        dc = date_column(e)
        if dc:
            parts.append(f"SELECT '{t}' AS tabla, COUNT(*) AS filas_total, SUM(CASE WHEN {dc} >= {since} THEN 1 ELSE 0 END) AS filas_{days}d, "
                         f"MIN({dc}) AS desde, MAX({dc}) AS hasta, '{dc}' AS columna_fecha FROM {t}")
        else:
            parts.append(f"SELECT '{t}' AS tabla, COUNT(*) AS filas_total, NULL AS filas_{days}d, NULL AS desde, NULL AS hasta, NULL AS columna_fecha FROM {t}")
    out.append("\nUNION ALL\n".join(parts) + ";")
    if skipped:
        out.append("\n-- Omitidas por nombre no estándar (revisar a mano): " + ", ".join(skipped))
    out.append("\n-- Tamaño por tabla (opcional): ver references/volumenes.md")
    return "\n".join(out) + "\n", [e["name"] for e in spec.get("entities", []) if not date_column(e)]


def main_sql(args):
    import argparse
    ap = argparse.ArgumentParser(prog="tdocs volsql")
    ap.add_argument("spec", nargs="?", default="docs/spec/erd.json")
    ap.add_argument("-o", "--out", default="docs")
    ap.add_argument("--dialect", required=True, choices=sorted(NOW))
    ap.add_argument("--days", type=int, default=7)
    a = ap.parse_args(args)
    spec = read_json(a.spec)
    sql, nodate = build_sql(spec, a.dialect, a.days)
    p = pathlib.Path(a.out) / "03-modelo-datos" / "consultas-volumen.sql"
    write(p, sql)
    print(f"OK consultas de volumetría ({a.dialect}, muestra {a.days} d) → {p}")
    if nodate:
        print("Sin columna de fecha (pregunta al usuario su tasa de negocio, ej. «¿cuántos al día?»):", ", ".join(nodate))


def _num(x):
    try:
        return float(str(x).replace(",", "").strip())
    except Exception:
        return None


def main_apply(args):
    import argparse
    ap = argparse.ArgumentParser(prog="tdocs volapply")
    ap.add_argument("csv")
    ap.add_argument("spec", nargs="?", default="docs/spec/erd.json")
    ap.add_argument("--days", type=int, default=7)
    a = ap.parse_args(args)
    spec = read_json(a.spec)
    txt = pathlib.Path(a.csv).read_text(encoding="utf-8-sig")
    try:
        dia = csv.Sniffer().sniff(txt.splitlines()[0], delimiters=",;\t|")
    except Exception:
        dia = csv.excel
    rows = list(csv.DictReader(txt.splitlines(), dialect=dia))
    by = {e["name"].lower(): e for e in spec["entities"]}
    n = 0
    for r in rows:
        r = {k.strip().lower(): v for k, v in r.items() if k}
        e = by.get((r.get("tabla") or "").strip().lower())
        tot = _num(r.get("filas_total") or r.get("filas"))
        if not e or tot is None:
            continue
        v = e.setdefault("volume", {})
        v["rows"] = int(tot)
        samp = next((_num(val) for k, val in r.items() if re.match(r"filas_\d+d$", k)), None)
        if samp is not None and r.get("columna_fecha"):
            v["sample"] = {"days": a.days, "rows": int(samp), "date_column": r["columna_fecha"].strip()}
        b = _num(r.get("bytes"))
        if b and tot:
            v["avg_row_bytes"] = round(b / tot, 1)
        v["source"] = "medido"
        n += 1
    write(a.spec, json.dumps(spec, indent=2, ensure_ascii=False))
    print(f"OK {n} entidades actualizadas con datos medidos → {a.spec}. Corre `tdocs erd` para regenerar.")
