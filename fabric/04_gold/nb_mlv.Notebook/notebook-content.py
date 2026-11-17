# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {}
# META }

# CELL ********************

# MAGIC %%configure -f
# MAGIC {
# MAGIC     "defaultLakehouse": {"name": "lh_silver"}
# MAGIC }

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# # Marts sobre silver con materialized lake views (D35)
# - **Qué hace:** crea el schema `mart` en `lh_silver` y define tres materialized lake views (MLV):
#   `fractura_por_pozo`, `produccion_primer_anio` y `fractura_vs_produccion`, que lee de las otras dos.
# - **La receta y el plato:** este notebook viaja con Git y con `dp-oil`; las MLV no, porque viven en
#   el lakehouse de cada ambiente. Se corre una vez por ambiente para crearlas y después las refresca
#   Fabric (lakehouse > *Manage materialized lake views*). `IF NOT EXISTS` lo hace seguro de repetir.
# - **Lakehouse por nombre:** la primera celda fija `lh_silver` como lakehouse por defecto con
#   `%%configure`, sin IDs: sirve en dev, feat y prod sin cambios.
# - **Cambiar una definición:** `IF NOT EXISTS` no pisa una MLV que ya existe. Para cambiarla se usa
#   `CREATE OR REPLACE`.
# - **Refresco:** full. El incremental pide Change Data Feed en todas las fuentes y que no reciban
#   updates ni deletes (o un `REFRESH_HINT`, en preview); `fractura` se reemplaza entera y
#   `produccion_pozo` recibe `MERGE`. Igual el SQL evita window functions y `DISTINCT`, para poder
#   pasar a incremental si silver cambia.
# - **En Azure:** no hay equivalente nativo en Synapse; el primo es la materialized view de Databricks.


# CELL ********************

# MAGIC %%sql
# MAGIC CREATE SCHEMA IF NOT EXISTS mart

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 1. Fractura por pozo
# Un pozo puede tener varias operaciones de fractura en el Adjunto IV: se suman etapas, arena y agua.
# Los pozos sin etapas informadas se descartan con un constraint (`ON MISMATCH DROP`); el lineage
# muestra cuántos.

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE MATERIALIZED LAKE VIEW IF NOT EXISTS mart.fractura_por_pozo
# MAGIC (
# MAGIC     CONSTRAINT etapas_informadas CHECK (etapas IS NOT NULL) ON MISMATCH DROP
# MAGIC )
# MAGIC COMMENT 'Un pozo fracturado por fila: etapas, arena y agua de todas sus operaciones (Adjunto IV).'
# MAGIC AS
# MAGIC SELECT idpozo,
# MAGIC        MAX(cuenca)                     AS cuenca,
# MAGIC        MAX(formacion_productiva)       AS formacion,
# MAGIC        MAX(tipo_reservorio)            AS tipo_reservorio,
# MAGIC        MAX(empresa_informante)         AS empresa,
# MAGIC        MIN(fecha_inicio_fractura)      AS primera_fractura,
# MAGIC        COUNT(*)                        AS operaciones,
# MAGIC        SUM(cantidad_fracturas)         AS etapas,
# MAGIC        MAX(longitud_rama_horizontal_m) AS rama_horizontal_m,
# MAGIC        SUM(coalesce(arena_bombeada_nacional_tn, 0) + coalesce(arena_bombeada_importada_tn, 0)) AS arena_tn,
# MAGIC        SUM(agua_inyectada_m3)          AS agua_m3
# MAGIC FROM energia.fractura
# MAGIC GROUP BY idpozo

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 2. Producción del primer año de cada pozo
# El primer mes es el primero con petróleo o gas, y se suman los 12 meses que arrancan ahí.
# `meses_con_dato` dice si el año está completo: un pozo nuevo todavía no llegó a 12.
# Sin window functions: el primer mes sale de un `GROUP BY` y se une con un `JOIN`.

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE MATERIALIZED LAKE VIEW IF NOT EXISTS mart.produccion_primer_anio
# MAGIC COMMENT 'Petróleo y gas de los primeros 12 meses de cada pozo, desde su primer mes productivo.'
# MAGIC AS
# MAGIC WITH inicio AS (
# MAGIC     SELECT idpozo, MIN(make_date(anio, mes, 1)) AS primer_mes
# MAGIC     FROM energia.produccion_pozo
# MAGIC     WHERE coalesce(prod_pet, 0) > 0 OR coalesce(prod_gas, 0) > 0
# MAGIC     GROUP BY idpozo
# MAGIC )
# MAGIC SELECT p.idpozo,
# MAGIC        i.primer_mes,
# MAGIC        COUNT(*)                     AS meses_con_dato,
# MAGIC        SUM(coalesce(p.prod_pet, 0)) AS petroleo_12m_m3,
# MAGIC        SUM(coalesce(p.prod_gas, 0)) AS gas_12m_miles_m3
# MAGIC FROM energia.produccion_pozo AS p
# MAGIC INNER JOIN inicio AS i ON i.idpozo = p.idpozo
# MAGIC WHERE make_date(p.anio, p.mes, 1) >= i.primer_mes
# MAGIC   AND make_date(p.anio, p.mes, 1) <  add_months(i.primer_mes, 12)
# MAGIC GROUP BY p.idpozo, i.primer_mes

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 3. Fractura contra producción
# Lee de las dos MLV anteriores: Fabric las refresca en orden de dependencias (lineage).

# CELL ********************

# MAGIC %%sql
# MAGIC CREATE MATERIALIZED LAKE VIEW IF NOT EXISTS mart.fractura_vs_produccion
# MAGIC COMMENT 'Pozos fracturados con su producción del primer año, por rango de etapas.'
# MAGIC AS
# MAGIC SELECT f.idpozo, f.cuenca, f.formacion, f.tipo_reservorio, f.empresa, f.primera_fractura,
# MAGIC        f.operaciones, f.etapas, f.rama_horizontal_m, f.arena_tn, f.agua_m3,
# MAGIC        p.primer_mes, p.meses_con_dato, p.petroleo_12m_m3, p.gas_12m_miles_m3,
# MAGIC        CASE WHEN f.etapas < 20 THEN '01-19'
# MAGIC             WHEN f.etapas < 40 THEN '20-39'
# MAGIC             WHEN f.etapas < 60 THEN '40-59'
# MAGIC             ELSE '60+' END   AS rango_etapas,
# MAGIC        p.meses_con_dato = 12 AS anio_completo
# MAGIC FROM mart.fractura_por_pozo AS f
# MAGIC INNER JOIN mart.produccion_primer_anio AS p ON p.idpozo = f.idpozo

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Lectura: ¿más etapas, más petróleo?
# Solo pozos con el primer año completo.

# CELL ********************

# MAGIC %%sql
# MAGIC SELECT rango_etapas,
# MAGIC        COUNT(*)                         AS pozos,
# MAGIC        ROUND(AVG(etapas), 0)            AS etapas_prom,
# MAGIC        ROUND(AVG(rama_horizontal_m), 0) AS rama_prom_m,
# MAGIC        ROUND(AVG(petroleo_12m_m3), 0)   AS petroleo_12m_prom_m3
# MAGIC FROM mart.fractura_vs_produccion
# MAGIC WHERE anio_completo
# MAGIC GROUP BY rango_etapas
# MAGIC ORDER BY rango_etapas

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }
