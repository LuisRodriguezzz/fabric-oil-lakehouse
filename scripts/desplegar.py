"""Despliega los items del repo (carpeta fabric/) en el workspace de un ambiente, con fabric-cicd.

Es el paso de "release" de CI/CD: toma lo que está en Git, no lo que hay en oil-dev, y lo publica
en el workspace del ambiente. Lo que cambia entre ambientes está en fabric/parameter.yml y en los
juegos de valores de la Variable library vl_oil (D20, D39).

Identidad:
  - en tu compu, tu usuario (código de dispositivo, como el resto de los scripts);
  - en GitHub Actions, la identidad con la que el workflow hizo `azure/login`: el service
    principal sp-oil-cicd, sin contraseña (credencial federada, OIDC).

Uso:
  .venv\\Scripts\\python scripts\\desplegar.py PROD            despliega
  .venv\\Scripts\\python scripts\\desplegar.py PROD --previa   muestra qué reemplaza, sin publicar
"""

import os
import sys
from pathlib import Path

import requests
from azure.identity import AzureCliCredential
from fabric_cicd import FabricWorkspace, publish_all_items

from fabric_api import API, SCOPE_API, credencial

WORKSPACES = {"PROD": "oil-prod"}

# Lo que se despliega: el batch. Afuera quedan, a propósito:
#  - el laboratorio de tiempo real (Eventhouse, KQLDatabase, Eventstream, KQLDashboard, Reflex):
#    telemetría simulada, no va a prod (D38); además, un service principal no puede crear ni
#    actualizar un Activator (Reflex);
#  - lo que vive solo en prod y no en Git: el monitoreo del workspace (D37) y act_oil.
# Las conexiones y el gateway no son items: viven en el tenant.
TIPOS = [
    "Lakehouse",
    "Warehouse",
    "SQLDatabase",
    "VariableLibrary",
    "Notebook",
    "DataPipeline",
    "DataBuildToolJob",
    "SemanticModel",
    "Report",
]
REPO = Path(__file__).resolve().parents[1] / "fabric"


def identidad():
    # GitHub Actions define CI; Azure Pipelines define TF_BUILD.
    if os.environ.get("CI") or os.environ.get("TF_BUILD"):
        return AzureCliCredential()
    return credencial()


def id_del_workspace(cred, nombre: str) -> str:
    token = cred.get_token(SCOPE_API).token
    r = requests.get(f"{API}/workspaces", headers={"Authorization": f"Bearer {token}"}, timeout=60)
    r.raise_for_status()
    return next(w["id"] for w in r.json()["value"] if w["displayName"] == nombre)


def destino(ambiente: str) -> FabricWorkspace:
    cred = identidad()
    return FabricWorkspace(
        workspace_id=id_del_workspace(cred, WORKSPACES[ambiente]),
        # Elige la columna de parameter.yml y el juego activo de vl_oil: tiene que llamarse igual.
        environment=ambiente,
        repository_directory=str(REPO),
        item_type_in_scope=TIPOS,
        token_credential=cred,
    )


def previa(ws: FabricWorkspace) -> None:
    """Muestra, sin publicar nada, cómo quedan los archivos que parameter.yml modifica."""
    ws._refresh_repository_items()
    ws._refresh_deployed_items()
    for tipo, items in ws.repository_items.items():
        for nombre, item in items.items():
            for archivo in item.item_files:
                if archivo.type != "text":
                    continue
                antes = archivo.contents
                despues = ws._replace_parameters(archivo, item)
                if antes != despues:
                    print(f"== {tipo} {nombre}: {archivo.file_path.name}")
                    for a, d in zip(antes.splitlines(), despues.splitlines()):
                        if a != d:
                            print(f"   - {a.strip()}\n   + {d.strip()}")


def desplegar(ambiente: str) -> None:
    ws = destino(ambiente)
    publish_all_items(ws)
    # No se llama a unpublish_all_orphan_items: con item_type_in_scope recortado, la doc de
    # fabric-cicd lo desaconseja. Un item que se borra del repo se borra a mano en prod (como con
    # dp-oil, que tampoco despliega borrados).
    print(f"Desplegado en {WORKSPACES[ambiente]}.")


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3) or sys.argv[1] not in WORKSPACES:
        sys.exit(__doc__)
    if sys.argv[2:] == ["--previa"]:
        previa(destino(sys.argv[1]))
    else:
        desplegar(sys.argv[1])
