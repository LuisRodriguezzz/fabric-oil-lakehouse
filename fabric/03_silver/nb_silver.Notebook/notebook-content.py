# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {}
# META }

# MARKDOWN ********************

# # Silver: el estado vigente de cada fuente, tipado y validado, más su cuarentena
# - **Lee** `lh_bronze.energia.<fuente>`. **Escribe** `lh_silver.energia.<fuente>`,
#   `lh_silver.energia.<fuente>_cuarentena` y suma una fila por fuente a
#   `lh_silver.energia.control_calidad`.
# - **La última foto manda:** cada archivo del portal es una foto completa de lo que cubre.
#   - `padron` (modo `foto`): un archivo con todo. Silver toma la entrega más nueva y reemplaza
#     la tabla entera.
#   - `produccion_pozo` (modo `por_anio`, D32): un archivo por año. Silver lee bronze en
#     streaming (`availableNow` + checkpoint) solo para saber qué años llegaron; de cada año toma
#     la foto de `_version_origen` más alta y la aplica con `MERGE`: actualiza lo que cambió,
#     agrega lo nuevo y borra lo que ya no viene, **solo dentro de ese año**. Con Change Data Feed
#     prendido, cada rectificación queda registrada como los cambios reales y no como el año entero.
#   Una fila corregida toma el valor nuevo y una que el portal sacó deja de estar.
# - **Contrato por fuente:** el tipo de cada columna, la clave y las reglas de calidad.
# - **Nada se tira:** lo que no cumple va a cuarentena, con el texto original y los motivos.
# - **Control antes de publicar:** si la entrega viene vacía o con demasiadas filas en
#   cuarentena, la tabla vigente no se toca y el notebook falla: el pipeline se corta y lo que
#   sigue queda con la última versión buena. La cuarentena sí se escribe, para diagnosticar.
# - **En Azure:** Databricks, con materialized views y expectations (como el proyecto de
#   Databricks), o Synapse Spark con este mismo código.
# - Las funciones se prueban con pytest (`tests/test_silver.py`): el bloque que escribe solo
#   corre dentro de Fabric.


# CELL ********************

import json
from datetime import datetime, timezone

