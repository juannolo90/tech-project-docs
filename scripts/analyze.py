"""Paso 1 · Entender el proyecto: grafo de módulos, dependencias, rutas, entornos y tablas.

Genera <out>/00-grafo/graph.json y GRAPH_REPORT.md. Solo librería estándar.
SEGURIDAD: nunca lee archivos .env reales (solo .env.example/.sample/.template, y solo los NOMBRES de variables).
"""
import json, os, re, subprocess, collections, pathlib
from common import write

IGNORE_DIRS = {".git", "node_modules", "dist", "build", "out", ".next", ".nuxt", "venv", ".venv", "env", "__pycache__",
               ".idea", ".vscode", "target", "bin", "obj", "coverage", ".cache", ".turbo", "vendor", "docs", "graphify-out"}
LANG = {".ts": "TypeScript", ".tsx": "TypeScript", ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript",
        ".cjs": "JavaScript", ".py": "Python", ".java": "Java", ".go": "Go", ".cs": "C#", ".rb": "Ruby", ".php": "PHP",
        ".abap": "ABAP", ".sql": "SQL", ".kt": "Kotlin", ".rs": "Rust", ".prisma": "Prisma"}
CODE_EXT = set(LANG)
MAX_BYTES = 1_500_000
SAFE_ENV = (".env.example", ".env.sample", ".env.template", ".env.dist")

DEP_CATALOG = {  # dependencia -> (categoría, nombre, icono)
    "express": ("web", "Express", "express"), "fastify": ("web", "Fastify", "fastify"), "next": ("web", "Next.js", "nextjs"),
    "react": ("ui", "React", "react"), "vue": ("ui", "Vue", "vuejs"), "@angular/core": ("ui", "Angular", "angularjs"),
    "svelte": ("ui", "Svelte", "svelte"), "vite": ("build", "Vite", "vitejs"), "typescript": ("lang", "TypeScript", "typescript"),
    "mssql": ("db", "SQL Server", "microsoftsqlserver"), "pg": ("db", "PostgreSQL", "postgresql"),
    "mysql": ("db", "MySQL", "mysql"), "mysql2": ("db", "MySQL", "mysql"), "mongodb": ("db", "MongoDB", "mongodb"),
    "mongoose": ("db", "MongoDB", "mongodb"), "redis": ("cache", "Redis", "redis"), "ioredis": ("cache", "Redis", "redis"),
    "sqlite3": ("db", "SQLite", "sqlite"), "better-sqlite3": ("db", "SQLite", "sqlite"), "oracledb": ("db", "Oracle DB", "oracle"),
    "@sap/hana-client": ("db", "SAP HANA", "database"), "prisma": ("orm", "Prisma", "prisma"), "typeorm": ("orm", "TypeORM", "typeorm"),
    "sequelize": ("orm", "Sequelize", "sequelize"), "kafkajs": ("queue", "Kafka", "apachekafka"),
    "amqplib": ("queue", "RabbitMQ", "rabbitmq"), "bullmq": ("queue", "BullMQ", "queue"),
    "@modelcontextprotocol/sdk": ("protocol", "MCP SDK", "plug"), "@anthropic-ai/sdk": ("ai", "Anthropic API", "cloud"),
    "openai": ("ai", "OpenAI API", "cloud"), "axios": ("http", "Axios (HTTP)", "api"), "node-fetch": ("http", "HTTP", "api"),
    "aws-sdk": ("cloud", "AWS", "amazonwebservices"), "googleapis": ("cloud", "Google APIs", "google"),
    "stripe": ("saas", "Stripe", "stripe"), "docker": ("infra", "Docker", "docker"), "zod": ("lib", "Zod", "box"),
    "dotenv": ("config", "dotenv", "file"), "jsonwebtoken": ("auth", "JWT", "lock"), "passport": ("auth", "Passport", "lock"),
    "flask": ("web", "Flask", "flask"), "fastapi": ("web", "FastAPI", "fastapi"), "django": ("web", "Django", "django"),
    "sqlalchemy": ("orm", "SQLAlchemy", "sqlalchemy"), "psycopg2": ("db", "PostgreSQL", "postgresql"),
    "pandas": ("data", "pandas", "pandas"), "celery": ("queue", "Celery", "celery"), "boto3": ("cloud", "AWS", "amazonwebservices"),
}
SQL_KW = {"select", "set", "values", "where", "the", "a", "an", "table", "dual", "null", "case", "when", "then", "end", "as",
          "on", "and", "or", "not", "by", "order", "group", "top", "distinct", "all", "inner", "outer", "left", "right", "sql",
          "this", "that", "each", "any", "if", "exists", "with", "into", "from", "join", "update", "delete", "insert"}


