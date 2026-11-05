---
name: tech-project-docs
description: Genera la documentación técnica completa de un proyecto (grafo del código, flujos de operación, arquitectura en .drawio con iconos por componente, y modelo entidad-relación con volúmenes y proyección de crecimiento). Usar cuando el usuario diga "genera documentación proyecto tecnológico", "documenta este proyecto", "diagrama de arquitectura", "modelo de datos con volúmenes" o "generate project documentation". Autónoma: no depende de otras skills.
---

# tech-project-docs

Una sola skill, cinco entregables, todo en `docs/` del proyecto:

| Paso | Qué hace | Salida |
|---|---|---|
| 1. Grafo | Entiende módulos, entradas, rutas, entornos y tablas; **reutiliza** un grafo existente | `docs/00-grafo/graph.json`, `GRAPH_REPORT.md`, `graph.html` (visor interactivo) |
| 2. Flujos | Flujos de operación (diagrama de flujo y de secuencia) | `docs/01-flujos/*.svg`, `flujos.html`, `flujos.md` (Mermaid) |
| 3. Arquitectura | Componentes agrupados, con icono por tecnología | `docs/02-arquitectura/arquitectura.drawio` + `.svg` |
| 3b. Red y despliegue | Sitios (on-prem/AWS/Azure/SAP/SaaS), segmentos con CIDR, IPs, elementos de red y flujos numerados | `docs/02-arquitectura/red.html` (interactivo) + `red.svg` + `red-pendientes.md` |
| 4. Datos | Modelo ER + volúmenes y crecimiento a 6/12/24/36 meses (medido con muestra de 7 días o por tasa de negocio) | `docs/03-modelo-datos/modelo-datos.drawio`, `.svg`, `volumenes.md`, `.mmd`, `consultas-volumen.sql` |
| 6. Todo en uno | Un HTML con todo lo anterior en pestañas o diapositivas | `docs/documentacion.html` |

Todo el código está en `scripts/` (solo librería estándar de Python 3.9+). Los scripts **dibujan**; tú **lees el código y decides el contenido** escribiendo specs JSON.

## Cuándo activarse

Frases como: «genera documentación proyecto tecnológico», «documenta este proyecto», «arma la arquitectura/ER/flujos de esta app». Si el usuario pide solo una parte (p. ej. "solo el modelo de datos"), ejecuta solo ese paso.

## Reglas que no se negocian

1. **Nunca leas ni imprimas `.env`** ni secretos. Del `.env.example` solo importan los nombres de variables. Las credenciales dentro de URLs de conexión jamás se copian (solo host y puerto).
1b. **IPs y topología son datos sensibles.** `docs/` puede contener IPs/CIDR internos: avisa al usuario antes de commitear/publicar `docs/` y ofrece `--mask-ips` (deja `10.20.x.x`). Nunca pegues IPs internas en issues, PRs ni repos públicos.
2. **No inventes volúmenes.** `volume.rows` sale de una medición real (ver `references/volumenes.md`) o de un supuesto que el usuario te dio, y siempre con `source` (`medido`, `estimado`, `supuesto`). Sin dato → omite `volume` y el diagrama mostrará «sin medir».
3. **Marca lo inferido**: columnas deducidas de consultas llevan `"inferred": true` (se dibujan en cursiva). No presentes inferencias como esquema real.
4. **Pregunta lo que no sabes (red).** Una IP privada no dice si el servidor está on-prem, en AWS o en Azure; el código no dice si hay firewall, VPN o balanceador. Nunca lo supongas: usa los «pendientes» del paso 3b y pregúntalos (ver abajo).
4b. **Revisa visualmente** cada diagrama (paso «Verificar») antes de entregarlo. Un diagrama con flechas sobre texto no está terminado.
5. **Nunca consultes una base de datos sin que el usuario lo autorice** (solo lectura, solo `SELECT`/`COUNT`, sin guardar credenciales).
5b. **Pide confirmación antes de escribir dentro del repo del usuario** si `docs/` ya existe.
5c. **Cada comando (`arch`, `net`, `erd`) termina con «PENDIENTES POR CONFIRMAR».** Si aparece esa lista, tu siguiente acción es preguntarla al usuario con AskUserQuestion, no entregar.
6. Responde en el idioma del usuario (por defecto español). Títulos y etiquetas de los diagramas en ese idioma.

## Flujo de trabajo

Sea `S` la carpeta de esta skill y `R` el repo a documentar.

### 0. Preparar
- Confirma la ruta del proyecto y la carpeta de salida (por defecto `R/docs`).
- Tema de color opcional: JSON con claves `azul, azul_med, naranjo, gris, gris_light, verde, rojo` (ver `references/spec-formats.md`). Pásalo con `--theme`.

