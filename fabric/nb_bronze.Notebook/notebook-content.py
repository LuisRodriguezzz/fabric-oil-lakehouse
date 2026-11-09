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
# - **Lee** `lh_bronze/Files/landing/<fuente>/ingest_date=AAAA-MM-DD/*.csv`.
# - **Escribe** `lh_bronze/Tables/<fuente>`: todas las columnas como texto, más el linaje
#   (`_archivo`, `ingest_date`, `_cargado_en`). Tipar y validar es trabajo de silver.
# - **Contrato de columnas:** cada fuente declara su encabezado. Si un archivo llega con otras columnas u otro orden, la carga falla y nombra el archivo (`enforceSchema=False`), en vez de mezclar datos en silencio.
# - **Cada archivo entra una sola vez:** Structured Streaming con un checkpoint y
#   `trigger(availableNow=True)` procesa solo lo nuevo y termina. Volver a correrlo no duplica.
# - **Sirve en dev y en prod sin cambios:** arma las rutas con el nombre del workspace donde corre.
# - **En Azure:** lo mismo se hace en Databricks con Auto Loader, o en Synapse Spark con este código.

# CELL ********************

from pyspark.sql import functions as F
from pyspark.sql.types import StringType, StructField, StructType

# El contrato de cada fuente: el encabezado que esperamos, columna por columna y en orden.
# Cambiar un contrato es un commit revisado, no algo que pasa solo cuando cambia la fuente.
CONTRATOS = {
    "produccion": (
        "idempresa,anio,mes,idpozo,prod_pet,prod_gas,prod_agua,iny_agua,iny_gas,iny_co2,iny_otro,"
        "tef,vida_util,tipoextraccion,tipoestado,tipopozo,observaciones,fechaingreso,rectificado,"
        "habilitado,idusuario,empresa,sigla,formprod,profundidad,formacion,idareapermisoconcesion,"
        "areapermisoconcesion,idareayacimiento,areayacimiento,cuenca,provincia,tipo_de_recurso,"
        "proyecto,clasificacion,subclasificacion,sub_tipo_recurso,fecha_data,id"
    ).split(","),
    "padron": "idpozo,anio,mes".split(","),
}

# El workspace donde corre el notebook: oil-dev o oil-prod. Así no hay IDs fijos en el código.
WORKSPACE = notebookutils.runtime.context["currentWorkspaceName"]  # noqa: F821
BRONZE = f"abfss://{WORKSPACE}@onelake.dfs.fabric.microsoft.com/lh_bronze.Lakehouse"

print(f"Workspace: {WORKSPACE}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

def esquema(fuente: str) -> StructType:
    """Las columnas del contrato, todas como texto, más ingest_date (sale de la carpeta)."""
    return StructType(
        [StructField(c, StringType()) for c in CONTRATOS[fuente]]
        + [StructField("ingest_date", StringType())]
    )


def ingerir(fuente: str) -> None:
    origen = f"{BRONZE}/Files/landing/{fuente}/"
    destino = f"{BRONZE}/Tables/{fuente}"
    checkpoint = f"{BRONZE}/Files/_checkpoints/bronze_{fuente}"

    consulta = (
        spark.readStream.schema(esquema(fuente))  # noqa: F821
        .option("header", True)
        # Por defecto Spark ignora el encabezado y asigna las columnas por posición: si la fuente
        # invierte dos columnas, las mezcla sin avisar. Así compara cada encabezado con el contrato.
        .option("enforceSchema", False)
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


for fuente in CONTRATOS:
    ingerir(fuente)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
