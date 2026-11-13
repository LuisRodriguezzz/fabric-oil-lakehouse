"""Despliega los items del repo (carpeta fabric/) en el workspace de un ambiente, con fabric-cicd.

Es el paso de "release" de CI/CD: toma lo que está en Git, no lo que hay en oil-dev, y lo publica
en el workspace del ambiente. Lo que cambia entre ambientes está en fabric/parameter.yml.

Identidad:
  - en tu compu, tu usuario (código de dispositivo, como el resto de los scripts);
  - en un pipeline de CI/CD (Azure DevOps o GitHub Actions), la identidad con la que el pipeline
    hizo `az login`: un service principal sin contraseña (workload identity federation).

Uso: .venv\\Scripts\\python scripts\\desplegar.py PROD
"""

import os
import sys
from pathlib import Path

import requests
from azure.identity import AzureCliCredential
from fabric_cicd import FabricWorkspace, publish_all_items, unpublish_all_orphan_items

from fabric_api import API, SCOPE_API, credencial

WORKSPACES = {"PROD": "oil-prod"}
# Lo que se despliega. Las conexiones y el gateway no son items: viven en el tenant.
TIPOS = ["Lakehouse", "SQLDatabase", "Notebook", "DataPipeline"]
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


def desplegar(ambiente: str) -> None:
    cred = identidad()
    nombre = WORKSPACES[ambiente]
    destino = FabricWorkspace(
        workspace_id=id_del_workspace(cred, nombre),
        environment=ambiente,
        repository_directory=str(REPO),
        item_type_in_scope=TIPOS,
        token_credential=cred,
    )
    publish_all_items(destino)
    # Lo que está en el workspace del ambiente y ya no está en el repo, se borra: Git manda.
    unpublish_all_orphan_items(destino)
    print(f"Desplegado en {nombre}.")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in WORKSPACES:
        sys.exit(__doc__)
    desplegar(sys.argv[1])
