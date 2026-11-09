"""Crea la plataforma del proyecto en Fabric: un workspace por ambiente, en la capacidad (D3, D6).

Es idempotente: si un workspace ya existe, no lo crea de nuevo; si está en otra capacidad, lo
reasigna. En Azure, este paso sería un template de Bicep o ARM con un resource group por ambiente.

Uso (desde la raíz del repo):
    set FABRIC_TENANT_ID=<id del directorio>
    .venv\\Scripts\\python scripts\\plataforma.py
Si hay más de una capacidad activa, definir también FABRIC_CAPACITY_ID.
"""

import os
import sys

from fabric_api import FabricApi

WORKSPACES = {
    "dev": "oil-dev",
    "prod": "oil-prod",
}


def capacidad(api: FabricApi) -> dict:
    activas = [c for c in api.listar("/capacities") if c.get("state") == "Active"]
    elegida = os.environ.get("FABRIC_CAPACITY_ID")
    if elegida:
        activas = [c for c in activas if c["id"] == elegida]
    if len(activas) != 1:
        nombres = [f"{c['displayName']} ({c['id']})" for c in activas]
        sys.exit(f"Se esperaba una capacidad activa y hay {len(activas)}: {nombres}")
    return activas[0]


def main() -> None:
    api = FabricApi()
    cap = capacidad(api)
    print(f"Capacidad: {cap['displayName']} · {cap['sku']} · {cap['region']}")

    existentes = {ws["displayName"]: ws for ws in api.listar("/workspaces")}
    for ambiente, nombre in WORKSPACES.items():
        ws = existentes.get(nombre)
        if ws is None:
            api.post(
                "/workspaces",
                {
                    "displayName": nombre,
                    "capacityId": cap["id"],
                    "description": f"Proyecto oil, ambiente {ambiente}.",
                },
            )
            print(f"{nombre}: creado")
        elif ws.get("capacityId") != cap["id"]:
            api.post(f"/workspaces/{ws['id']}/assignToCapacity", {"capacityId": cap["id"]})
            print(f"{nombre}: reasignado a la capacidad")
        else:
            print(f"{nombre}: ya existe, sin cambios")


if __name__ == "__main__":
    main()
