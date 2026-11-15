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
# - **Lee** `lh_bronze/Files/landing/<fuente>/ingest_date=AAAA-MM-DD/<archivo>.csv`.
# - **Escribe** `lh_bronze.energia.<fuente>` (`Tables/energia/<fuente>`): todas las columnas como
#   texto, más el linaje (`_archivo`, `ingest_date`, `_version_origen`, `_cargado_en`). El schema `energia` es el
#   sistema de origen: el portal de la Secretaría de Energía.
# - **Acepta todo, sin mezclar columnas:** cada archivo se lee con su propio encabezado, así las
#   columnas se asignan por nombre. Una columna nueva se suma a la tabla (las filas anteriores
#   quedan en `null`); una que falta queda en `null`. Qué columnas valen lo decide silver (D15).
# - **Cada archivo entra una sola vez:** un stream de archivos con checkpoint y
#   `trigger(availableNow=True)` encuentra lo nuevo y termina. Cada escritura lleva el número de
#   tanda, así un reintento no escribe dos veces.
# - **Sirve en dev y en prod sin cambios:** arma las rutas con el nombre del workspace donde corre.
# - **En Azure:** en Databricks, Auto Loader con `addNewColumns`; en Synapse Spark, este código.


# CELL ********************

import re
import uuid
from functools import reduce

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import BinaryType, LongType, StringType, StructField, StructType, TimestampType

# Datasets: carpetas de landing y tablas de bronze. produccion_pozo junta los 21 años (D32);
# produccion (solo no convencional) quedó apagada y su tabla no recibe más archivos.
FUENTES = ("produccion_pozo", "padron")
SCHEMA = "energia"

# El workspace donde corre el notebook: oil-dev o oil-prod. Así no hay IDs fijos en el código.
WORKSPACE = notebookutils.runtime.context["currentWorkspaceName"]  # noqa: F821
BRONZE = f"abfss://{WORKSPACE}@onelake.dfs.fabric.microsoft.com/lh_bronze.Lakehouse"

# Marca de orden de bytes que traen algunos CSV del portal pegada a la primera columna.
BOM = "﻿"
FECHA_DE_INGESTA = re.compile(r"/ingest_date=(\d{4}-\d{2}-\d{2})/")
# El pipeline nombra cada archivo <fuente>_<última modificación en el portal>_<tamaño>.csv.
# Esa fecha es la versión del origen: con ella silver elige la foto más nueva de cada año (D32).
VERSION_DE_ORIGEN = re.compile(r"_(\d{8}T\d{6})_\d+\.csv$")

# Un stream necesita el esquema por adelantado; este es el fijo del lector binaryFile.
ARCHIVOS = StructType([
    StructField("path", StringType()),
    StructField("modificationTime", TimestampType()),
    StructField("length", LongType()),
    StructField("content", BinaryType()),
])

print(f"Workspace: {WORKSPACE}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

def leer_archivo(ruta: str) -> DataFrame:
    """Un CSV con su propio encabezado: columnas por nombre, todas como texto, más el linaje.

    Leer varios CSV juntos no sirve: Spark toma el encabezado de uno y asigna el resto por
    posición. Por eso cada archivo se lee solo.
    """
    datos = spark.read.option("header", True).csv(ruta)  # noqa: F821  (sin inferSchema: texto)
    datos = datos.toDF(*[c.lstrip(BOM).strip() for c in datos.columns])
    fecha = FECHA_DE_INGESTA.search(ruta)
    version = VERSION_DE_ORIGEN.search(ruta)
    return (
        datos.withColumn("_archivo", F.lit(ruta))
        .withColumn("ingest_date", F.lit(fecha.group(1) if fecha else None))
        .withColumn("_version_origen", F.lit(version.group(1) if version else None))
        .withColumn("_cargado_en", F.current_timestamp())
    )


def id_de_escritura(checkpoint: str, fuente: str) -> str:
    """Identifica las escrituras de este checkpoint para que Delta descarte un reintento.

    Vive dentro del checkpoint: si alguien lo borra para reprocesar todo, el id cambia y las
    tandas, que vuelven a empezar en 0, no se confunden con las viejas.
    """
    marca = f"{checkpoint}/_id_escritura"
    if not notebookutils.fs.exists(marca):  # noqa: F821
        notebookutils.fs.put(marca, f"bronze_{fuente}_{uuid.uuid4()}", True)  # noqa: F821
    return notebookutils.fs.head(marca, 200).strip()  # noqa: F821


def escribir_tanda(fuente: str, destino: str, id_app: str):
    def escribir(tanda: DataFrame, numero: int) -> None:
        rutas = sorted(fila.path for fila in tanda.collect())
        if not rutas:
            return
        datos = reduce(
            lambda a, b: a.unionByName(b, allowMissingColumns=True),
            [leer_archivo(ruta) for ruta in rutas],
        )
        (
            datos.write.format("delta")
            .mode("append")
            .option("mergeSchema", True)  # una columna nueva se suma a la tabla
            .option("txnAppId", id_app)  # si esta tanda ya se escribió, Delta no la repite
            .option("txnVersion", numero)
            .save(destino)
        )
        print(f"  tanda {numero}: {len(rutas)} archivo(s) -> {fuente}")

    return escribir


def ingerir(fuente: str) -> None:
    origen = f"{BRONZE}/Files/landing/{fuente}/"
    destino = f"{BRONZE}/Tables/{SCHEMA}/{fuente}"
    checkpoint = f"{BRONZE}/Files/_checkpoints/bronze_{fuente}"

    consulta = (
        # El stream solo descubre archivos nuevos: se pide la ruta, no el contenido.
        spark.readStream.format("binaryFile")  # noqa: F821
        .schema(ARCHIVOS)
        .option("pathGlobFilter", "*.csv")
        .option("recursiveFileLookup", True)
        .load(origen)
        .select("path")
        .writeStream.foreachBatch(escribir_tanda(fuente, destino, id_de_escritura(checkpoint, fuente)))
        .option("checkpointLocation", checkpoint)
        .trigger(availableNow=True)
        .start()
    )
    consulta.awaitTermination()
    tabla = spark.read.format("delta").load(destino)  # noqa: F821
    print(f"{SCHEMA}.{fuente}: {tabla.count()} filas, {len(tabla.columns)} columnas")


for fuente in FUENTES:
    ingerir(fuente)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
