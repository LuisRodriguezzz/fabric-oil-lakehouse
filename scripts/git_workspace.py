"""Control de código del workspace oil-dev desde la terminal: el panel "Source control" de Fabric.

    status   qué cambió en el workspace y qué cambió en la rama
    commit   guarda en Git todo lo que cambió en el workspace (como "Commit" en el portal)
    update   trae al workspace lo que cambió en la rama (como "Update all" en el portal)

En Azure Data Factory, el equivalente es la integración de Git de ADF Studio: se guarda en la rama
de trabajo y "Publish" genera los ARM templates. En Fabric no hay paso de publish (D5).

Uso: .venv\\Scripts\\python scripts\\git_workspace.py status|commit|update ["mensaje"]
"""

import sys

import requests

from fabric_api import API, FabricApi

WORKSPACE = "oil-dev"


def _ws(api: FabricApi) -> str:
    for w in api.listar("/workspaces"):
        if w["displayName"] == WORKSPACE:
            return w["id"]
    sys.exit(f"No existe el workspace {WORKSPACE}.")


def _estado(api: FabricApi, ws: str) -> dict:
    r = requests.get(f"{API}/workspaces/{ws}/git/status", headers=api._headers(), timeout=120)
    if r.status_code == 202:  # el estado se calcula como operación larga
        return api._esperar(r) or {}
    r.raise_for_status()
    return r.json()


def status(api: FabricApi, ws: str) -> dict:
    estado = _estado(api, ws)
    print(f"workspaceHead={estado.get('workspaceHead')}  remoteCommitHash={estado.get('remoteCommitHash')}")
    for c in estado.get("changes", []):
        item = c["itemMetadata"]
        print(
            f"  {item['itemType']:<12} {item['displayName']:<20} "
            f"workspace={c.get('workspaceChange')}  rama={c.get('remoteChange')}  conflicto={c.get('conflictType')}"
        )
    return estado


def commit(api: FabricApi, ws: str, mensaje: str) -> None:
    estado = status(api, ws)
    if not any(c.get("workspaceChange") for c in estado.get("changes", [])):
        print("No hay cambios del workspace para guardar.")
        return
    api.post(
        f"/workspaces/{ws}/git/commitToGit",
        {"mode": "All", "workspaceHead": estado.get("workspaceHead"), "comment": mensaje},
    )
    print("Commit hecho en la rama.")


def update(api: FabricApi, ws: str) -> None:
    estado = status(api, ws)
    if estado.get("remoteCommitHash") == estado.get("workspaceHead"):
        print("El workspace ya está al día con la rama.")
        return
    api.post(
        f"/workspaces/{ws}/git/updateFromGit",
        {
            "remoteCommitHash": estado.get("remoteCommitHash"),
            "workspaceHead": estado.get("workspaceHead"),
            # Si un item cambió en los dos lados, gana la rama: el repo es la fuente de verdad.
            "conflictResolution": {
                "conflictResolutionType": "Workspace",
                "conflictResolutionPolicy": "PreferRemote",
            },
            "options": {"allowOverrideItems": True},
        },
    )
    print("Workspace actualizado desde la rama.")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("status", "commit", "update"):
        sys.exit(__doc__)
    api = FabricApi()
    ws = _ws(api)
    if sys.argv[1] == "status":
        status(api, ws)
    elif sys.argv[1] == "commit":
        commit(api, ws, sys.argv[2] if len(sys.argv) > 2 else "Cambios desde el workspace oil-dev")
    else:
        update(api, ws)
