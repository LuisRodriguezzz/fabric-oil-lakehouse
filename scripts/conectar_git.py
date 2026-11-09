"""Conecta el workspace de dev al repo de GitHub, en la rama main y la carpeta fabric/ (D4).

Es idempotente: si el workspace ya está conectado, solo muestra a qué. Usa una conexión de Fabric
de tipo GitHub que ya tenga el token (se crea una vez en Workspace settings > Git integration >
Add account; el token nunca pasa por este repo).

En Azure DevOps sería lo mismo con gitProviderType "AzureDevOps", sin token: se autentica con la
cuenta de Entra ID o con un service principal.

Uso (desde la raíz del repo): .venv\\Scripts\\python scripts\\conectar_git.py
"""

import os
import sys

import requests

from fabric_api import API, FabricApi

WORKSPACE = "oil-dev"
CONEXION = os.environ.get("FABRIC_GIT_CONNECTION", "luis-github")
REPO = {
    "gitProviderType": "GitHub",
    "ownerName": "LuisRodriguezzz",
    "repositoryName": "fabric-oil-lakehouse",
    "branchName": "main",
    "directoryName": "/fabric",
}


def main() -> None:
    api = FabricApi()
    ws = next((w for w in api.listar("/workspaces") if w["displayName"] == WORKSPACE), None)
    if ws is None:
        sys.exit(f"No existe el workspace {WORKSPACE}: correr antes scripts/plataforma.py")

    r = requests.get(f"{API}/workspaces/{ws['id']}/git/connection", headers=api._headers(), timeout=60)
    r.raise_for_status()
    estado = r.json()
    if estado["gitConnectionState"] != "NotConnected":
        d = estado["gitProviderDetails"]
        print(f"{WORKSPACE} ya está conectado a {d['repositoryName']}:{d['branchName']}{d['directoryName']}")
        return

    conexion = next(
        (c for c in api.listar("/connections") if c.get("displayName") == CONEXION), None
    )
    if conexion is None:
        sys.exit(f"No existe la conexión de GitHub {CONEXION!r} en Fabric.")

    api.post(
        f"/workspaces/{ws['id']}/git/connect",
        {
            "gitProviderDetails": REPO,
            "myGitCredentials": {"source": "ConfiguredConnection", "connectionId": conexion["id"]},
        },
    )
    # Primera sincronización. Con el workspace y la carpeta vacíos no hay nada que copiar; si
    # los dos tuvieran contenido, PreferWorkspace deja que gane lo que hay en Fabric.
    inicio = api.post(
        f"/workspaces/{ws['id']}/git/initializeConnection",
        {"initializationStrategy": "PreferWorkspace"},
    )
    print(f"{WORKSPACE} conectado a {REPO['repositoryName']}:{REPO['branchName']}{REPO['directoryName']}")
    print(f"Acción pendiente después de conectar: {inicio.get('requiredAction')}")


if __name__ == "__main__":
    main()
