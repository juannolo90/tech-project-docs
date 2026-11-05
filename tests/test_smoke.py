"""Prueba de humo: ejecuta el pipeline completo con los ejemplos (sin red) y valida las salidas."""
import os, pathlib, subprocess, sys, tempfile, unittest, xml.dom.minidom, json

ROOT = pathlib.Path(__file__).resolve().parent.parent
CLI = ROOT / "scripts" / "tdocs.py"
ENV = dict(os.environ, TDOCS_OFFLINE="1", TDOCS_CACHE=tempfile.mkdtemp())


def run(*args):
    r = subprocess.run([sys.executable, "-I", str(CLI), *args], capture_output=True, text=True, env=ENV)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


class Smoke(unittest.TestCase):
    def test_pipeline(self):
        with tempfile.TemporaryDirectory() as out:
            run("flows", str(ROOT / "examples/flows.json"), "-o", out)
            run("arch", str(ROOT / "examples/architecture.json"), "-o", out)
            run("erd", str(ROOT / "examples/erd.json"), "-o", out)
            run("index", "-o", out)
            for f in ("01-flujos/flujos.html", "01-flujos/flujo-checkout.svg", "02-arquitectura/arquitectura.drawio",
                      "02-arquitectura/arquitectura.svg", "03-modelo-datos/modelo-datos.drawio", "03-modelo-datos/volumenes.md", "README.md"):
                self.assertTrue((pathlib.Path(out) / f).exists(), f)
            for f in pathlib.Path(out).rglob("*.drawio"):
                xml.dom.minidom.parse(str(f))
            for f in pathlib.Path(out).rglob("*.svg"):
                xml.dom.minidom.parse(str(f))
            self.assertIn("sin medir", (pathlib.Path(out) / "03-modelo-datos/volumenes.md").read_text(encoding="utf-8").lower() + "sin medir")

    def test_analyze_never_reads_env(self):
        with tempfile.TemporaryDirectory() as repo, tempfile.TemporaryDirectory() as out:
            r = pathlib.Path(repo)
            (r / "src").mkdir()
            (r / ".env").write_text("DB_PASSWORD=SUPERSECRETO\n")
            (r / ".env.example").write_text("DB_PASSWORD=\n")
            (r / "src" / "a.ts").write_text("import { b } from './b.js';\nconst p = process.env.DB_PASSWORD;\n")
            (r / "src" / "b.ts").write_text("export const b = 1;\n")
            run("analyze", str(r), "-o", out)
            blob = "".join(p.read_text(encoding="utf-8") for p in pathlib.Path(out).rglob("*") if p.is_file())
            self.assertNotIn("SUPERSECRETO", blob)
            g = json.loads((pathlib.Path(out) / "00-grafo/graph.json").read_text(encoding="utf-8"))
            self.assertEqual(len(g["edges"]), 1)
            self.assertIn("DB_PASSWORD", g["env_vars"])

    def test_network_render_and_mask(self):
        with tempfile.TemporaryDirectory() as out:
            run("net", str(ROOT / "examples/network.json"), "-o", out)
            html = (pathlib.Path(out) / "02-arquitectura/red.html").read_text(encoding="utf-8")
            self.assertIn("10.20.4.22", html)
            self.assertIn("Ocultar IPs", html)
            xml.dom.minidom.parse(str(pathlib.Path(out) / "02-arquitectura/red.svg"))
        with tempfile.TemporaryDirectory() as out:
            run("net", str(ROOT / "examples/network.json"), "-o", out, "--mask-ips")
            for f in ("red.html", "red.svg", "red-pendientes.md"):
                blob = (pathlib.Path(out) / "02-arquitectura" / f).read_text(encoding="utf-8")
                self.assertNotIn("10.20.4.22", blob)
                self.assertNotIn("10.50.8.15", blob)

    def test_network_pending_questions(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import net
        spec = {"sites": [{"id": "a", "label": "AWS", "kind": "aws"}, {"id": "o", "label": "DC", "kind": "onprem"}],
                "nodes": [{"id": "x", "name": "API", "site": "a"}, {"id": "y", "name": "BD", "site": "o", "ip": "10.1.1.1"}, {"id": "z", "name": "Huerfano"}],
                "flows": [{"id": "1", "label": "x", "hops": ["x", "y"]}]}
        errs, pend = net.check(spec)
        blob = " ".join(pend)
        self.assertFalse(errs)
        self.assertIn("IP u hostname de «API»", blob)
        self.assertIn("sitio está «Huerfano»", blob)
        self.assertIn("firewall", blob)  # cruza de sitio sin elemento de red
        self.assertIn("protocolo y puerto", blob)

    def test_network_detection_in_analyze(self):
        with tempfile.TemporaryDirectory() as repo, tempfile.TemporaryDirectory() as out:
            r = pathlib.Path(repo)
            (r / "src").mkdir()
            (r / ".env").write_text("X=10.9.9.9" + chr(10))
            (r / "src" / "a.js").write_text('const u="mssql://sa:Clave123@10.196.4.50:1433/x"; const h="srv.database.windows.net"; app.listen(3000); // v1.2.3.4' + chr(10))
            run("analyze", str(r), "-o", out)
            g = json.loads((pathlib.Path(out) / "00-grafo/graph.json").read_text(encoding="utf-8"))
            nh = g["network_hints"]
            self.assertEqual([i["ip"] for i in nh["ips"]], ["10.196.4.50"])
            self.assertEqual(nh["segments_detected"][0]["cidr"], "10.196.4.0/24")
            self.assertTrue(any(h["site_hint"] == "azure" for h in nh["hosts"]))
            self.assertEqual(nh["listen_ports"][0]["port"], 3000)
            blob = "".join(p.read_text(encoding="utf-8") for p in pathlib.Path(out).rglob("*") if p.is_file())
            self.assertNotIn("Clave123", blob)
            self.assertNotIn("10.9.9.9", blob)  # .env real jamás se lee
            run("analyze", str(r), "-o", out, "--mask-ips")
            blob = (pathlib.Path(out) / "00-grafo/graph.json").read_text(encoding="utf-8")
            self.assertNotIn("10.196.4.50", blob)

    def test_net_init_draft(self):
        with tempfile.TemporaryDirectory() as repo, tempfile.TemporaryDirectory() as out:
            r = pathlib.Path(repo)
            (r / "a.js").write_text('const u="mssql://u:p@10.196.4.50:1433/x"; app.listen(3000);' + chr(10))
            run("analyze", str(r), "-o", out)
            run("net-init", str(pathlib.Path(out) / "00-grafo/graph.json"), "-o", str(pathlib.Path(out) / "spec/network.json"))
            run("net", str(pathlib.Path(out) / "spec/network.json"), "-o", out)
            self.assertTrue((pathlib.Path(out) / "02-arquitectura/red.html").exists())

    def test_graph_reuse_and_html(self):
        with tempfile.TemporaryDirectory() as repo, tempfile.TemporaryDirectory() as out:
            r = pathlib.Path(repo)
            (r / "a.js").write_text("import './b.js';" + chr(10))
            (r / "b.js").write_text("export const b = 1;" + chr(10))
            first = run("analyze", str(r), "-o", out)
            self.assertIn("OK grafo:", first)
            self.assertTrue((pathlib.Path(out) / "00-grafo/graph.html").exists())
            self.assertIn("REUTILIZA", run("analyze", str(r), "-o", out))        # repo sin cambios: no relee
            (r / "c.js").write_text("export const c = 1;" + chr(10))
            self.assertIn("OK grafo:", run("analyze", str(r), "-o", out))        # cambió: re-analiza
            self.assertIn("REUTILIZA", run("analyze", str(r), "-o", out))
            self.assertIn("OK grafo:", run("analyze", str(r), "-o", out, "--force"))

    def test_graph_import_nodelink(self):
        with tempfile.TemporaryDirectory() as out:
            gj = pathlib.Path(out) / "g.json"
            gj.write_text(json.dumps({"nodes": [{"id": "a", "label": "A", "community": 0}, {"id": "b", "label": "B", "community": 1}],
                                      "links": [{"source": "a", "target": "b", "relation": "calls"}]}))
            run("graph", "--from", str(gj), "-o", out)
            html = (pathlib.Path(out) / "00-grafo/graph.html").read_text(encoding="utf-8")
            self.assertIn('"nodes"', html)
            self.assertIn("canvas", html)

    def test_arch_pending_questions(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import arch
        q = arch.check({"nodes": [{"id": "a", "name": "API", "icon": "express"}, {"id": "b", "name": "BD", "icon": "database", "site": "AWS", "ip": "10.0.0.1"},
                                  {"id": "u", "name": "Usuario", "icon": "user"}],
                        "edges": [{"from": "a", "to": "b", "kind": "dashed"}]})
        blob = " ".join(q)
        self.assertIn("sitio/servidor corre «API»", blob)
        self.assertIn("IP u hostname de «API»", blob)
        self.assertIn("integración", blob)
        self.assertNotIn("«BD»? (on-prem", blob)
        self.assertNotIn("Usuario", blob)

    def test_volume_sample_and_rates(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import erd, volsql
        spec = {"entities": [
            {"name": "projects", "columns": [{"name": "id", "type": "int", "pk": True}, {"name": "created_at", "type": "datetime"}],
             "volume": {"rows": 1000, "sample": {"days": 7, "rows": 70, "date_column": "created_at"}}},
            {"name": "tasks", "columns": [{"name": "id", "type": "int", "pk": True}],
             "volume": {"rows": 8000, "per_parent": {"entity": "projects", "ratio": 8}}},
            {"name": "logs", "columns": [{"name": "id", "type": "int"}], "volume": {"rows": 5, "rows_per_day": 10, "source": "supuesto"}}]}
        erd.normalize(spec)
        self.assertAlmostEqual(spec["entities"][0]["volume"]["rows_per_month"], 300)     # 70/7*30
        self.assertEqual(spec["entities"][0]["volume"]["source"], "medido")
        self.assertAlmostEqual(spec["entities"][1]["volume"]["rows_per_month"], 2400)    # 300*8
        self.assertAlmostEqual(spec["entities"][2]["volume"]["rows_per_month"], 300)     # 10*30
        self.assertEqual(volsql.date_column(spec["entities"][0]), "created_at")
        sql, nodate = volsql.build_sql(spec, "postgres", 7)
        self.assertIn("now() - interval '7 days'", sql)
        self.assertEqual(nodate, ["tasks", "logs"])
        self.assertEqual(volsql.build_sql({"entities": [{"name": "x; DROP TABLE y", "columns": []}]}, "mssql", 7)[0].count("DROP"), 1)  # solo en comentario
        self.assertNotIn("FROM x; DROP", volsql.build_sql({"entities": [{"name": "x; DROP TABLE y", "columns": []}]}, "mssql", 7)[0])

    def test_volapply_and_report(self):
        with tempfile.TemporaryDirectory() as out:
            o = pathlib.Path(out)
            (o / "spec").mkdir()
            (o / "spec/erd.json").write_text(json.dumps({"title": "t", "entities": [
                {"name": "orders", "columns": [{"name": "id", "type": "int", "pk": True}, {"name": "created_at", "type": "datetime"}]}]}))
            (o / "res.csv").write_text("tabla,filas_total,filas_7d,desde,hasta,columna_fecha" + chr(10) + "orders,12000,140,2025-01-01,2026-11-01,created_at" + chr(10))
            run("volapply", str(o / "res.csv"), str(o / "spec/erd.json"))
            v = json.loads((o / "spec/erd.json").read_text(encoding="utf-8"))["entities"][0]["volume"]
            self.assertEqual((v["rows"], v["sample"]["rows"], v["source"]), (12000, 140, "medido"))
            run("erd", str(o / "spec/erd.json"), "-o", out)
            self.assertIn("muestra 7 d", (o / "03-modelo-datos/volumenes.md").read_text(encoding="utf-8"))
            run("net", str(ROOT / "examples/network.json"), "-o", out)
            run("report", "-o", out, "--title", "Demo")
            html = (o / "documentacion.html").read_text(encoding="utf-8")
            self.assertIn("Demo", html)
            self.assertIn("Presentar", html)
            self.assertIn("<iframe", html)                      # red.html embebido
            self.assertIn('disabled', html)                     # secciones no generadas (grafo, flujos) deshabilitadas
            run("report", "-o", out, "--mask-ips")
            self.assertNotIn("10.20.4.22", (o / "documentacion.html").read_text(encoding="utf-8"))

    def test_growth_projection(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import erd
        v = {"rows": 1000, "growth_pct_month": 10}
        self.assertAlmostEqual(erd.project(v, 12), 1000 * 1.1 ** 12)
        self.assertEqual(erd.project({"rows": 100, "rows_per_month": 5}, 6), 130)
        self.assertIsNone(erd.project(None, 6))


if __name__ == "__main__":
    unittest.main()