def walk(root):
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in IGNORE_DIRS and not d.startswith(".git")]
        for fn in fns:
            if fn.startswith(".env") and fn not in SAFE_ENV:
                continue  # nunca leer secretos
            p = pathlib.Path(dp) / fn
            try:
                if p.stat().st_size > MAX_BYTES:
                    continue
            except OSError:
                continue
            yield p


def read(p):
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


JS_IMP = [re.compile(r"""(?:import|export)\s+(?:[^'"]*?\s+from\s+)?['"]([^'"]+)['"]"""),
          re.compile(r"""require\(\s*['"]([^'"]+)['"]\s*\)"""), re.compile(r"""import\(\s*['"]([^'"]+)['"]\s*\)""")]
PY_IMP = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", re.M)
JAVA_IMP = re.compile(r"^\s*import\s+(?:static\s+)?([\w.]+);", re.M)
GO_IMP = re.compile(r'^\s*(?:import\s+)?(?:\w+\s+)?"([\w./\-]+)"\s*$', re.M)
CS_IMP = re.compile(r"^\s*using\s+([\w.]+);", re.M)

ROUTES = [
    (re.compile(r"""\b(?:app|router|server)\.(get|post|put|delete|patch)\(\s*['"`]([^'"`]+)['"`]"""), "http"),
    (re.compile(r"""@\w+\.(route|get|post|put|delete|patch)\(\s*['"]([^'"]+)['"]"""), "http"),
    (re.compile(r"""@(Get|Post|Put|Delete|Patch|Request)Mapping\(\s*(?:value\s*=\s*)?["']([^"']+)["']"""), "http"),
    (re.compile(r"""(registerTool|\.tool)\(\s*['"]([\w\-.]+)['"]"""), "mcp-tool"),
]
ENV_PAT = [re.compile(r"process\.env\.([A-Z][A-Z0-9_]+)"), re.compile(r"process\.env\[\s*['\"]([A-Z][A-Z0-9_]+)['\"]"),
           re.compile(r"os\.environ(?:\.get)?[\[(]\s*['\"]([A-Z][A-Z0-9_]+)['\"]"), re.compile(r"getenv\(\s*['\"]([A-Z][A-Z0-9_]+)['\"]"),
           re.compile(r"System\.getenv\(\s*\"([A-Z][A-Z0-9_]+)\"")]
ENV_DESTRUCT = re.compile(r"\{([^}]+)\}\s*=\s*process\.env")
SQL_TBL = re.compile(r"\b(FROM|JOIN|INTO|UPDATE)\s+(?:\[?(\w+)\]?\.)?\[?([A-Za-z_]\w*)\]?", re.I)
DDL = re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\[\"`]?(?:\w+[\]\"`]?\.[\[\"`]?)?(\w+)[\]\"`]?\s*\((.*?)\)\s*;", re.I | re.S)
PRISMA_MODEL = re.compile(r"^model\s+(\w+)\s*\{(.*?)^\}", re.M | re.S)
IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