### 1. Grafo (entender el proyecto) — reutiliza antes de generar
**Regla de ahorro: nunca regeneres ni releas el código si ya existe un grafo.** Revisa en este orden y para en el primero que exista:
1. `docs/00-grafo/graph.json` ya generado → `analyze` compara una huella (ruta+tamaño+fecha, sin leer contenido) y, si el repo no cambió, **reutiliza** el grafo y solo asegura `graph.html`. Con `--force` se rehace.
2. El repo trae `graphify-out/` (graphify u otro grafo node-link) → **no lo regeneres** (cuesta tokens). Lee su `GRAPH_REPORT.md` e impórtalo:
   ```bash
   python3 S/scripts/tdocs.py graph --from R/graphify-out/graph.json -o R/docs     # solo transforma el JSON
   python3 S/scripts/tdocs.py analyze R -o R/docs                                  # barato y local: agrega rutas, env, tablas e IPs/segmentos
   ```
3. No hay nada → `analyze` (script local, **0 tokens**: no usa LLM).
```bash
python3 S/scripts/tdocs.py analyze R -o R/docs        # genera graph.json, GRAPH_REPORT.md y graph.html (visor interactivo)
```
Lee solo `docs/00-grafo/GRAPH_REPORT.md` (o el de graphify). Después **abre únicamente los archivos clave** que el reporte señala: puntos de entrada, nodos de mayor grado, conexión a BD, jobs/crons, integraciones. No recorras el repo completo.

### 2. Flujos de operación
Escribe `docs/spec/flows.json` (formato en `references/spec-formats.md`): 2–5 flujos que cuenten cómo opera el sistema (flujo principal de negocio, arranque/inicialización, manejo de errores, batch). Usa `flowchart` para lógica con decisiones y `sequence` para interacción entre componentes.
```bash
python3 S/scripts/tdocs.py flows docs/spec/flows.json -o docs
```

### 3. Arquitectura
Escribe `docs/spec/architecture.json`: `nodes` (un componente por tecnología/módulo relevante, con `icon`), `groups` (runtime, vendor, red, repo) y `edges` (`primary` = flujo principal, `internal`, `dashed` = batch/externo, `risk`). Usa `suggested_components` de `graph.json` como punto de partida.
**Pregunta lo que el código no dice** (AskUserQuestion, 1–4 preguntas por turno, con «No sé / lo averiguo»): sitio o servidor de cada componente (on-prem, AWS, Azure, SAP, SaaS), IP/hostname, y el **nombre de cada integración** (iFlow, API, job, cola, archivo) con su protocolo. Complétalos en el spec con los campos opcionales `site`, `ip`/`host` de cada nodo y `label` de cada arista.
```bash
python3 S/scripts/tdocs.py arch docs/spec/architecture.json -o docs
```
Al terminar imprime y guarda en `arquitectura-pendientes.md` lo que sigue sin respuesta (nodo sin sitio/IP, integración sin nombre): pregúntalo y vuelve a ejecutar. Los nodos muestran `sitio · IP` bajo el rol.
- Los iconos se descargan en tiempo de ejecución desde **devicon** y **svgl** (y se cachean en `~/.cache/tech-project-docs`). Si no hay red o el icono no existe, se usa un pictograma genérico (`database`, `server`, `queue`, `cache`, `cloud`, `api`, `clock`, `lock`, `browser`, `user`…). Para un logo propio: `--icons-dir carpeta` con `nombre.svg`.
- No se redistribuyen logos de marca; no recolores logos.

### 3b. Red y despliegue (dónde corre cada cosa)
Responde: ¿en qué **sitio** está cada componente (on-prem, AWS, Azure, SAP RISE, SaaS, Internet), en qué **segmento** (VPC/VNet/subred/VLAN + CIDR), con qué **IP:puerto**, y **por qué elementos de red** pasa cada flujo (firewall, VPN/Direct Connect/ExpressRoute, gateway, proxy, balanceador).
```bash
python3 S/scripts/tdocs.py analyze R -o R/docs          # (ya hecho en el paso 1) llena graph.json → network_hints
python3 S/scripts/tdocs.py net-init docs/00-grafo/graph.json -o docs/spec/network.json   # borrador
```
`network_hints` trae lo detectado en código/config (nunca `.env` reales): IPs (con tipo privada/pública), CIDR, hosts (con sitio probable por sufijo: `*.database.windows.net` → Azure, `*.rds.amazonaws.com` → AWS, `*.hana.ondemand.com` → SAP…), puertos y segmentos /24 agrupados.

