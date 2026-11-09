# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {}
# META }

# MARKDOWN ********************

# # Bronze: cada entrega de landing, tal como llegó, en una tabla Delta
# # - **Lee** `lh_bronze/Files/landing/<fuente>/ingest_date=AAAA-MM-DD/*.csv`.
# - **Escribe** `lh_bronze/Tables/<fuente>`: todas las columnas como texto, más el linaje
#   (`_archivo`, `ingest_date`, `_cargado_en`). Tipar y validar es trabajo de silver.
# - **Cada archivo entra una sola vez:** Structured Streaming con un checkpoint y
#   `trigger(availableNow=True)` procesa solo lo nuevo y termina. Volver a correrlo no duplica.
# - **Sirve en dev y en prod sin cambios:** arma las rutas con el nombre del workspace donde corre.
# # En Azure, lo mismo se hace en Databricks con Auto Loader, o en Synapse Spark con este mismo código.

# CELL ********************

from pyspark.sql import functions as F
from pyspark.sql.types import StringType, StructField, StructType

FUENTES = ["produccion", "padron"]

# El workspace donde corre el notebook: oil-dev o oil-prod. Así no hay IDs fijos en el código.
WORKSPACE = notebookutils.runtime.context["currentWorkspaceName"]  # noqa: F821
BRONZE = f"abfss://{WORKSPACE}@onelake.dfs.fabric.microsoft.com/lh_bronze.Lakehouse"

# Algunos CSV del portal traen la marca BOM pegada al nombre de la primera columna.
BOM = "﻿"

print(f"Workspace: {WORKSPACE}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

def esquema_de_texto(origen: str) -> StructType:
    """Las columnas del encabezado, todas como texto, más ingest_date (sale de la carpeta).

    Un stream de archivos necesita el esquema de antemano. Se toma del encabezado de lo que ya
    está en landing; con enforceSchema (el valor por defecto) Spark lee por posición, así que los
    nombres se pueden limpiar del BOM.
    """
    encabezado = spark.read.option("header", True).csv(origen).schema  # noqa: F821
    columnas = [c.name.lstrip(BOM) for c in encabezado if c.name != "ingest_date"]
    return StructType(
        [StructField(c, StringType()) for c in columnas] + [StructField("ingest_date", StringType())]
    )


def ingerir(fuente: str) -> None:
    origen = f"{BRONZE}/Files/landing/{fuente}/"
    destino = f"{BRONZE}/Tables/{fuente}"
    checkpoint = f"{BRONZE}/Files/_checkpoints/bronze_{fuente}"

    consulta = (
        spark.readStream.schema(esquema_de_texto(origen))  # noqa: F821
        .option("header", True)
        .csv(origen)
        .withColumn("_archivo", F.input_file_name())
        .withColumn("_cargado_en", F.current_timestamp())
        .writeStream.format("delta")
        .option("checkpointLocation", checkpoint)
        .trigger(availableNow=True)
        .start(destino)
    )
    consulta.awaitTermination()
    filas = spark.read.format("delta").load(destino).count()  # noqa: F821
    print(f"bronze.{fuente}: {filas} filas en total")


for fuente in FUENTES:
    ingerir(fuente)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
