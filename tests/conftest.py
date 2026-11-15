"""Lo que comparten los tests: el código de nb_silver como módulo y una sesión de Spark.

El notebook vive en fabric/nb_silver.Notebook/notebook-content.py, que es Python válido (las
marcas de celda son comentarios). Al importarlo, __name__ no es "__main__", así que el bloque
que escribe en OneLake no corre: solo quedan las funciones y los contratos.
"""

import importlib.util
from pathlib import Path

import pytest
from pyspark.sql import SparkSession

# El notebook se busca dentro de fabric/ esté en la carpeta que esté: el workspace se ordena en
# carpetas y Git las refleja como subcarpetas (D31).
NOTEBOOK = next((Path(__file__).resolve().parents[1] / "fabric").glob("**/nb_silver.Notebook/notebook-content.py"))


def _cargar_silver():
    spec = importlib.util.spec_from_file_location("nb_silver", NOTEBOOK)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture(scope="session")
def silver():
    return _cargar_silver()


@pytest.fixture(scope="session")
def spark():
    # Dentro de Fabric ya hay una sesión: se usa esa y no se apaga al final.
    activa = SparkSession.getActiveSession()
    sesion = activa or (
        SparkSession.builder.master("local[1]")
        .appName("tests-fabric-oil-lakehouse")
        .config("spark.sql.ansi.enabled", "true")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.shuffle.partitions", "1")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )
    yield sesion
    if activa is None:
        sesion.stop()