from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F
from pyspark.sql.types import (
    ArrayType,
    DoubleType,
    LongType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

# Columnas de bronze que silver conserva para rastrear cada fila hasta su archivo.
LINAJE = ["ingest_date", "_archivo", "_fuente", "_version_origen", "_cargado_en"]

# Cuántas filas por archivo Parquet al escribir. Sin esto, Spark escribe un archivo por
# partición del último paso (200 por defecto): 431 mil filas quedaban en 200 archivos chicos,
# y muchos archivos chicos hacen lenta la lectura (probado el 10/11).
FILAS_POR_ARCHIVO = 1_000_000

# Reglas que valen para todas las fuentes. Cada regla es una condición SQL que una fila válida
# cumple; si da falso o nulo, la fila va a cuarentena con el nombre de la regla como motivo.
REGLAS_COMUNES = {
    # Un valor que vino escrito y no se pudo convertir a su tipo (por ejemplo "12,5").
    "valores_convierten": "size(_no_convierte) = 0",
    # Dos versiones distintas de la misma clave con la misma fecha: no se sabe cuál vale.
    "sin_versiones_en_conflicto": "_versiones <= 1",
}

CONTRATOS = {
    "produccion_pozo": {
        "modo": "por_anio",
        "clave": ["idpozo", "anio", "mes"],
        # Entre dos declaraciones de la misma clave gana la de fechaingreso más nueva.
        "version": "fechaingreso",
        # Por encima de este porcentaje de filas en cuarentena, silver no se actualiza.
        "umbral_cuarentena_pct": 1.0,
        "tipos": {
            "idempresa": "string",
            "anio": "int",
            "mes": "int",
            "idpozo": "bigint",
            "prod_pet": "double",
            "prod_gas": "double",
            "prod_agua": "double",
            "iny_agua": "double",
            "iny_gas": "double",
            "iny_co2": "double",
            "iny_otro": "double",
            "tef": "double",
            "vida_util": "double",
            "tipoextraccion": "string",
            "tipoestado": "string",
            "tipopozo": "string",
            "observaciones": "string",
            "fechaingreso": "timestamp",
            "rectificado": "boolean",
            "habilitado": "boolean",
            "idusuario": "string",
            "empresa": "string",
            "sigla": "string",
            "formprod": "string",
            "profundidad": "double",
            "formacion": "string",
            "idareapermisoconcesion": "string",
            "areapermisoconcesion": "string",
            "idareayacimiento": "string",
            "areayacimiento": "string",
            "cuenca": "string",
            "provincia": "string",
            "tipo_de_recurso": "string",
            "proyecto": "string",
            "clasificacion": "string",
            "subclasificacion": "string",
            "sub_tipo_recurso": "string",
            "fecha_data": "date",
            "id": "string",
        },
        "reglas": {
            "clave_completa": "idpozo IS NOT NULL AND anio IS NOT NULL AND mes IS NOT NULL",
            "mes_valido": "mes BETWEEN 1 AND 12",
            "empresa_informada": "empresa IS NOT NULL",
            # Horas efectivas en el mes: no pueden pasar de 744 (31 días por 24 horas).
            "tef_en_rango": "tef IS NULL OR tef BETWEEN 0 AND 744",
            "produccion_no_negativa": (
                "coalesce(prod_pet, 0) >= 0 AND coalesce(prod_gas, 0) >= 0 "
                "AND coalesce(prod_agua, 0) >= 0"
            ),
            "inyeccion_no_negativa": (
                "coalesce(iny_agua, 0) >= 0 AND coalesce(iny_gas, 0) >= 0 "
                "AND coalesce(iny_co2, 0) >= 0 AND coalesce(iny_otro, 0) >= 0"
            ),
            "profundidad_y_vida_util_no_negativas": (
                "coalesce(profundidad, 0) >= 0 AND coalesce(vida_util, 0) >= 0"
            ),
            "tipo_de_recurso_conocido": (
                "tipo_de_recurso IS NULL OR tipo_de_recurso IN "
                "('CONVENCIONAL', 'NO CONVENCIONAL', 'SIN RESERVORIO', 'NO DISCRIMINADO')"
            ),
            # El MERGE borra lo que no vino solo dentro del año del archivo: si un archivo trajera
            # filas de otro año, esas filas romperían ese supuesto. La fuente termina en el año.
            "anio_del_archivo": "_fuente IS NULL OR right(_fuente, 4) = cast(anio AS string)",
        },
    },
    "padron": {
        "modo": "foto",
        "clave": ["idpozo"],
        # El archivo no trae fecha de carga por fila: dos filas distintas del mismo pozo son
        # un conflicto.
        "version": None,
        "umbral_cuarentena_pct": 1.0,
        "tipos": {"idpozo": "bigint", "anio": "int", "mes": "int"},
        "reglas": {
            "clave_completa": "idpozo IS NOT NULL",
            "primera_produccion_completa": "anio IS NOT NULL AND mes IS NOT NULL",
            "mes_valido": "mes BETWEEN 1 AND 12",
        },
    },
}

# Una fila por fuente y corrida en control_calidad.
ESQUEMA_CONTROL = StructType([
    StructField("fuente", StringType()),
    StructField("entrega", StringType()),
    StructField("filas_vigentes", LongType()),
    StructField("filas_cuarentena", LongType()),
    StructField("porcentaje_cuarentena", DoubleType()),
    StructField("umbral_porcentaje", DoubleType()),
    StructField("motivos", StringType()),
    StructField("columnas_fuera_de_contrato", ArrayType(StringType())),
    StructField("resultado", StringType()),
    StructField("evaluado_en", TimestampType()),
])

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

def ultima_entrega(bronze: DataFrame) -> DataFrame:
    """Solo las filas del archivo más nuevo: la carpeta de fecha más nueva y, si hubiera dos
    archivos el mismo día, el nombre mayor, para que el resultado sea siempre el mismo."""
    entregas = bronze.select("ingest_date", "_archivo").distinct()
    orden = Window.orderBy(F.desc("ingest_date"), F.desc("_archivo"))
    vigente = entregas.withColumn("_n", F.row_number().over(orden)).filter("_n = 1")
    return bronze.join(vigente.select("_archivo"), "_archivo", "left_semi")


def ultima_foto_por_fuente(bronze: DataFrame) -> DataFrame:
    """De cada fuente (cada año de producción), solo las filas de su foto más nueva.

    Ordena por `_version_origen`, la fecha en que el portal publicó el archivo (tiempo del origen),
    y no por cuándo se cargó: si se recarga un archivo viejo, no le gana al nuevo. Si hubiera dos
    archivos con la misma versión, desempata el nombre, para que el resultado sea siempre el mismo.
    """
    entregas = bronze.select("_fuente", "_version_origen", "_archivo").distinct()
    orden = Window.partitionBy("_fuente").orderBy(F.desc("_version_origen"), F.desc("_archivo"))
    vigente = entregas.withColumn("_n", F.row_number().over(orden)).filter("_n = 1")
    return bronze.join(vigente.select("_archivo"), "_archivo", "left_semi")


def anio_de(fuente: str) -> int:
    """produccion_pozo_2006 -> 2006: el año que cubre el archivo de esa fuente."""
    return int(fuente[-4:])


def con_huella(filas: DataFrame, columnas: list[str]) -> DataFrame:
    """Agrega `_huella`: un hash de los datos de la fila (sin el linaje).

    El MERGE actualiza una fila solo si su huella cambió. Así una foto nueva que repite el mismo
    valor no cuenta como cambio, y el Change Data Feed registra solo lo que de verdad cambió.
    """
    return filas.withColumn("_huella", F.sha2(F.to_json(F.struct(*[F.col(c) for c in columnas])), 256))


def tipar(filas: DataFrame, tipos: dict[str, str]) -> DataFrame:
    """Cada columna a su tipo, sin perder lo que no convierte.

    Una columna del contrato que no vino en el archivo queda nula (y las reglas deciden). Con
    `try_cast` un valor que no convierte da nulo en vez de fallar; para que no pase callado, si
    el texto original no estaba vacío, el nombre de la columna se anota en `_no_convierte`. El
    texto original de toda la fila queda en `_original`, para la cuarentena.
    """
    # Un linaje que la tabla de bronze todavía no tiene (versiones viejas) también queda nulo.
    faltan = [c for c in [*tipos, *LINAJE] if c not in filas.columns]
    filas = filas.select("*", *[F.lit(None).cast("string").alias(c) for c in faltan])
    convertidas = {
        c: F.expr(f"try_cast(`{c}` AS {t})") for c, t in tipos.items() if t != "string"
    }
    tipadas = [convertidas.get(c, F.col(c)).alias(c) for c in tipos]
    no_convierte = F.filter(
        F.array(*[F.when(F.col(c).isNotNull() & v.isNull(), F.lit(c)) for c, v in convertidas.items()]),
        lambda nombre: nombre.isNotNull(),
    )
    original = F.struct(*[F.col(c) for c in tipos])
    return filas.select(*tipadas, no_convierte.alias("_no_convierte"), original.alias("_original"), *LINAJE)


def una_version_por_clave(filas: DataFrame, clave: list[str], version: str | None, columnas: list[str]) -> DataFrame:
    """Una sola fila por clave, sin elegir al azar.

    1. Si la fuente tiene columna de versión, queda la más nueva de cada clave (una rectificativa
       reemplaza a la original). Una fila con un valor que no convirtió nunca se descarta acá:
       tiene que llegar a la cuarentena.
    2. Las copias idénticas quedan en una.
    3. Si siguen quedando versiones distintas, se cuentan en `_versiones` y la regla
       `sin_versiones_en_conflicto` las manda a cuarentena.
    """
    por_clave = Window.partitionBy(*clave)
    convierte = F.size("_no_convierte") == 0
    if version:
        mas_nueva = F.col(version).eqNullSafe(F.max(version).over(por_clave))
        filas = filas.withColumn("_mas_nueva", mas_nueva).filter(F.col("_mas_nueva") | ~convierte).drop("_mas_nueva")
    filas = filas.dropDuplicates(columnas)
    return filas.withColumn("_versiones", F.count(F.when(convierte, 1)).over(por_clave))


def sin_nulos(reglas: dict[str, str]) -> dict[str, str]:
    """Cada regla con nulo cuenta como falla: en SQL, `NULL BETWEEN 0 AND 744` no es ni
    verdadero ni falso."""
    return {nombre: f"coalesce(({condicion}), false)" for nombre, condicion in reglas.items()}


def marcar(filas: DataFrame, reglas: dict[str, str]) -> DataFrame:
    """Agrega `_motivos`: los nombres de las reglas que la fila no cumple (vacío si está bien)."""
    fallas = [F.when(~F.expr(c), F.lit(n)) for n, c in sin_nulos(reglas).items()]
    return filas.withColumn("_motivos", F.filter(F.array(*fallas), lambda n: n.isNotNull()))


def entrega_vigente(bronze: DataFrame, contrato: dict) -> DataFrame:
    """Las filas de bronze que valen hoy: la última foto (modo foto) o la de cada año (por_anio)."""
    if contrato["modo"] == "por_anio":
        return ultima_foto_por_fuente(bronze)
    return ultima_entrega(bronze)


def validar(bronze: DataFrame, contrato: dict) -> DataFrame:
    """Bronze -> entrega vigente -> tipos -> una versión por clave -> motivos."""
    columnas = list(contrato["tipos"])
    filas = tipar(entrega_vigente(bronze, contrato), contrato["tipos"])
    filas = una_version_por_clave(filas, contrato["clave"], contrato["version"], columnas)
    return marcar(filas, {**contrato["reglas"], **REGLAS_COMUNES})


def vigentes(validada: DataFrame, contrato: dict) -> DataFrame:
    return validada.filter(F.size("_motivos") == 0).select(*contrato["tipos"], *LINAJE)


def cuarentena(validada: DataFrame) -> DataFrame:
    return validada.filter(F.size("_motivos") > 0).select(
        "_motivos", "_no_convierte", "_original.*", *LINAJE
    )


def archivos_para(filas: int) -> int:
    """Cuántos archivos escribir: uno cada FILAS_POR_ARCHIVO filas, y al menos uno."""
    return max(1, -(-filas // FILAS_POR_ARCHIVO))


def columnas_fuera_de_contrato(bronze: DataFrame, contrato: dict) -> list[str]:
    """Columnas con datos en la entrega vigente que el contrato no conoce: alguien tiene que
    decidir si se suman. Silver no las usa hasta que entren al contrato."""
    extra = [c for c in bronze.columns if c not in contrato["tipos"] and c not in LINAJE]
    if not extra:
        return []
    cuentas = entrega_vigente(bronze, contrato).agg(*[F.count(F.col(c)).alias(c) for c in extra]).first()
    return sorted(c for c in extra if cuentas[c] > 0)


def controlar(fuente: str, validada: DataFrame, contrato: dict, extra: list[str], cuando: datetime) -> dict:
    """Una fila de control: cuántas vigentes y en cuarentena, por qué motivos, y si pasa."""
    cuentas = validada.agg(
        F.sum(F.when(F.size("_motivos") == 0, 1).otherwise(0)).alias("vigentes"),
        F.sum(F.when(F.size("_motivos") > 0, 1).otherwise(0)).alias("cuarentena"),
        F.max("_archivo").alias("entrega"),
    ).first()
    vigentes_n, cuarentena_n = int(cuentas["vigentes"] or 0), int(cuentas["cuarentena"] or 0)
    total = vigentes_n + cuarentena_n
    porcentaje = round(cuarentena_n * 100 / total, 4) if total else 0.0
    motivos = {
        r["motivo"]: r["filas"]
        for r in validada.select(F.explode("_motivos").alias("motivo")).groupBy("motivo")
        .agg(F.count(F.lit(1)).alias("filas")).collect()
    }
    if vigentes_n == 0:
        resultado = "falla: entrega sin filas vigentes"
    elif porcentaje > contrato["umbral_cuarentena_pct"]:
        resultado = "falla: cuarentena sobre el umbral"
    else:
        resultado = "ok"
    return {
        "fuente": fuente,
        "entrega": cuentas["entrega"],
        "filas_vigentes": vigentes_n,
        "filas_cuarentena": cuarentena_n,
        "porcentaje_cuarentena": float(porcentaje),
        "umbral_porcentaje": float(contrato["umbral_cuarentena_pct"]),
        "motivos": json.dumps(motivos, ensure_ascii=False, sort_keys=True),
        "columnas_fuera_de_contrato": extra,
        "resultado": resultado,
        "evaluado_en": cuando,
    }

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Lo que escribe: solo corre dentro de Fabric. Cuando pytest importa este archivo, __name__ no
# es "__main__" y este bloque no se ejecuta.
if __name__ == "__main__":
    from delta.tables import DeltaTable

    WORKSPACE = notebookutils.runtime.context["currentWorkspaceName"]  # noqa: F821
    ONELAKE = f"abfss://{WORKSPACE}@onelake.dfs.fabric.microsoft.com"
    BRONZE = f"{ONELAKE}/lh_bronze.Lakehouse/Tables/energia"
    SILVER = f"{ONELAKE}/lh_silver.Lakehouse/Tables/energia"
    CHECKPOINTS = f"{ONELAKE}/lh_silver.Lakehouse/Files/_checkpoints"
    cuando = datetime.now(timezone.utc).replace(tzinfo=None)

    def informar(control: dict) -> None:
        print(f"{control['fuente']}: {control['filas_vigentes']} vigentes, {control['filas_cuarentena']} "
              f"en cuarentena ({control['porcentaje_cuarentena']} %) -> {control['resultado']}")

    def guardar_controles(controles: list[dict]) -> None:
        (spark.createDataFrame(controles, ESQUEMA_CONTROL)  # noqa: F821
         .write.format("delta").mode("append").save(f"{SILVER}/control_calidad"))

    def fallar_si_hace_falta(controles: list[dict]) -> None:
        fallas = [c for c in controles if c["resultado"] != "ok"]
        if fallas:
            raise RuntimeError(
                "Silver no se actualizó para: "
                + "; ".join(f"{c['fuente']} ({c['resultado']}, motivos {c['motivos']})" for c in fallas)
            )

    def foto(fuente: str, contrato: dict) -> None:
        """Modo foto: la última entrega reemplaza la tabla entera."""
        bronze = spark.read.format("delta").load(f"{BRONZE}/{fuente}")  # noqa: F821
        validada = validar(bronze, contrato).persist()
        control = controlar(fuente, validada, contrato, columnas_fuera_de_contrato(bronze, contrato), cuando)
        informar(control)
        # La cuarentena se escribe siempre, aunque la entrega falle el control: es lo que alguien
        # tiene que mirar para entender qué pasó. Cada fila trae su _archivo de origen.
        (cuarentena(validada).repartition(archivos_para(control["filas_cuarentena"]))
         .write.format("delta").mode("overwrite")
         .option("overwriteSchema", True).save(f"{SILVER}/{fuente}_cuarentena"))
        if control["resultado"] == "ok":
            (vigentes(validada, contrato).repartition(archivos_para(control["filas_vigentes"]))
             .write.format("delta").mode("overwrite")
             .option("overwriteSchema", True).save(f"{SILVER}/{fuente}"))
        validada.unpersist()
        guardar_controles([control])
        fallar_si_hace_falta([control])

    def crear_si_no_existe(ruta: str, ejemplo: DataFrame) -> None:
        """La tabla vacía con el esquema de silver y Change Data Feed prendido desde el inicio:
        el CDF solo registra lo que pasa después de prenderlo."""
        if not DeltaTable.isDeltaTable(spark, ruta):  # noqa: F821
            ejemplo.limit(0).write.format("delta").save(ruta)
            spark.sql(f"ALTER TABLE delta.`{ruta}` SET TBLPROPERTIES (delta.enableChangeDataFeed = true)")  # noqa: F821

    def por_anio(dataset: str, contrato: dict) -> None:
        """Modo por_anio: el stream dice qué años llegaron; cada año se aplica con MERGE."""
        origen = f"{BRONZE}/{dataset}"
        destino = f"{SILVER}/{dataset}"
        columnas = list(contrato["tipos"])
        clave = " AND ".join(f"t.{c} = s.{c}" for c in contrato["clave"])

        def procesar(tanda: DataFrame, numero: int) -> None:
            fuentes = sorted(r["_fuente"] for r in tanda.select("_fuente").distinct().collect() if r["_fuente"])
            if not fuentes:
                return
            # La tanda solo avisa qué años llegaron. La foto se lee entera de bronze, filtrada por
            # la partición: aunque el stream partiera un archivo en dos tandas, cada año se aplica
            # completo, y si llegó una foto vieja tarde, no le gana a la más nueva.
            bronze = spark.read.format("delta").load(origen).filter(F.col("_fuente").isin(fuentes))  # noqa: F821
            validada = validar(bronze, contrato).persist()
            extra = columnas_fuera_de_contrato(bronze, contrato)
            controles, aprobadas = [], []
            for fuente in fuentes:
                del_anio = validada.filter(F.col("_fuente") == fuente)
                control = controlar(fuente, del_anio, contrato, extra, cuando)
                informar(control)
                controles.append(control)
                # La cuarentena de ese año se reemplaza: queda la de su foto vigente.
                escritura = cuarentena(del_anio).write.format("delta").option("mergeSchema", True)
                if DeltaTable.isDeltaTable(spark, f"{destino}_cuarentena"):  # noqa: F821
                    escritura = escritura.mode("overwrite").option("replaceWhere", f"_fuente = '{fuente}'")
                escritura.save(f"{destino}_cuarentena")
                if control["resultado"] == "ok":
                    aprobadas.append(fuente)
            if aprobadas:
                nuevas = con_huella(vigentes(validada, contrato), columnas).filter(
                    F.col("_fuente").isin(aprobadas)
                ).withColumn("_actualizado_en", F.current_timestamp())
                crear_si_no_existe(destino, nuevas)
                anios = ", ".join(str(anio_de(f)) for f in aprobadas)
                (DeltaTable.forPath(spark, destino).alias("t")  # noqa: F821
                 .merge(nuevas.alias("s"), clave)
                 # Solo si cambió el dato: una foto que repite el valor no es un cambio.
                 .whenMatchedUpdateAll(condition="t._huella <> s._huella")
                 .whenNotMatchedInsertAll()
                 # Lo que el portal sacó, solo dentro de los años de esta tanda: sin el filtro por
                 # año, el MERGE borraría los otros 20 años, que no vienen en estos archivos.
                 .whenNotMatchedBySourceDelete(condition=f"t.anio IN ({anios})")
                 .execute())
                print(f"  tanda {numero}: MERGE de {', '.join(aprobadas)}")
            validada.unpersist()
            guardar_controles(controles)
            # Si un año falla, la tanda falla: el checkpoint no avanza y la próxima corrida la
            # repite. Los años que pasaron se vuelven a aplicar igual, y el MERGE da lo mismo.
            fallar_si_hace_falta(controles)

        consulta = (
            spark.readStream.format("delta")  # noqa: F821
            # La retención de bronze borra versiones viejas: esos commits no son datos nuevos.
            .option("skipChangeCommits", True)
            .load(origen)
            .select("_fuente")
            .writeStream.foreachBatch(procesar)
            .option("checkpointLocation", f"{CHECKPOINTS}/silver_{dataset}")
            .trigger(availableNow=True)
            .start()
        )
        consulta.awaitTermination()
        if DeltaTable.isDeltaTable(spark, destino):  # noqa: F821
            print(f"energia.{dataset}: {spark.read.format('delta').load(destino).count()} filas vigentes")  # noqa: F821

    # Cada fuente se procesa aunque otra falle; al final, si alguna falló, el notebook falla y el
    # pipeline se corta antes de gold.
    errores = []
    for fuente, contrato in CONTRATOS.items():
        try:
            por_anio(fuente, contrato) if contrato["modo"] == "por_anio" else foto(fuente, contrato)
        except Exception as error:  # noqa: BLE001
            errores.append(f"{fuente}: {error}")
    if errores:
        raise RuntimeError(" | ".join(errores))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
