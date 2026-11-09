"""Deja una entrega en landing, como lo haría el proveedor de datos (D9).

Destino: lh_bronze.Lakehouse/Files/landing/<fuente>/ingest_date=<AAAA-MM-DD>/<archivo>

Landing es inmutable: si ese archivo ya está en esa fecha, no se pisa. Una corrección de la fuente
llega como un archivo nuevo en otra fecha, y elegir cuál vale es trabajo de silver.

Usa el SDK de ADLS Gen2: es el mismo código que contra un Data Lake de Azure; solo cambia la
dirección (D8). En producción, este paso lo hace el pipeline de Data Factory (F2).

Uso: .venv\\Scripts\\python scripts\\subir_a_landing.py <produccion|padron> <archivo.csv> [AAAA-MM-DD]
"""

import os
import sys
from datetime import date
from pathlib import Path

from azure.storage.filedatalake import DataLakeServiceClient

from fabric_api import credencial

FUENTES = ("produccion", "padron")
WORKSPACE = os.environ.get("FABRIC_WORKSPACE", "oil-dev")

# Azure: https://<storage account>.dfs.core.windows.net. OneLake: la cuenta es siempre "onelake";
# se usa el endpoint de la región de la capacidad para que los datos no salgan de ella.
ONELAKE = os.environ.get("ONELAKE_URL", "https://brazilsouth-onelake.dfs.fabric.microsoft.com")


def subir(fuente: str, archivo: Path, fecha: str) -> None:
    servicio = DataLakeServiceClient(account_url=ONELAKE, credential=credencial())
    container = servicio.get_file_system_client(WORKSPACE)  # Azure: el container
    carpeta = container.get_directory_client(
        f"lh_bronze.Lakehouse/Files/landing/{fuente}/ingest_date={fecha}"
    )
    destino = carpeta.get_file_client(archivo.name)
    if destino.exists():
        print(f"Ya existe {fuente}/ingest_date={fecha}/{archivo.name}: landing no se pisa.")
        return
    carpeta.create_directory()
    # overwrite=True es seguro acá porque ya se comprobó que no existe; con overwrite=False el SDK
    # no crea el archivo y falla con PathNotFound (probado el 9/11).
    with archivo.open("rb") as datos:
        destino.upload_data(datos, overwrite=True)
    tamano = destino.get_file_properties().size
    print(f"Subido {fuente}/ingest_date={fecha}/{archivo.name} ({tamano} bytes)")


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4) or sys.argv[1] not in FUENTES:
        sys.exit(__doc__)
    fecha = sys.argv[3] if len(sys.argv) == 4 else date.today().isoformat()
    date.fromisoformat(fecha)  # falla si la fecha no es AAAA-MM-DD
    subir(sys.argv[1], Path(sys.argv[2]), fecha)