# ---- red: IPs, CIDR, hosts, puertos (solo de archivos de código/config; nunca .env reales) ----
CONF_EXT = {".yml", ".yaml", ".tf", ".tfvars", ".conf", ".ini", ".properties", ".toml", ".cfg", ".config", ".sh", ".ps1", ".bicep"}
CONF_NAMES = ("dockerfile", "appsettings", "local.settings", "ecosystem.config", "nginx", "haproxy", "web.config")
NET_SKIP = {"package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "composer.lock", "tsconfig.json"}
IP4 = re.compile(r"(?<![\w.^~=<>])(\d{1,3}(?:\.\d{1,3}){3})(?:/(\d{1,2}))?(?!\d|\.\d)")
HOST_URL = re.compile(r"\b((?:jdbc:)?[a-z][a-z0-9+\-]*)://(?:[^/\s:@'\"`]+(?::[^@\s'\"`]*)?@)?((?:[A-Za-z0-9\-]+\.)*[A-Za-z0-9\-]+)(?::(\d{2,5}))?")
LISTEN = [re.compile(r"\.listen\(\s*(?:process\.env\.\w+\s*(?:\|\||\?\?)\s*)?(\d{2,5})"), re.compile(r"\bPORT\b\s*(?:\|\||\?\?|=|:)\s*['\"]?(\d{2,5})"),
          re.compile(r"^\s*EXPOSE\s+(\d{2,5})", re.M), re.compile(r"^\s*-\s*['\"]?(\d{2,5}):(\d{2,5})['\"]?\s*$", re.M)]
NOISE_HOSTS = ("w3.org", "schemas.", "github.com", "githubusercontent.com", "npmjs.", "yarnpkg.com", "example.", "json-schema.org",
               "nodejs.org", "python.org", "mozilla.org", "apache.org", "opensource.org", "creativecommons.org", "xmlsoap.org",
               "openxmlformats.org", "docs.", "shields.io", "unpkg.com", "jsdelivr.net", "cloudflare.com")
SITE_SUFFIX = [(".database.windows.net", "azure", "Azure SQL"), (".blob.core.windows.net", "azure", "Azure Storage"),
               (".azurewebsites.net", "azure", "Azure App Service"), (".cloudapp.azure.com", "azure", "Azure VM"),
               (".windows.net", "azure", ""), (".azure.com", "azure", ""), ("graph.microsoft.com", "azure", "Microsoft Graph"),
               ("login.microsoftonline.com", "azure", "Entra ID"), (".rds.amazonaws.com", "aws", "AWS RDS"),
               (".cache.amazonaws.com", "aws", "ElastiCache"), (".amazonaws.com", "aws", ""), (".cloudfront.net", "aws", "CloudFront"),
               (".hana.ondemand.com", "sap", "SAP BTP"), (".s4hana.cloud.sap", "sap", "SAP S/4HANA Cloud"), (".cloud.sap", "sap", "SAP Cloud"),
               (".googleapis.com", "gcp", ""), (".run.app", "gcp", "Cloud Run"), (".signavio.com", "saas", "SAP Signavio")]
PORT_SERVICE = {1433: "SQL Server", 5432: "PostgreSQL", 3306: "MySQL", 27017: "MongoDB", 6379: "Redis", 5672: "RabbitMQ",
                9092: "Kafka", 389: "LDAP", 636: "LDAPS", 25: "SMTP", 465: "SMTP", 587: "SMTP", 22: "SSH/SFTP", 30015: "SAP HANA",
                443: "HTTPS", 80: "HTTP", 1521: "Oracle", 9200: "Elasticsearch"}


BARE_CLOUD = re.compile(r"(?<![\w.-])((?:[a-z0-9-]+\.)+(?:database\.windows\.net|rds\.amazonaws\.com|hana\.ondemand\.com|azurewebsites\.net|cache\.amazonaws\.com|s4hana\.cloud\.sap))(?![\w-])", re.I)


def ip_kind(ip):
    a, b = int(ip.split(".")[0]), int(ip.split(".")[1])
    if a == 127:
        return "loopback"
    if a == 10 or (a == 172 and 16 <= b <= 31) or (a == 192 and b == 168) or (a == 100 and 64 <= b <= 127):
        return "private"
    if a == 169 and b == 254:
        return "link-local"
    return "public"


def mask_ip(ip):
    p = ip.split(".")
    return f"{p[0]}.{p[1]}.x.x"


def scan_net(rel, txt, hints):
    for m in IP4.finditer(txt):
        ip, mask = m.group(1), m.group(2)
        o = [int(x) for x in ip.split(".")]
        if any(x > 255 for x in o) or ip in ("0.0.0.0", "255.255.255.255") or o[0] == 0:
            continue
        if mask is not None and int(mask) > 32:
            continue
        d = hints["ips"].setdefault(ip, {"ip": ip, "kind": ip_kind(ip), "files": set()})
        d["files"].add(rel)
        if mask is not None:
            hints["cidrs"].setdefault(f"{ip}/{mask}", set()).add(rel)
    for m in HOST_URL.finditer(txt):
        scheme, host, port = m.group(1).lower(), m.group(2).lower(), m.group(3)
        if scheme in ("file", "data", "chrome", "vscode") or IP4.fullmatch(host):
            continue
        if any(n in host for n in NOISE_HOSTS) or (scheme in ("http", "https") and "." not in host and host != "localhost"):
            continue
        d = hints["hosts"].setdefault((host, port or ""), {"host": host, "port": int(port) if port else None, "schemes": set(), "files": set()})
        d["schemes"].add(scheme.replace("jdbc:", ""))
        d["files"].add(rel)
    for m in BARE_CLOUD.finditer(txt):  # hosts cloud sin esquema (p. ej. server=foo.database.windows.net)
        host = m.group(1).lower()
        hints["hosts"].setdefault((host, ""), {"host": host, "port": None, "schemes": set(), "files": set()})["files"].add(rel)
    for rx in LISTEN:
        for m in rx.finditer(txt):
            hints["ports"].setdefault(int(m.group(m.lastindex)), set()).add(rel)


def finish_net(hints, mask):
    mk = mask_ip if mask else (lambda x: x)
    mkc = (lambda c: mask_ip(c.split("/")[0]) + "/" + c.split("/")[1]) if mask else (lambda c: c)
    ips = [{"ip": mk(v["ip"]), "kind": v["kind"], "files": sorted(v["files"])[:5]}
           for v in sorted(hints["ips"].values(), key=lambda x: [int(o) for o in x["ip"].split(".")])]
    seg = collections.defaultdict(list)
    for v in hints["ips"].values():
        if v["kind"] == "private":
            seg[".".join(v["ip"].split(".")[:3]) + ".0/24"].append(mk(v["ip"]))
    hosts = []
    for v in sorted(hints["hosts"].values(), key=lambda x: x["host"]):
        site, svc = None, None
        for suf, st, sv in SITE_SUFFIX:
            if v["host"].endswith(suf) or v["host"] == suf.lstrip("."):
                site, svc = st, sv or None
                break
        if not svc and v["port"] in PORT_SERVICE:
            svc = PORT_SERVICE[v["port"]]
        hosts.append({"host": v["host"], "port": v["port"], "schemes": sorted(v["schemes"]), "site_hint": site,
                      "service_hint": svc, "files": sorted(v["files"])[:5]})
    withport = {h["host"] for h in hosts if h["port"]}
    hosts = [h for h in hosts if h["port"] or h["host"] not in withport]
    return {"ips": ips, "cidrs": [{"cidr": mkc(c), "files": sorted(f)[:3]} for c, f in sorted(hints["cidrs"].items())],
            "segments_detected": [{"cidr": mkc(c), "ips": sorted(i)} for c, i in sorted(seg.items())],
            "hosts": hosts, "listen_ports": [{"port": p, "files": sorted(f)[:3]} for p, f in sorted(hints["ports"].items())],
            "masked": mask,
            "note": "Una IP privada NO dice en qué sitio está (on-prem, AWS, Azure…): confirmar con el usuario."}


def resolve_js(src_rel, spec, files):
    if not spec.startswith("."):
        return None
    base = pathlib.PurePosixPath(src_rel).parent
    t = (base / spec)
    parts = []
    for part in t.parts:
        if part == "..":
            if parts:
                parts.pop()
        elif part != ".":
            parts.append(part)
    cand = "/".join(parts)
    stem = re.sub(r"\.(m|c)?jsx?$", "", cand)
    for c in [cand, stem + ".ts", stem + ".tsx", stem + ".js", stem + ".jsx", stem + ".mjs", stem + "/index.ts", stem + "/index.js", cand + ".ts", cand + ".js"]:
        if c in files:
            return c
    return None


def resolve_py(src_rel, mod, files):
    cands = [mod.replace(".", "/") + ".py", mod.replace(".", "/") + "/__init__.py"]
    if mod.startswith("."):
        base = pathlib.PurePosixPath(src_rel).parent
        cands = [str(base / (mod.lstrip(".").replace(".", "/") or "__init__")) + ".py"]
    for c in cands:
        if c in files:
            return c
    return None


def git_info(root):
    try:
        h = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5)
        return h.stdout.strip() or None
    except Exception:
        return None


