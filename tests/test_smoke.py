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

    def test_growth_projection(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import erd
        v = {"rows": 1000, "growth_pct_month": 10}
        self.assertAlmostEqual(erd.project(v, 12), 1000 * 1.1 ** 12)
        self.assertEqual(erd.project({"rows": 100, "rows_per_month": 5}, 6), 130)
        self.assertIsNone(erd.project(None, 6))


if __name__ == "__main__":
    unittest.main()
