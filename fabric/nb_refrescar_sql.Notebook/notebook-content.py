# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {}
# META }

# CELL ********************

# nb_refrescar_sql: refresca el SQL endpoint de los lakehouses que se consultan por SQL.
# Lo busca por el nombre del lakehouse en el workspace donde corre: no guarda IDs,
# así el mismo código sirve en oil-dev y en oil-prod (D11).
from sempy.fabric.sql_endpoint import refresh_sql_endpoint_metadata

LAKEHOUSES = ["lh_silver"]

for lh in LAKEHOUSES:
    estado = refresh_sql_endpoint_metadata(warehouse=lh, warehouse_type="Lakehouse")
    print(lh)
    print(estado.to_string())
    columna = next((c for c in estado.columns if c.lower() == "status"), None)
    if columna and (estado[columna] == "Failure").any():
        raise RuntimeError(f"{lh}: falló el refresco de alguna tabla")
    print(f"{lh}: refrescado")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