def parse_ddl(text):
    tables = []
    for m in DDL.finditer(text):
        name, body = m.group(1), m.group(2)
        cols = []
        for line in re.split(r",\s*\n|,(?![^()]*\))", body):
            line = line.strip()
            if not line or re.match(r"(PRIMARY|FOREIGN|CONSTRAINT|UNIQUE|KEY|INDEX|CHECK)\b", line, re.I):
                fk = re.search(r"FOREIGN\s+KEY\s*\(\s*[\"`\[]?(\w+)[\"`\]]?\s*\)\s*REFERENCES\s+[\"`\[]?(\w+)[\"`\]]?\s*\(\s*[\"`\[]?(\w+)", line, re.I)
                if fk:
                    for c in cols:
                        if c["name"] == fk.group(1):
                            c["fk"] = f"{fk.group(2)}.{fk.group(3)}"
                continue
            mm = re.match(r"[\"`\[]?(\w+)[\"`\]]?\s+([\w]+(?:\([\d, ]+\))?)(.*)", line, re.S)
            if mm:
                rest = mm.group(3)
                col = {"name": mm.group(1), "type": mm.group(2), "pk": bool(re.search(r"PRIMARY\s+KEY", rest, re.I)),
                       "nullable": not re.search(r"NOT\s+NULL", rest, re.I)}
                ref = re.search(r"REFERENCES\s+[\"`\[]?(\w+)[\"`\]]?\s*\(\s*[\"`\[]?(\w+)", rest, re.I)
                if ref:
                    col["fk"] = f"{ref.group(1)}.{ref.group(2)}"
                cols.append(col)
        tables.append({"name": name, "columns": cols, "source": "ddl"})
    return tables


def parse_prisma(text):
    out = []
    for m in PRISMA_MODEL.finditer(text):
        cols = []
        for line in m.group(2).splitlines():
            mm = re.match(r"\s*(\w+)\s+(\w+)(\??)(\[\])?\s*(.*)", line)
            scalar = ("String", "Int", "BigInt", "Float", "Decimal", "Boolean", "DateTime", "Json", "Bytes")
            if mm and not line.strip().startswith("@@") and mm.group(2) in scalar:
                cols.append({"name": mm.group(1), "type": mm.group(2), "pk": "@id" in mm.group(5), "nullable": bool(mm.group(3))})
        out.append({"name": m.group(1), "columns": cols, "source": "prisma"})
    return out


def analyze(root, out_dir, mask_ips=False):
    root = pathlib.Path(root).resolve()
    files = {}
    for p in walk(root):
        files[p.relative_to(root).as_posix()] = p
    nodes, edges = {}, []
    langs, ext_deps = collections.Counter(), collections.defaultdict(set)
    routes, envs, tables, ddl_tables, comps = [], {}, collections.defaultdict(set), [], {}
    entry = set()
    manifests = {}
    hints = {"ips": {}, "cidrs": {}, "hosts": {}, "ports": {}}

    for rel, p in files.items():
        ext = p.suffix.lower()
        name = p.name
        is_conf = ext in CONF_EXT or name.lower().startswith(CONF_NAMES) or (ext == ".json" and name.lower().startswith(("appsettings", "config", "settings", "local.settings")))
        txt = read(p) if (ext in CODE_EXT or is_conf or name in SAFE_ENV or name in ("package.json", "requirements.txt", "pyproject.toml", "go.mod", "pom.xml", "docker-compose.yml", "docker-compose.yaml", "Dockerfile")) else ""
        if txt and name not in NET_SKIP:
            scan_net(rel, txt, hints)
        if name in SAFE_ENV:
            for line in txt.splitlines():
                m = re.match(r"\s*([A-Z][A-Z0-9_]+)\s*=", line)
                if m:
                    envs.setdefault(m.group(1), set()).add(rel)
            continue
        if name == "package.json":
            try:
                j = json.loads(txt)
                manifests[rel] = j
                for k in ("dependencies", "devDependencies", "peerDependencies"):
                    for d in (j.get(k) or {}):
                        ext_deps[d].add(rel)
                if j.get("main"):
                    entry.add((pathlib.PurePosixPath(rel).parent / j["main"]).as_posix().lstrip("./"))
                for v in (j.get("scripts") or {}).values():
                    for m in re.finditer(r"(?:node|tsx|ts-node)\s+([\w./\-]+)", v):
                        entry.add((pathlib.PurePosixPath(rel).parent / m.group(1)).as_posix().lstrip("./"))
            except Exception:
                pass
            continue
        if name == "requirements.txt":
            for line in txt.splitlines():
                m = re.match(r"\s*([A-Za-z0-9_.\-]+)", line)
                if m and not line.strip().startswith("#"):
                    ext_deps[m.group(1).lower()].add(rel)
            continue
        if name in ("docker-compose.yml", "docker-compose.yaml"):
            for m in re.finditer(r"image:\s*['\"]?([\w./\-:]+)", txt):
                comps["docker:" + m.group(1)] = ("infra", m.group(1).split("/")[-1].split(":")[0], m.group(1).split("/")[-1].split(":")[0])
            continue
        if ext not in CODE_EXT:
            continue
        lang = LANG[ext]
        langs[lang] += txt.count("\n") + 1
        nodes[rel] = {"id": rel, "lang": lang, "loc": txt.count("\n") + 1}
        specs = []
        if lang in ("TypeScript", "JavaScript"):
            for rx in JS_IMP:
                specs += rx.findall(txt)
            for s in specs:
                tgt = resolve_js(rel, s, files)
                if tgt:
                    edges.append((rel, tgt))
                else:
                    pkg = s if not s.startswith("@") else "/".join(s.split("/")[:2])
                    pkg = pkg.split("/")[0] if not s.startswith("@") else pkg
                    if not s.startswith(".") and not s.startswith("node:"):
                        ext_deps[pkg].add(rel)
        elif lang == "Python":
            for a, b in PY_IMP.findall(txt):
                mod = a or b
                tgt = resolve_py(rel, mod, files)
                if tgt:
                    edges.append((rel, tgt))
                else:
                    ext_deps[mod.split(".")[0].lower()].add(rel)
        elif lang == "Java":
            for s in JAVA_IMP.findall(txt):
                ext_deps[".".join(s.split(".")[:2])].add(rel)
        elif lang == "Go":
            for s in GO_IMP.findall(txt):
                if "." in s.split("/")[0]:
                    ext_deps[s].add(rel)
        elif lang == "C#":
            for s in CS_IMP.findall(txt):
                ext_deps[s.split(".")[0]].add(rel)
        for rx, kind in ROUTES:
            for m in rx.finditer(txt):
                routes.append({"kind": kind, "method": m.group(1).upper() if kind == "http" else "TOOL", "path": m.group(2), "file": rel})
        for rx in ENV_PAT:
            for m in rx.finditer(txt):
                envs.setdefault(m.group(1), set()).add(rel)
        for m in ENV_DESTRUCT.finditer(txt):
            for v in m.group(1).split(","):
                v = v.split(":")[0].strip()
                if re.fullmatch(r"[A-Z][A-Z0-9_]+", v):
                    envs.setdefault(v, set()).add(rel)
        if lang == "SQL":
            ddl_tables += parse_ddl(txt)
        if lang == "Prisma":
            ddl_tables += parse_prisma(txt)
        elif re.search(r"\b(SELECT|INSERT|UPDATE|DELETE)\b", txt):
            for kw, sch, tb in SQL_TBL.findall(txt):
                if kw.isupper() or re.search(r"select", txt, re.I):
                    if tb.lower() not in SQL_KW and len(tb) > 2 and (kw.isupper()):
                        tables[tb].add(rel)
            ddl_tables += [t for t in parse_ddl(txt)]
        base = name.rsplit(".", 1)[0].lower()
        if base in ("main", "index", "app", "server", "cli", "__main__", "program", "manage") and "/" not in rel.replace("src/", "", 1):
            entry.add(rel)
        if re.search(r"if\s+__name__\s*==\s*['\"]__main__['\"]|\.listen\(|createServer\(|StdioServerTransport|app\.run\(|public static void main", txt):
            entry.add(rel)

    ids = set(nodes)
    edges = sorted({(a, b) for a, b in edges if a in ids and b in ids and a != b})
    deg = collections.Counter()
    for a, b in edges:
        deg[a] += 1
        deg[b] += 1
    for n in nodes.values():
        n["degree"] = deg[n["id"]]
        top = n["id"].split("/")
        n["community"] = top[1] if len(top) > 2 and top[0] in ("src", "app", "lib") else top[0] if len(top) > 1 else "(raíz)"

    # componentes sugeridos por dependencias
    for dep, users in ext_deps.items():
        key = dep if dep in DEP_CATALOG else dep.lower()
        if key in DEP_CATALOG:
            comps[key] = DEP_CATALOG[key]
    suggested = sorted({(c[0], c[1], c[2]) for c in comps.values()})
    all_tables = {}
    for t in ddl_tables:
        all_tables[t["name"]] = t
    inferred = [{"name": k, "files": sorted(v)} for k, v in sorted(tables.items()) if k not in all_tables]
    has_git = git_info(root)

    graph = {
        "root": root.name, "commit": has_git, "languages": dict(langs),
        "nodes": list(nodes.values()), "edges": [{"from": a, "to": b} for a, b in edges],
        "entry_points": sorted(e for e in entry if e in ids),
        "routes": sorted({(r["kind"], r["method"], r["path"], r["file"]) for r in routes}),
        "env_vars": {k: sorted(v) for k, v in sorted(envs.items())},
        "external_deps": {k: sorted(v) for k, v in sorted(ext_deps.items())},
        "suggested_components": [{"category": a, "name": b, "icon": c} for a, b, c in suggested],
        "schema_ddl": list(all_tables.values()), "tables_referenced_in_code": inferred,
        "network_hints": finish_net(hints, mask_ips),
    }
    graph["routes"] = [{"kind": k, "method": m, "path": p, "file": f} for k, m, p, f in graph["routes"]]
    out = pathlib.Path(out_dir) / "00-grafo"
    write(out / "graph.json", json.dumps(graph, indent=2, ensure_ascii=False))
    write(out / "GRAPH_REPORT.md", report(graph, manifests))
    return graph


