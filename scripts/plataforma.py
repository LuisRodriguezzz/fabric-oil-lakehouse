"""Crea la plataforma del proyecto en Fabric: un workspace por ambiente, en la capacidad (D3, D6).

Es idempotente: si un workspace ya existe, no lo crea de nuevo; si está en otra capacidad, lo
reasigna. En Azure, este paso sería un template de Bicep o ARM con un resource group por ambiente.

También deja los ajustes de Spark de cada workspace como los necesita el proyecto (D21): la alta
concurrencia para pipelines, para que nb_bronze y nb_silver compartan una sesión de Spark.

Uso (desde la raíz del repo):
    set FABRIC_TENANT_ID=<id del directorio>
    .venv\\Scripts\\python scripts\\plataforma.py          (todos los ambientes)
    .venv\\Scripts\\python scripts\\plataforma.py dev      (uno solo)
Si hay más de una capacidad activa, definir también FABRIC_CAPACITY_ID.
"""

import os
import sys

from fabric_api import FabricApi

WORKSPACES = {
    "dev": "oil-dev",
    "prod": "oil-prod",
}

# Ajustes de Spark por workspace (API "Workspace Settings - Update Spark Settings"). La alta
# concurrencia para pipelines es lo que habilita el sessionTag de las actividades Notebook.
ALTA_CONCURRENCIA = {"notebookPipelineRunEnabled": True}


def asegurar_spark(api: FabricApi, ws_id: str, nombre: str) -> None:
    """Prende la alta concurrencia para pipelines si está apagada. Si ya está, no toca nada."""
    ruta = f"/workspaces/{ws_id}/spark/settings"
    antes = api.get(ruta)
    actual = antes.get("highConcurrency", {})
    if all(actual.get(k) == v for k, v in ALTA_CONCURRENCIA.items()):
        print(f"{nombre}: alta concurrencia para pipelines ya prendida, sin cambios")
        return
    # Se manda la sección entera (lo que había más el cambio) y solo esa sección.
    api.patch(ruta, {"highConcurrency": {**actual, **ALTA_CONCURRENCIA}})
    despues = api.get(ruta)
    sin_tocar = {k: v for k, v in antes.items() if k != "highConcurrency"}
    if {k: despues.get(k) for k in sin_tocar} != sin_tocar:
        sys.exit(f"{nombre}: el PATCH cambió otros ajustes de Spark: {antes} -> {despues}")
    if not all(despues["highConcurrency"].get(k) == v for k, v in ALTA_CONCURRENCIA.items()):
        sys.exit(f"{nombre}: la alta concurrencia no quedó prendida: {despues}")
    print(f"{nombre}: alta concurrencia para pipelines prendida ({actual} -> {despues['highConcurrency']})")


def capacidad(api: FabricApi) -> dict:
    """La capacidad de Fabric activa. Las de Fabric tienen SKU F (de prueba: FT); se descartan las
    de Power BI, como Premium Per User (PP), porque no corren lakehouses ni pipelines."""
    activas = [
        c
        for c in api.listar("/capacities")
        if c.get("state") == "Active" and c.get("sku", "").startswith("F")
    ]
    elegida = os.environ.get("FABRIC_CAPACITY_ID")
    if elegida:
        activas = [c for c in activas if c["id"] == elegida]
    if len(activas) != 1:
        nombres = [f"{c['displayName']} ({c['id']})" for c in activas]
        sys.exit(f"Se esperaba una capacidad activa y hay {len(activas)}: {nombres}")
    return activas[0]


def main(ambientes: list[str]) -> None:
    api = FabricApi()
    cap = capacidad(api)
    print(f"Capacidad: {cap['displayName']} | {cap['sku']} | {cap['region']}")

    existentes = {ws["displayName"]: ws for ws in api.listar("/workspaces")}
    for ambiente in ambientes:
        nombre = WORKSPACES[ambiente]
        ws = existentes.get(nombre)
        if ws is None:
            ws = api.post(
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
        asegurar_spark(api, ws["id"], nombre)


if __name__ == "__main__":
    pedidos = sys.argv[1:] or list(WORKSPACES)
    if any(a not in WORKSPACES for a in pedidos):
        sys.exit(__doc__)
    main(pedidos)
