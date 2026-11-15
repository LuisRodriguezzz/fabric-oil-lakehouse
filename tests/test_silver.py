"""Tests de silver (fabric/nb_silver.Notebook): cada paso con tablitas de pocas filas.

Son los casos del proyecto de Databricks, adaptados a Fabric: acá cada archivo del portal es una
foto completa de la fuente, y bronze no tiene _rescued_data.
"""

from pyspark.sql.types import StringType, StructField, StructType

CARPETA = "abfss://ws@onelake.dfs.fabric.microsoft.com/lh_bronze.Lakehouse/Files/landing/produccion"

# Un contrato chico para probar los pasos sin escribir las 39 columnas.
TIPOS = {
    "idpozo": "bigint",
    "anio": "int",
    "mes": "int",
    "prod_pet": "double",
    "prod_gas": "double",
    "fechaingreso": "timestamp",
}
CLAVE = ["idpozo", "anio", "mes"]


def archivo(fecha: str, nombre: str = "produccion_20261022T210055_148923474.csv") -> str:
    return f"{CARPETA}/ingest_date={fecha}/{nombre}"


def fila(**valores) -> dict:
    """Una declaración válida del pozo 1 en enero de 2024; los argumentos cambian lo necesario."""
    base = {
        "idpozo": "1",
        "anio": "2024",
        "mes": "1",
        "prod_pet": "10.5",
        "prod_gas": "20.0",
        "fechaingreso": "2024-02-01 10:00:00",
        "_archivo": archivo("2026-11-11"),
    }
    return {**base, **valores}


def bronze(spark, silver, filas: list[dict], columnas: list[str]):
    """Un DataFrame como bronze: las columnas pedidas más el linaje, todo como texto."""
    todas = [*columnas, *silver.LINAJE]
    datos = []
    for f in filas:
        f = dict(f)
        f.setdefault("ingest_date", f["_archivo"].split("ingest_date=")[1].split("/")[0])
        datos.append(tuple(f.get(c) for c in todas))
    return spark.createDataFrame(datos, StructType([StructField(c, StringType()) for c in todas]))


def hasta_versiones(spark, silver, filas):
    df = silver.tipar(silver.ultima_entrega(bronze(spark, silver, filas, list(TIPOS))), TIPOS)
    return silver.una_version_por_clave(df, CLAVE, "fechaingreso", list(TIPOS))


# ultima_entrega


def test_queda_solo_la_entrega_mas_nueva(spark, silver):
    vieja, nueva = archivo("2026-11-09"), archivo("2026-11-11")
    filas = [fila(_archivo=vieja), fila(_archivo=vieja, mes="2"), fila(_archivo=nueva)]

    resultado = silver.ultima_entrega(bronze(spark, silver, filas, list(TIPOS))).collect()

    assert [r["_archivo"] for r in resultado] == [nueva]  # la fila de febrero solo estaba en la vieja


def test_dos_archivos_el_mismo_dia_desempata_el_nombre(spark, silver):
    a = archivo("2026-11-11", "padron_20261110T090243_1172135.csv")
    b = archivo("2026-11-11", "padron_20261111T120000_1172200.csv")
    filas = [fila(_archivo=a), fila(_archivo=b, idpozo="2")]

    resultado = silver.ultima_entrega(bronze(spark, silver, filas, list(TIPOS))).collect()

    assert [r["idpozo"] for r in resultado] == ["2"]


# ultima_foto_por_fuente (producción completa, un archivo por año)


def foto_de(fuente: str, version: str, fecha: str = "2026-11-16") -> dict:
    """Linaje de un archivo de producción por año, como lo escribe bronze."""
    nombre = f"{fuente}_{version}_300000000.csv"
    return {"_archivo": archivo(fecha, nombre), "_fuente": fuente, "_version_origen": version}


def test_de_cada_anio_queda_su_foto_mas_nueva(spark, silver):
    v1_2006 = foto_de("produccion_pozo_2006", "20261003T100000")
    v2_2006 = foto_de("produccion_pozo_2006", "20261103T100000")
    v1_2024 = foto_de("produccion_pozo_2024", "20261015T100000")
    filas = [
        fila(anio="2006", **v1_2006),
        fila(anio="2006", mes="2", **v1_2006),  # la rectificación de noviembre la sacó
        fila(anio="2006", **v2_2006),
        fila(anio="2024", **v1_2024),
    ]

    resultado = silver.ultima_foto_por_fuente(bronze(spark, silver, filas, list(TIPOS))).collect()

    assert sorted((r["_fuente"], r["_version_origen"], r["mes"]) for r in resultado) == [
        ("produccion_pozo_2006", "20261103T100000", "1"),
        ("produccion_pozo_2024", "20261015T100000", "1"),
    ]


