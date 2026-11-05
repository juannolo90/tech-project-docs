# Cómo medir volúmenes (solo lectura)

Pregunta primero al usuario si puedes consultar la BD (solo lectura). Si no, que ejecute esto con un usuario de solo lectura y pegue el resultado. No ejecutes nada sin su confirmación y nunca guardes credenciales.

**Atajo:** `tdocs volsql erd.json --dialect <motor>` genera `consultas-volumen.sql` con el total y una **muestra de 7 días** por tabla (usa su columna de fecha); `tdocs volapply resultados.csv` aplica el resultado al `erd.json`. Si la tabla no tiene fecha o no hay acceso, pregunta tasas de negocio (`rows_per_day`, `per_parent`).

## Filas y tamaño por tabla

**SQL Server**
```sql
SELECT t.name AS tabla, SUM(p.rows) AS filas,
       SUM(a.total_pages) * 8 * 1024 AS bytes
FROM sys.tables t
JOIN sys.indexes i ON i.object_id = t.object_id AND i.index_id IN (0,1)
JOIN sys.partitions p ON p.object_id = t.object_id AND p.index_id = i.index_id
JOIN sys.allocation_units a ON a.container_id = p.partition_id
GROUP BY t.name ORDER BY filas DESC;
```
**PostgreSQL**
```sql
SELECT relname AS tabla, reltuples::bigint AS filas, pg_total_relation_size(oid) AS bytes
FROM pg_class WHERE relkind = 'r' AND relnamespace = 'public'::regnamespace ORDER BY filas DESC;
```
**MySQL / MariaDB**
```sql
SELECT table_name AS tabla, table_rows AS filas, data_length + index_length AS bytes
FROM information_schema.tables WHERE table_schema = DATABASE() ORDER BY filas DESC;
```
**Oracle**
```sql
SELECT table_name AS tabla, num_rows AS filas, blocks * 8192 AS bytes FROM user_tables ORDER BY num_rows DESC;
```
**SAP HANA**
```sql
SELECT table_name AS tabla, record_count AS filas, table_size AS bytes FROM m_tables WHERE schema_name = CURRENT_SCHEMA ORDER BY record_count DESC;
```

## Crecimiento mensual
Si la tabla tiene una columna de fecha de creación (`created_at`):
```sql
SELECT DATE_TRUNC('month', created_at) AS mes, COUNT(*) AS filas FROM <tabla> GROUP BY 1 ORDER BY 1;  -- PostgreSQL
SELECT FORMAT(created_at,'yyyy-MM') AS mes, COUNT(*) AS filas FROM <tabla> GROUP BY FORMAT(created_at,'yyyy-MM') ORDER BY 1;  -- SQL Server
```
- Con ≥6 meses de historia: `growth_pct_month` = variación mensual promedio (o `rows_per_month` si el crecimiento es lineal).
- `avg_row_bytes` = `bytes / filas`.
- Sin historia: pregunta el supuesto al usuario y regístralo con `source: "supuesto"`.
- Las cifras `reltuples`/`num_rows`/`table_rows` son estimaciones del motor: usa `source: "estimado"`. Un `COUNT(*)` exacto es `medido`.