def report(g, manifests):
    L = []
    L.append(f"# GRAPH_REPORT · {g['root']}")
    L.append(f"\n- Commit: `{g['commit'] or 'sin git'}`")
    L.append(f"- Archivos de código: {len(g['nodes'])} · Dependencias internas: {len(g['edges'])}")
    L.append("- Lenguajes (líneas): " + ", ".join(f"{k} {v}" for k, v in sorted(g["languages"].items(), key=lambda x: -x[1])))
    gods = sorted(g["nodes"], key=lambda n: -n["degree"])[:8]
    L.append("\n## Nodos centrales (mayor grado)\n")
    L += [f"- `{n['id']}` · grado {n['degree']} · {n['loc']} líneas" for n in gods if n["degree"] > 0] or ["- (sin dependencias internas)"]
    comm = collections.defaultdict(list)
    for n in g["nodes"]:
        comm[n["community"]].append(n["id"])
    L.append("\n## Comunidades (por carpeta)\n")
    L += [f"- **{k}** ({len(v)}): " + ", ".join(f"`{x}`" for x in v[:6]) + ("…" if len(v) > 6 else "") for k, v in sorted(comm.items())]
    L.append("\n## Puntos de entrada\n")
    L += [f"- `{e}`" for e in g["entry_points"]] or ["- (no detectados)"]
    if g["routes"]:
        L.append("\n## Rutas / tools expuestas\n")
        L += [f"- `{r['method']} {r['path']}` ({r['kind']}) → `{r['file']}`" for r in g["routes"][:60]]
    if g["env_vars"]:
        L.append("\n## Variables de entorno (solo nombres)\n")
        L += [f"- `{k}` ← {', '.join('`'+x+'`' for x in v[:3])}" for k, v in g["env_vars"].items()]
    if g["suggested_components"]:
        L.append("\n## Componentes sugeridos (por dependencias)\n")
        L += [f"- {c['name']} · {c['category']}" for c in g["suggested_components"]]
    if g["schema_ddl"]:
        L.append("\n## Esquema detectado (DDL / Prisma)\n")
        L += [f"- `{t['name']}`: {len(t['columns'])} columnas" for t in g["schema_ddl"]]
    if g["tables_referenced_in_code"]:
        L.append("\n## Tablas referenciadas en consultas (esquema NO declarado: columnas por inferir)\n")
        L += [f"- `{t['name']}` ← {', '.join('`'+x+'`' for x in t['files'][:3])}" for t in g["tables_referenced_in_code"]]
    nh = g.get("network_hints") or {}
    if nh.get("ips") or nh.get("hosts") or nh.get("listen_ports"):
        L.append("\n## Red detectada (confirmar con el usuario: sitio, segmento y elementos de red)\n")
        L += [f"- Segmento `{s['cidr']}`: " + ", ".join(f"`{i}`" for i in s["ips"][:8]) for s in nh.get("segments_detected", [])]
        L += [f"- IP pública `{i['ip']}` ← `{i['files'][0]}`" for i in nh.get("ips", []) if i["kind"] == "public"][:15]
        L += [f"- Host `{h['host']}{':' + str(h['port']) if h['port'] else ''}`" + (f" · {h['service_hint']}" if h["service_hint"] else "")
              + (f" · sitio probable: **{h['site_hint']}**" if h["site_hint"] else " · sitio: ¿?") for h in nh.get("hosts", [])[:40]]
        L += [f"- Puerto de escucha `{p['port']}` ← `{p['files'][0]}`" for p in nh.get("listen_ports", [])]
        if not nh.get("masked"):
            L.append("\n> ⚠ Este reporte puede contener IPs/hosts internos. No publiques `docs/` sin revisarlo (o regenera con `--mask-ips`).")
    L.append("\n> Generado por tech-project-docs. Los valores de `.env` reales no se leen ni se registran.")
    return "\n".join(L) + "\n"


def main(args):
    import argparse
    ap = argparse.ArgumentParser(prog="tdocs analyze")
    ap.add_argument("repo")
    ap.add_argument("-o", "--out", default="docs")
    ap.add_argument("--mask-ips", action="store_true", help="enmascara IPs (a.b.x.x) en graph.json y el reporte")
    a = ap.parse_args(args)
    g = analyze(a.repo, a.out, a.mask_ips)
    print(f"OK grafo: {len(g['nodes'])} archivos, {len(g['edges'])} aristas, {len(g['entry_points'])} entradas → {a.out}/00-grafo/")