def test_una_foto_vieja_cargada_despues_no_le_gana_a_la_nueva(spark, silver):
    # La versión de noviembre llegó primero; la de octubre se recargó después (otra ingest_date).
    nueva = foto_de("produccion_pozo_2006", "20261103T100000", fecha="2026-11-03")
    vieja = foto_de("produccion_pozo_2006", "20261003T100000", fecha="2026-11-20")
    filas = [fila(anio="2006", prod_pet="1", **nueva), fila(anio="2006", prod_pet="9", **vieja)]

    resultado = silver.ultima_foto_por_fuente(bronze(spark, silver, filas, list(TIPOS))).collect()

    assert [r["prod_pet"] for r in resultado] == ["1"]


def test_el_anio_sale_del_nombre_de_la_fuente(silver):
    assert silver.anio_de("produccion_pozo_2006") == 2006


def test_una_fila_de_otro_anio_que_el_archivo_va_a_cuarentena(spark, silver):
    contrato = silver.CONTRATOS["produccion_pozo"]
    columnas = list(contrato["tipos"])
    base = {c: None for c in columnas} | {
        "idpozo": "1", "mes": "1", "empresa": "YPF S.A.", **foto_de("produccion_pozo_2006", "20261103T100000"),
    }
    filas = [base | {"anio": "2006"}, base | {"idpozo": "2", "anio": "2007"}]

    r = {x["idpozo"]: x["_motivos"] for x in silver.validar(bronze(spark, silver, filas, columnas), contrato).collect()}

    assert r[1] == [] and r[2] == ["anio_del_archivo"]


def test_la_huella_cambia_con_el_dato_y_no_con_el_linaje(spark, silver):
    a = foto_de("produccion_pozo_2006", "20261003T100000")
    b = foto_de("produccion_pozo_2006", "20261103T100000")
    df = bronze(spark, silver, [fila(**a), fila(**b), fila(prod_pet="99", **b)], list(TIPOS))

    h = [r["_huella"] for r in silver.con_huella(df, list(TIPOS)).collect()]

    assert h[0] == h[1] and h[0] != h[2]


# tipar


def test_un_valor_que_no_convierte_queda_anotado_con_su_texto_original(spark, silver):
    df = silver.ultima_entrega(bronze(spark, silver, [fila(prod_gas="12,5")], list(TIPOS)))

    r = silver.tipar(df, TIPOS).collect()[0]

    assert r["prod_gas"] is None
    assert r["_no_convierte"] == ["prod_gas"]
    assert r["_original"]["prod_gas"] == "12,5"


def test_un_valor_vacio_no_es_un_error_de_conversion(spark, silver):
    df = silver.ultima_entrega(bronze(spark, silver, [fila(prod_gas=None)], list(TIPOS)))

    r = silver.tipar(df, TIPOS).collect()[0]

    assert r["prod_gas"] is None
    assert r["_no_convierte"] == []


def test_una_columna_del_contrato_que_no_vino_queda_nula(spark, silver):
    sin_gas = [c for c in TIPOS if c != "prod_gas"]
    df = silver.ultima_entrega(bronze(spark, silver, [fila()], sin_gas))

    r = silver.tipar(df, TIPOS).collect()[0]

    assert r["prod_gas"] is None
    assert r["_no_convierte"] == []


def test_los_tipos_quedan_convertidos(spark, silver):
    df = silver.ultima_entrega(bronze(spark, silver, [fila()], list(TIPOS)))

    tipos = dict(silver.tipar(df, TIPOS).dtypes)

    assert (tipos["idpozo"], tipos["prod_pet"], tipos["fechaingreso"]) == ("bigint", "double", "timestamp")


# una_version_por_clave


def test_la_rectificativa_le_gana_a_la_declaracion_original(spark, silver):
    filas = [
        fila(prod_pet="10.5", fechaingreso="2024-02-01 10:00:00"),
        fila(prod_pet="99.0", fechaingreso="2024-03-01 10:00:00"),
    ]

    r = hasta_versiones(spark, silver, filas).collect()

    assert [x["prod_pet"] for x in r] == [99.0]
    assert r[0]["_versiones"] == 1


def test_las_copias_identicas_quedan_en_una(spark, silver):
    r = hasta_versiones(spark, silver, [fila(), fila()]).collect()

    assert len(r) == 1 and r[0]["_versiones"] == 1


def test_dos_versiones_distintas_con_la_misma_fecha_quedan_en_conflicto(spark, silver):
    r = hasta_versiones(spark, silver, [fila(prod_pet="10.5"), fila(prod_pet="11.5")]).collect()

    assert sorted(x["_versiones"] for x in r) == [2, 2]


def test_una_fila_que_no_convierte_no_se_descarta_aunque_sea_vieja(spark, silver):
    filas = [
        fila(fechaingreso="2024-03-01 10:00:00"),
        fila(prod_gas="12,5", fechaingreso="2024-02-01 10:00:00"),
    ]

    r = hasta_versiones(spark, silver, filas).collect()

    assert len([x for x in r if x["_no_convierte"]]) == 1  # llega a la cuarentena
    assert [x["_versiones"] for x in r if not x["_no_convierte"]] == [1]


# marcar y contratos


def test_una_regla_que_da_nulo_cuenta_como_falla(spark, silver):
    df = spark.createDataFrame([(None,), (5.0,)], "tef double")

    r = silver.marcar(df, {"tef_en_rango": "tef BETWEEN 0 AND 744"}).collect()

    assert [x["_motivos"] for x in r] == [["tef_en_rango"], []]


def test_las_reglas_del_contrato_de_padron_separan_buenas_de_malas(spark, silver):
    contrato = silver.CONTRATOS["padron"]
    filas = [
        {"idpozo": "1", "anio": "2006", "mes": "1"},
        {"idpozo": "2", "anio": "2006", "mes": "13"},
        {"idpozo": "x", "anio": "2006", "mes": "1"},
    ]
    filas = [{**f, "_archivo": archivo("2026-11-11", "padron.csv")} for f in filas]

    validada = silver.validar(bronze(spark, silver, filas, list(contrato["tipos"])), contrato)
    motivos = {r["_original"]["idpozo"]: sorted(r["_motivos"]) for r in validada.collect()}

    assert motivos["1"] == []
    assert motivos["2"] == ["mes_valido"]
    assert "valores_convierten" in motivos["x"] and "clave_completa" in motivos["x"]


def test_el_contrato_de_produccion_tiene_sql_valido(spark, silver):
    contrato = silver.CONTRATOS["produccion_pozo"]
    columnas = list(contrato["tipos"])
    f = {c: None for c in columnas} | {
        "idpozo": "157982", "anio": "2024", "mes": "1", "empresa": "YPF S.A.", "tef": "31",
        "fechaingreso": "2024-02-16 17:45:24.72974", "rectificado": "f", "habilitado": "t",
        "fecha_data": "2024-01-31", "tipo_de_recurso": "NO CONVENCIONAL", "_archivo": archivo("2026-11-11"),
    }

    r = silver.validar(bronze(spark, silver, [f], columnas), contrato).collect()[0]

    assert r["_motivos"] == []
    assert (r["rectificado"], r["habilitado"]) == (False, True)


# controlar


def test_el_control_falla_si_la_cuarentena_supera_el_umbral(spark, silver):
    contrato = silver.CONTRATOS["padron"]
    filas = [{"idpozo": str(i), "anio": "2006", "mes": "1"} for i in range(1, 99)]
    filas += [{"idpozo": "999", "anio": "2006", "mes": "13"}, {"idpozo": "998", "anio": "2006", "mes": "13"}]
    filas = [{**f, "_archivo": archivo("2026-11-11", "padron.csv")} for f in filas]
    validada = silver.validar(bronze(spark, silver, filas, list(contrato["tipos"])), contrato)

    control = silver.controlar("padron", validada, contrato, [], None)

    assert (control["filas_vigentes"], control["filas_cuarentena"]) == (98, 2)
    assert control["porcentaje_cuarentena"] == 2.0
    assert control["resultado"] == "falla: cuarentena sobre el umbral"
    assert control["motivos"] == '{"mes_valido": 2}'


def test_un_archivo_por_millon_de_filas_y_al_menos_uno(silver):
    assert [silver.archivos_para(n) for n in (0, 431_319, 1_000_000, 1_000_001)] == [1, 1, 1, 2]


def test_una_columna_nueva_con_datos_se_avisa(spark, silver):
    contrato = silver.CONTRATOS["padron"]
    filas = [{"idpozo": "1", "anio": "2006", "mes": "1", "pozo_horizontal": "S",
              "_archivo": archivo("2026-11-11", "padron.csv")}]
    df = bronze(spark, silver, filas, [*contrato["tipos"], "pozo_horizontal"])

    assert silver.columnas_fuera_de_contrato(df, contrato) == ["pozo_horizontal"]
