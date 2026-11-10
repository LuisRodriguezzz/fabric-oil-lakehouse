"""Cuenta las filas de una tabla Delta leyendo solo su _delta_log, sin Spark.

Recorre los commits en orden: cada `add` suma un archivo a la versión actual y cada `remove` lo
saca. Las filas son la suma de `numRecords` (de las estadísticas de cada `add`) de los archivos que
quedan vigentes. Es lo que viste en "Delta por dentro", aplicado a OneLake con el SDK de ADLS.

Uso: .venv\\Scripts\\python scripts\\contar_delta.py <lakehouse> <tabla>   (ej.: lh_bronze energia/produccion)
"""

import json
import os
import sys

from azure.storage.filedatalake import DataLakeServiceClient

from fabric_api import credencial

WORKSPACE = os.environ.get("FABRIC_WORKSPACE", "oil-dev")
ONELAKE = os.environ.get("ONELAKE_URL", "https://brazilsouth-onelake.dfs.fabric.microsoft.com")


def contar(lakehouse: str, tabla: str) -> None:
    container = DataLakeServiceClient(ONELAKE, credential=credencial()).get_file_system_client(
        WORKSPACE
    )
    log = f"{lakehouse}.Lakehouse/Tables/{tabla}/_delta_log"
    commits = sorted(p.name for p in container.get_paths(path=log) if p.name.endswith(".json"))
    vigentes: dict[str, int] = {}
    for ruta in commits:
        texto = container.get_file_client(ruta).download_file().readall().decode("utf-8")
        for linea in texto.splitlines():
            accion = json.loads(linea)
            if "add" in accion:
                stats = json.loads(accion["add"].get("stats") or "{}")
                vigentes[accion["add"]["path"]] = stats.get("numRecords", 0)
            elif "remove" in accion:
                vigentes.pop(accion["remove"]["path"], None)
    print(
        f"{WORKSPACE}/{lakehouse}/{tabla}: {len(commits)} commits, "
        f"{len(vigentes)} archivos vigentes, {sum(vigentes.values())} filas"
    )


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    contar(sys.argv[1], sys.argv[2])
