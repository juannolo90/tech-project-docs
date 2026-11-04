# Formatos de spec (JSON)

Los tres specs viven en `docs/spec/`. Ejemplos completos en `examples/`.

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
              "col":2,"row":0,"x":300,"y":150,"tile":"dark"}],
  "edges":  [{"from":"web","to":"api","label":"REST","kind":"primary|internal|dashed|risk"}]
}
```
- `icon`: nombre devicon/svgl (`postgresql`, `redis`, `nodejs`, `docker`…), alias comunes (`mssql`, `pg`, `k8s`…) o genérico: `database server user users queue cache cloud api file clock browser gear box lock mail plug refresh chart`.
- Layout automático: columna = profundidad según las flechas; **cada grupo de primer nivel ocupa su propia banda** (no se solapan). Sobrescribe con `col`/`row` o con `x`/`y` absolutos.
- `tile: "dark"` para logos blancos/claros.

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
- Crecimiento: `growth_pct_month` (compuesto) **o** `rows_per_month` (lineal).
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
