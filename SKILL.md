---
name: tech-project-docs
description: Genera la documentación técnica completa de un proyecto (grafo del código, flujos de operación, arquitectura en .drawio con iconos por componente, y modelo entidad-relación con volúmenes y proyección de crecimiento). Usar cuando el usuario diga "genera documentación proyecto tecnológico", "documenta este proyecto", "diagrama de arquitectura", "modelo de datos con volúmenes" o "generate project documentation". Autónoma: no depende de otras skills.
---

# tech-project-docs

Una sola skill, cuatro entregables, todo en `docs/` del proyecto:

| Paso | Qué hace | Salida |
|---|---|---|
| 1. Grafo | Recorre el repo y entiende módulos, entradas, rutas, entornos y tablas | `docs/00-grafo/graph.json`, `GRAPH_REPORT.md` |
| 2. Flujos | Flujos de operación (diagrama de flujo y de secuencia) | `docs/01-flujos/*.svg`, `flujos.html`, `flujos.md` (Mermaid) |
| 3. Arquitectura | Componentes agrupados, con icono por tecnología | `docs/02-arquitectura/arquitectura.drawio` + `.svg` |
| 4. Datos | Modelo ER + volúmenes y crecimiento a 6/12/24/36 meses | `docs/03-modelo-datos/modelo-datos.drawio`, `.svg`, `volumenes.md`, `.mmd` |

Todo el código está en `scripts/` (solo librería estándar de Python 3.9+). Los scripts **dibujan**; tú **lees el código y decides el contenido** escribiendo specs JSON.

## Cuándo activarse

Frases como: «genera documentación proyecto tecnológico», «documenta este proyecto», «arma la arquitectura/ER/flujos de esta app». Si el usuario pide solo una parte (p. ej. "solo el modelo de datos"), ejecuta solo ese paso.

## Reglas que no se negocian

1. **Nunca leas ni imprimas `.env`** ni secretos. Del `.env.example` solo importan los nombres de variables. Redacta hosts/IPs internos en lo que escribas (el analizador ya las enmascara).
2. **No inventes volúmenes.** `volume.rows` sale de una medición real (ver `references/volumenes.md`) o de un supuesto que el usuario te dio, y siempre con `source` (`medido`, `estimado`, `supuesto`). Sin dato → omite `volume` y el diagrama mostrará «sin medir».
3. **Marca lo inferido**: columnas deducidas de consultas llevan `"inferred": true` (se dibujan en cursiva). No presentes inferencias como esquema real.
4. **Revisa visualmente** cada diagrama (paso «Verificar») antes de entregarlo. Un diagrama con flechas sobre texto no está terminado.
5. **Pide confirmación antes de escribir dentro del repo del usuario** si `docs/` ya existe.
6. Responde en el idioma del usuario (por defecto español). Títulos y etiquetas de los diagramas en ese idioma.

## Flujo de trabajo

Sea `S` la carpeta de esta skill y `R` el repo a documentar.

### 0. Preparar
- Confirma la ruta del proyecto y la carpeta de salida (por defecto `R/docs`).
- Tema de color opcional: JSON con claves `azul, azul_med, naranjo, gris, gris_light, verde, rojo` (ver `references/spec-formats.md`). Pásalo con `--theme`.

### 1. Grafo (entender el proyecto)
```bash
python3 S/scripts/tdocs.py analyze R -o R/docs
```
Lee `docs/00-grafo/GRAPH_REPORT.md`. Después **lee tú mismo los archivos clave**: puntos de entrada, nodos de mayor grado, conexión a BD, jobs/crons, integraciones. El reporte orienta, no reemplaza leer el código.

### 2. Flujos de operación
Escribe `docs/spec/flows.json` (formato en `references/spec-formats.md`): 2–5 flujos que cuenten cómo opera el sistema (flujo principal de negocio, arranque/inicialización, manejo de errores, batch). Usa `flowchart` para lógica con decisiones y `sequence` para interacción entre componentes.
```bash
python3 S/scripts/tdocs.py flows docs/spec/flows.json -o docs
```

### 3. Arquitectura
Escribe `docs/spec/architecture.json`: `nodes` (un componente por tecnología/módulo relevante, con `icon`), `groups` (runtime, vendor, red, repo) y `edges` (`primary` = flujo principal, `internal`, `dashed` = batch/externo, `risk`). Usa `suggested_components` de `graph.json` como punto de partida.
```bash
python3 S/scripts/tdocs.py arch docs/spec/architecture.json -o docs
```
- Los iconos se descargan en tiempo de ejecución desde **devicon** y **svgl** (y se cachean en `~/.cache/tech-project-docs`). Si no hay red o el icono no existe, se usa un pictograma genérico (`database`, `server`, `queue`, `cache`, `cloud`, `api`, `clock`, `lock`, `browser`, `user`…). Para un logo propio: `--icons-dir carpeta` con `nombre.svg`.
- No se redistribuyen logos de marca; no recolores logos.

### 4. Modelo de datos con volúmenes
Escribe `docs/spec/erd.json`. Fuentes del esquema, en orden: DDL/Prisma detectado en `graph.json → schema_ddl`; migraciones/ORM del repo; si no hay nada, columnas inferidas de las consultas (`tables_referenced_in_code`) con `inferred: true`.
Para volúmenes ofrece al usuario las consultas de `references/volumenes.md` (solo lectura) y pídele que pegue los resultados; **no te conectes a bases de datos de producción por tu cuenta**.
```bash
python3 S/scripts/tdocs.py erd docs/spec/erd.json -o docs
```
Genera además la tabla de proyección (+6/+12/+24/+36 meses, tamaño hoy y a 36 m). Marca en rojo lo que supere 10 GB y en naranjo lo que crece más de 3× en 24 m.

### 5. Verificar y cerrar
```bash
python3 S/scripts/tdocs.py png -o docs      # requiere: pip install playwright && python3 -m playwright install chromium
```
Abre cada PNG y revisa: ninguna flecha cruza texto ni cajas ajenas, grupos sin solapes, íconos visibles, nada cortado, tabla de volúmenes legible. Corrige el spec (posiciones con `x`/`y`/`col`/`row` si hace falta) y vuelve a ejecutar.
```bash
python3 S/scripts/tdocs.py index -o docs    # docs/README.md con todo enlazado
```
Entrega: ruta de `docs/`, qué es medido vs. inferido vs. sin dato, y los huecos (p. ej. volúmenes pendientes).

## Límites conocidos
- El analizador cubre bien JS/TS y Python; para Java, Go, C#, PHP, ABAP detecta imports/tablas de forma básica.
- La vista previa `.svg` y el `.drawio` comparten el layout, pero draw.io enruta las flechas por su cuenta: ajusta a mano si hace falta.
- Si el repo es muy grande, limita con carpetas: `tdocs.py analyze R/servicio-x`.
