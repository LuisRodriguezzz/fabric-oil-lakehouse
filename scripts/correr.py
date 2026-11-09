"""Corre un notebook o un pipeline del workspace y espera a que termine (Job Scheduler de Fabric).

En Azure: un pipeline de Data Factory se dispara con `az datafactory pipeline create-run` o por la
API de ADF, y un notebook de Databricks con un job. En Fabric, los dos se corren igual: un "job" del
item, con la API de Job Scheduler.

Uso: .venv\\Scripts\\python scripts\\correr.py <nombre del item>   (por ejemplo nb_bronze)
"""

import os
import sys
import time

import requests

from fabric_api import API, FabricApi

WORKSPACE = os.environ.get("FABRIC_WORKSPACE", "oil-dev")
TIPO_DE_JOB = {"Notebook": "RunNotebook", "DataPipeline": "Pipeline"}


def correr(nombre: str) -> None:
    api = FabricApi()
    ws = next(w["id"] for w in api.listar("/workspaces") if w["displayName"] == WORKSPACE)
    item = next(
        (i for i in api.listar(f"/workspaces/{ws}/items") if i["displayName"] == nombre), None
    )
    if item is None or item["type"] not in TIPO_DE_JOB:
        sys.exit(f"No hay un notebook ni un pipeline llamado {nombre!r} en {WORKSPACE}.")

    url = f"{API}/workspaces/{ws}/items/{item['id']}/jobs/instances?jobType={TIPO_DE_JOB[item['type']]}"
    r = requests.post(url, headers=api._headers(), timeout=60)
    if r.status_code != 202:
        sys.exit(f"No se pudo iniciar: {r.status_code} {r.text}")
    instancia = r.headers["Location"]
    print(f"{nombre}: iniciado en {WORKSPACE}")

    inicio = time.time()
    while True:
        time.sleep(15)
        estado = requests.get(instancia, headers=api._headers(), timeout=60).json()
        print(f"  {int(time.time() - inicio)} s - {estado.get('status')}", flush=True)
        if estado.get("status") in ("Completed", "Failed", "Cancelled", "Deduped"):
            break
    if estado.get("status") != "Completed":
        sys.exit(f"{nombre}: {estado.get('status')} - {estado.get('failureReason')}")
    print(f"{nombre}: terminó bien")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    correr(sys.argv[1])
