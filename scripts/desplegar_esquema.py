"""Despliega el esquema (DDL) de wh_gold y sqldb_control en un ambiente, con DACPAC y SqlPackage (D40).

fabric-cicd publica el Warehouse y la SQL database solo como "cáscara": las tablas, vistas y
procedimientos no llegan por ese camino. Este script hace el resto:
  1. arma un DACPAC desde cada proyecto SQL del repo (dotnet build del .sqlproj);
  2. lo compara con la base del ambiente y aplica solo la diferencia (SqlPackage).

Reglas para una base con datos:
  - BlockOnPossibleDataLoss=True: si un cambio puede perder datos, frena en vez de aplicarlo;
  - DropObjectsNotInSource=False: no borra lo que esté en la base y no en el repo;
  - AllowTableRecreation=False: no reconstruye tablas (en un Warehouse, el ALTER TABLE es limitado
    y muchos cambios terminarían en recrear la tabla con sus datos).

Identidad: la misma que desplegar.py (tu usuario en la compu; el service principal en GitHub
Actions). SqlPackage recibe un token de Entra con /AccessToken.

Uso:
  .venv\\Scripts\\python scripts\\desplegar_esquema.py PROD --previa   genera el script SQL, sin aplicar
  .venv\\Scripts\\python scripts\\desplegar_esquema.py PROD            aplica
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import requests

from desplegar import WORKSPACES, id_del_workspace, identidad
from fabric_api import API, SCOPE_API

REPO = Path(__file__).resolve().parents[1] / "fabric"
SCOPE_SQL = "https://database.windows.net/.default"
BASES = [
    # (tipo de item, ruta de la API, carpeta del proyecto en el repo)
    ("Warehouse", "warehouses", REPO / "04_gold" / "wh_gold.Warehouse" / "wh_gold.sqlproj"),
    ("SQLDatabase", "sqlDatabases", REPO / "00_control" / "sqldb_control.SQLDatabase" / "sqldb_control.sqlproj"),
]
PROPIEDADES = [
    "/p:BlockOnPossibleDataLoss=True",
    "/p:DropObjectsNotInSource=False",
    "/p:AllowTableRecreation=False",
]


def herramienta(nombre: str) -> str:
    ruta = shutil.which(nombre) or shutil.which(str(Path.home() / ".dotnet" / nombre)) \
        or shutil.which(str(Path.home() / ".dotnet" / "tools" / nombre))
    if not ruta:
        sys.exit(f"No encuentro {nombre}. Instalá el SDK de .NET 8 y `dotnet tool install -g microsoft.sqlpackage`.")
    return ruta


def destino_sql(cred, workspace_id: str, tipo: str, ruta_api: str, nombre: str) -> tuple[str, str]:
    """Servidor y base del item en el workspace del ambiente, leídos de la API de Fabric."""
    h = {"Authorization": f"Bearer {cred.get_token(SCOPE_API).token}"}
    items = requests.get(f"{API}/workspaces/{workspace_id}/items?type={tipo}", headers=h, timeout=60).json()["value"]
    item = next(i for i in items if i["displayName"] == nombre)
    p = requests.get(f"{API}/workspaces/{workspace_id}/{ruta_api}/{item['id']}", headers=h, timeout=60).json()["properties"]
    if tipo == "Warehouse":
        return p["connectionString"], nombre
    # SQL database: "Data Source=<servidor>,1433;Initial Catalog=<base>;..."
    partes = dict(x.split("=", 1) for x in p["connectionString"].split(";") if "=" in x)
    return partes["Data Source"].split(",")[0], partes["Initial Catalog"]


def desplegar(ambiente: str, previa: bool) -> None:
    dotnet, sqlpackage = herramienta("dotnet"), herramienta("sqlpackage")
    cred = identidad()
    workspace_id = id_del_workspace(cred, WORKSPACES[ambiente])
    salida = Path(tempfile.mkdtemp(prefix="esquema_"))
    for tipo, ruta_api, proyecto in BASES:
        nombre = proyecto.stem
        subprocess.run([dotnet, "build", str(proyecto), "-c", "Release", "-o", str(salida / nombre),
                        "--nologo", "-v", "q"], check=True)
        servidor, base = destino_sql(cred, workspace_id, tipo, ruta_api, nombre)
        conexion = f"Server=tcp:{servidor},1433;Initial Catalog={base};Encrypt=True;TrustServerCertificate=False;Connection Timeout=60;"
        token = cred.get_token(SCOPE_SQL).token
        comun = [f"/SourceFile:{salida / nombre / (nombre + '.dacpac')}", f"/TargetConnectionString:{conexion}",
                 f"/AccessToken:{token}", *PROPIEDADES]
        if previa:
            script = salida / f"{nombre}.sql"
            subprocess.run([sqlpackage, "/Action:Script", *comun, f"/OutputPath:{script}"], check=True)
            print(f"== {nombre}: lo que aplicaría en {WORKSPACES[ambiente]} → {script}")
            print(script.read_text(encoding="utf-8"))
        else:
            subprocess.run([sqlpackage, "/Action:Publish", *comun], check=True)
            print(f"== {nombre}: esquema desplegado en {WORKSPACES[ambiente]}.")


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3) or sys.argv[1] not in WORKSPACES or sys.argv[2:] not in ([], ["--previa"]):
        sys.exit(__doc__)
    desplegar(sys.argv[1], previa=sys.argv[2:] == ["--previa"])
