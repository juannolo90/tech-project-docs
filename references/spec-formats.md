# Formatos de spec (JSON)

Los cuatro specs viven en `docs/spec/`. Ejemplos completos en `examples/`.

## Tema (opcional) — `--theme tema.json`
```json
{"azul":"#1B3A5C","azul_med":"#2C5282","naranjo":"#E8811A","gris":"#64748B",
 "gris_light":"#F1F5F9","verde":"#10B981","rojo":"#EF4444"}
```
Significado: `azul` títulos y alta jerarquía · `azul_med` conexiones/subtítulos · `naranjo` énfasis y flujo principal · `gris` texto secundario · `gris_light` fondos · `verde` positivo/fin · `rojo` riesgo.

## architecture.json
```json
{
  "title": "…", "subtitle": "…",
  "groups": [{"id":"g1","label":"Backend · Node.js","icon":"nodejs","style":"dashed","parent":"otro"}],
  "nodes":  [{"id":"api","name":"API REST","role":"Express","icon":"express","group":"g1",
              "site":"AWS sa-east-1","ip":"10.20.4.22","col":2,"row":0,"x":300,"y":150,"tile":"dark"}],
  "edges":  [{"from":"web","to":"api","label":"REST","kind":"primary|internal|dashed|risk"}]
}
```
- `icon`: nombre devicon/svgl (`postgresql`, `redis`, `nodejs`, `docker`…), alias comunes (`mssql`, `pg`, `k8s`…) o genérico: `database server user users queue cache cloud api file clock browser gear box lock mail plug refresh chart`.
- Layout automático: columna = profundidad según las flechas; **cada grupo de primer nivel ocupa su propia banda** (no se solapan). Sobrescribe con `col`/`row` o con `x`/`y` absolutos.
- `tile: "dark"` para logos blancos/claros.
- `site` / `ip` / `host` (opcionales) se muestran bajo el rol. Si faltan, `tdocs arch` los lista como **preguntas pendientes** (también una arista `primary`/`dashed`/`risk` sin `label`: «¿cómo se llama la integración?»).

## network.json  (paso 3b · `tdocs net`)
```json
{
  "title":"…","subtitle":"…","env":"PRD",
  "sites":[{"id":"aws","label":"AWS · cuenta prod","kind":"aws|azure|gcp|sap|onprem|saas|internet|users|unknown","detail":"sa-east-1"}],
  "segments":[{"id":"vpc","site":"aws","parent":"otro_segmento","label":"VPC Prod","cidr":"10.20.4.0/22","kind":"vpc|vnet|subnet|vlan|dmz"}],
  "nodes":[{"id":"api","name":"API REST","role":"Express","icon":"express","site":"aws","segment":"vpc",
            "ip":"10.20.4.22","host":"api.interno","port":3000,"kind":"app|db|user|saas|external|firewall|gateway|vpn|lb|proxy|router|dns"}],
  "flows":[{"id":"1","label":"Usuarios → portal","kind":"principal|interno|batch|externo|referencia|riesgo","protocol":"HTTPS 443",
            "hops":["usr","fw",{"id":"api","label":"TCP 3000"}],"note":"regla de firewall…"}],
  "pending":["pregunta abierta libre"]
}
```
- Un nodo con `kind` de red (`firewall`, `gateway`, `vpn`, `lb`, `proxy`, `router`, `dns`) se dibuja con borde rojo punteado.
- `hops` = recorrido ordenado de nodos; cada par consecutivo es un salto. Un hop puede ser `{"id","label"}` para rotular el puerto de ese salto.
- Sin `site`/`ip`/`segment`/`protocol`, o un flujo que cruza de sitio sin elemento de red, se reporta como **pendiente por confirmar** (no se inventa).
- `--mask-ips` deja `10.20.x.x` en todas las salidas; sin la bandera, `red.html` incluye un botón «Ocultar IPs».
- Ejemplo ficticio completo: `examples/network.json`.

## erd.json
```json
{
  "title": "…", "subtitle": "…",
  "entities": [{
    "name": "orders",
    "columns": [{"name":"id","type":"bigint","pk":true},
                {"name":"customer_id","type":"bigint","fk":"customers.id"},
                {"name":"payload","type":"jsonb","inferred":true}],
    "volume": {"rows": 900000, "growth_pct_month": 4, "avg_row_bytes": 180, "source": "medido"}
  }],
  "relations": [{"from":"orders.customer_id","to":"customers.id","card":"N:1"}]
}
```
- Las relaciones también se derivan de `fk`. `card` = `N:1` (por defecto), `1:1`, etc.
- Crecimiento: `growth_pct_month` (compuesto) **o** `rows_per_month` (lineal). Si no hay ninguno se **deriva** (y queda anotado en `derived`):
  - `rows_per_day: 10` → tasa de negocio («se crean 10 proyectos al día») × 30, `source: "supuesto"`.
  - `sample: {"days":7,"rows":420,"date_column":"created_at"}` → muestra medida de N días × 30/N (la rellena `tdocs volapply`).
  - `per_parent: {"entity":"projects","ratio":8}` → filas hijas por cada padre × tasa del padre.
- `source`: `medido` | `estimado` | `supuesto`. Sin `volume` → «sin medir».

## flows.json
```json
{"title":"…","flows":[
 {"id":"checkout","type":"flowchart","title":"…","description":"…",
  "nodes":[{"id":"a","label":"Inicio","kind":"start|process|decision|io|risk|end"}],
  "edges":[{"from":"a","to":"b","label":"sí"}]},
 {"id":"login","type":"sequence","title":"…",
  "actors":[{"id":"U","label":"Navegador"},{"id":"A","label":"API"}],
  "messages":[{"from":"U","to":"A","label":"POST /login"},{"from":"A","to":"U","label":"token","kind":"return"}]}
]}
```
- Un mensaje con `from == to` se dibuja como auto-llamada.
- Las aristas que vuelven hacia atrás (reintentos, bucles) se dibujan punteadas por el costado.