**Antes de completar `network.json`, pregunta al usuario** (usa AskUserQuestion; agrupa en 1–4 preguntas por turno, ofrece opciones y «No sé / lo averiguo»):
1. Sitio de cada IP privada detectada (¿on-prem, AWS, Azure, SAP RISE, otro?) y, si es nube, cuenta/suscripción y región.
2. VPC/VNet/subred/VLAN y CIDR de cada segmento; si hay DMZ.
3. ¿Hay firewall, VPN/Direct Connect/ExpressRoute, proxy, balanceador o API gateway entre usuarios → app → datos? ¿Cuáles y con qué IP?
4. Ambientes (DEV/QA/PRD): cuál se documenta y si las IPs difieren.
5. Desde dónde acceden los usuarios (oficina, VPN, internet) y con qué protocolo/puerto.
Lo que el usuario no sepa queda como pendiente visible en el diagrama (nodo con «IP por confirmar»), nunca inventado.
```bash
python3 S/scripts/tdocs.py net docs/spec/network.json -o docs      # [--mask-ips] [--strict]
```
Escribe en consola y en `red-pendientes.md` las preguntas que aún faltan (ej. «¿el flujo 2 cruza de sitio: hay firewall/VPN en medio?»). Itera preguntando hasta que la lista esté vacía o el usuario acepte los huecos. `red.html` permite resaltar cada flujo (chips, líneas o número), ver su tabla de saltos con IP y puerto, y ocultar IPs con un botón para capturas.

### 4. Modelo de datos con volúmenes
Escribe `docs/spec/erd.json`. Fuentes del esquema, en orden: DDL/Prisma detectado en `graph.json → schema_ddl`; migraciones/ORM del repo; si no hay nada, columnas inferidas de las consultas (`tables_referenced_in_code`) con `inferred: true`.
**OBLIGATORIO — antes de dar los volúmenes por terminados, llama a AskUserQuestion** (los scripts también imprimen estas preguntas como `PENDIENTES POR CONFIRMAR` y las guardan en `volumenes-pendientes.md`; no las ignores). Pregunta cómo obtener la volumetría y nunca asumas acceso:
1. **¿Puedo consultar la base de datos (solo lectura) para medir filas y crecimiento?** Opciones: *Sí, tengo una conexión/herramienta de solo lectura* · *No, te paso el SQL y lo ejecuto yo* · *No tengo acceso a la BD*.
2. Si **sí**: genera el SQL, **muéstraselo** y ejecútalo solo si el usuario confirma que la conexión es de solo lectura (idealmente réplica/QA). Solo `SELECT`/`COUNT`; no guardes credenciales ni cadenas de conexión en ningún archivo.
3. Si **no ejecutas tú**: entrega `consultas-volumen.sql` y pide que pegue el resultado (CSV).
```bash
python3 S/scripts/tdocs.py volsql docs/spec/erd.json --dialect mssql -o docs   # mssql|postgres|mysql|oracle|hana · [--days 7]
python3 S/scripts/tdocs.py volapply resultados.csv docs/spec/erd.json          # rellena rows, sample y source:"medido"
```
   El SQL cuenta el total **y una muestra de 7 días** sobre la columna de fecha de cada tabla (`created_at`, `fecha_*`…): con eso se extrapola la tasa mensual (filas/día × 30) sin esperar meses de historia.
4. **Tablas sin fecha o sin acceso a la BD → pregunta tasas de negocio**: «¿cuántos proyectos/pedidos/registros se crean al día?», «¿cuántas filas hijas por cada padre?». Regístralas como `rows_per_day` o `per_parent` con `source:"supuesto"` (ver `references/spec-formats.md`).
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
python3 S/scripts/tdocs.py report -o docs   # docs/documentacion.html: TODO en pestañas / presentación (tecla P, ← →)
python3 S/scripts/tdocs.py index  -o docs   # docs/README.md con todo enlazado
```
`documentacion.html` es autocontenido (Resumen · Grafo · Flujos · Arquitectura · Red · Datos y volúmenes · Pendientes); las secciones no generadas salen deshabilitadas. Si el usuario va a compartirlo fuera de su equipo, añade `--mask-ips`.
Entrega: ruta de `docs/`, qué es medido vs. inferido vs. sin dato, y los huecos (p. ej. volúmenes pendientes).

## Límites conocidos
- El analizador cubre bien JS/TS y Python; para Java, Go, C#, PHP, ABAP detecta imports/tablas de forma básica.
- La vista previa `.svg` y el `.drawio` comparten el layout, pero draw.io enruta las flechas por su cuenta: ajusta a mano si hace falta.
- Si el repo es muy grande, limita con carpetas: `tdocs.py analyze R/servicio-x`.
