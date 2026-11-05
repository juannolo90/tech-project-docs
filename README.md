# tech-project-docs

**Una skill, una frase:** *«genera documentación proyecto tecnológico»* → grafo del código, flujos de operación, arquitectura (`.drawio`) y modelo entidad-relación con volúmenes y proyección de crecimiento.

> One skill, one sentence: *"generate technology project documentation"* → code graph, operating flows, architecture (`.drawio`) and an ER model with row volumes and growth projection. Spanish-first; works with any agent that supports `SKILL.md` skills.

## Qué genera

| # | Entregable | Archivos |
|---|---|---|
| 1 | Grafo del proyecto | `docs/00-grafo/graph.json`, `GRAPH_REPORT.md` |
| 2 | Flujos de operación | `docs/01-flujos/*.svg`, `flujos.html`, `flujos.md` (Mermaid) |
| 3 | Arquitectura con iconos | `docs/02-arquitectura/arquitectura.drawio` + `.svg` |
| 3b | **Red y despliegue** (sitios on-prem/AWS/Azure/SAP, segmentos/CIDR, IPs, firewalls/VPN, flujos numerables) | `docs/02-arquitectura/red.html` (interactivo), `red.svg`, `red-pendientes.md` |
| 1b | **Visor del grafo** (reutiliza grafos existentes, p. ej. graphify, sin releer el código) | `docs/00-grafo/graph.html` |
| 4 | Modelo ER + volúmenes | `docs/03-modelo-datos/modelo-datos.drawio`, `.svg`, `volumenes.md`, `.mmd` |

Ejemplo (datos ficticios): ver `examples/`.

**Todo en un HTML:** `docs/documentacion.html` reúne grafo, flujos, arquitectura, red, datos/volúmenes y pendientes en pestañas, con modo presentación (tecla `P`, flechas ← →).

**Ahorro de tokens:** si ya existe `docs/00-grafo/graph.json` (o un `graphify-out/`), la skill lo reutiliza; `analyze` detecta con una huella de archivos si el repo cambió y no relee el código.

**Red y despliegue:** el analizador detecta IPs, CIDR, hosts cloud y puertos en código/config (nunca `.env` reales) y la skill **pregunta** lo que no puede saber (sitio de cada IP, segmentos, firewalls/VPN, ambientes). Las IPs internas son sensibles: usa `--mask-ips` antes de compartir `docs/`.

## Instalación

```bash
# Claude Code / agentes compatibles
npx skills add juannolo90/tech-project-docs
# o manual
git clone https://github.com/juannolo90/tech-project-docs ~/.claude/skills/tech-project-docs
```

Requisitos: Python 3.9+ (solo librería estándar). Opcional para revisar los diagramas como imagen: `pip install playwright && python3 -m playwright install chromium`.

## Uso

En tu agente, desde la raíz del proyecto: **«genera documentación proyecto tecnológico»**.
El agente ejecuta el flujo de `SKILL.md`: analiza el repo, lee el código y escribe tres specs JSON; los scripts los dibujan. También puedes usar el CLI directamente:

```bash
python3 scripts/tdocs.py analyze ./mi-proyecto -o docs
python3 scripts/tdocs.py flows  docs/spec/flows.json        -o docs
python3 scripts/tdocs.py arch   docs/spec/architecture.json -o docs
python3 scripts/tdocs.py net-init docs/00-grafo/graph.json -o docs/spec/network.json   # borrador: IPs, segmentos y hosts detectados
python3 scripts/tdocs.py net    docs/spec/network.json     -o docs   # [--mask-ips] [--strict]
python3 scripts/tdocs.py erd    docs/spec/erd.json          -o docs
python3 scripts/tdocs.py volsql docs/spec/erd.json --dialect mssql -o docs     # SQL de solo lectura: total + muestra de 7 días
python3 scripts/tdocs.py volapply resultados.csv docs/spec/erd.json
python3 scripts/tdocs.py report -o docs        # documentacion.html: todo en pestañas / presentación
python3 scripts/tdocs.py png -o docs && python3 scripts/tdocs.py index -o docs
```

## Principios

- **Autónoma:** no depende de otras skills ni de herramientas externas. Todo el código está aquí, escrito desde cero.
- **Seguridad:** nunca lee `.env` reales; solo nombres de variables de `.env.example`. Enmascara IPs.
- **Honestidad de datos:** los volúmenes son medidos o supuestos declarados (`source`); sin dato se muestra «sin medir». Lo inferido va en cursiva.
- **Tema configurable:** paleta por `--theme` (por defecto azul/naranjo/gris).

## Iconos y licencias

Los iconos de tecnología **no se incluyen** en este repositorio: se descargan en tiempo de ejecución desde [devicon](https://github.com/devicons/devicon) (MIT) y [svgl](https://svgl.app) y se cachean localmente; sin red se usan pictogramas genéricos propios. Las marcas pertenecen a sus dueños. Si usas iconos de AWS/Google Cloud/Azure, respeta sus guías de uso y no los redistribuyas en tu repo.

## Pruebas

```bash
python3 -m unittest discover -s tests
```

## Licencia

MIT — ver [LICENSE](LICENSE).
