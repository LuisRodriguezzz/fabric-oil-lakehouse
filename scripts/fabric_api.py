"""Cliente mínimo de la API REST de Fabric, con un token de Microsoft Entra ID.

En Azure se trabaja igual: `azure-identity` pide el token y cada servicio tiene su audiencia
(Resource Manager, Storage, Data Factory). Acá, la API de Fabric y OneLake (Storage).
"""

import os
import sys
import time
from pathlib import Path

import requests
from azure.identity import (
    AuthenticationRecord,
    DeviceCodeCredential,
    TokenCachePersistenceOptions,
)

API = "https://api.fabric.microsoft.com/v1"
SCOPE_API = "https://api.fabric.microsoft.com/.default"
SCOPE_STORAGE = "https://storage.azure.com/.default"

# Quién inició sesión (no es una contraseña) y la caché de tokens, fuera del repo.
_REGISTRO = Path.home() / ".fabric-oil-lakehouse" / "auth_record.json"
_CACHE = TokenCachePersistenceOptions(name="fabric-oil-lakehouse")  # cifrada por el sistema


def _mostrar_codigo(url: str, codigo: str, _vence) -> None:
    print(f"\nPara iniciar sesión, abrí {url} e ingresá el código {codigo}\n", flush=True)


def credencial() -> DeviceCodeCredential:
    """Inicio de sesión con código de dispositivo: no depende de que se abra una ventana.

    La primera vez imprime una dirección y un código; después usa la caché sin pedir nada.
    Es el mismo flujo que `az login --use-device-code` en Azure.
    """
    tenant = os.environ.get("FABRIC_TENANT_ID")
    if not tenant:
        sys.exit("Falta la variable FABRIC_TENANT_ID (el ID del directorio de Entra ID).")
    if _REGISTRO.exists():
        registro = AuthenticationRecord.deserialize(_REGISTRO.read_text())
        return DeviceCodeCredential(
            tenant_id=tenant, cache_persistence_options=_CACHE, authentication_record=registro
        )
    cred = DeviceCodeCredential(
        tenant_id=tenant, cache_persistence_options=_CACHE, prompt_callback=_mostrar_codigo
    )
    registro = cred.authenticate(scopes=[SCOPE_API])
    _REGISTRO.parent.mkdir(parents=True, exist_ok=True)
    _REGISTRO.write_text(registro.serialize())
    return cred


class FabricApi:
    def __init__(self) -> None:
        self._cred = credencial()

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._cred.get_token(SCOPE_API).token}"}

    def listar(self, ruta: str) -> list[dict]:
        """GET de una colección, siguiendo las páginas (continuationToken)."""
        elementos, params = [], {}
        while True:
            r = requests.get(f"{API}{ruta}", headers=self._headers(), params=params, timeout=60)
            r.raise_for_status()
            cuerpo = r.json()
            # La mayoría de las listas viene en "value"; la de tablas de un lakehouse, en "data".
            elementos += cuerpo.get("value", cuerpo.get("data", []))
            if not cuerpo.get("continuationToken"):
                return elementos
            params = {"continuationToken": cuerpo["continuationToken"]}

    def post(self, ruta: str, cuerpo: dict | None = None) -> dict:
        """POST que espera las operaciones largas (respuesta 202 con Location)."""
        r = requests.post(f"{API}{ruta}", headers=self._headers(), json=cuerpo, timeout=60)
        if not r.ok:
            # El cuerpo trae el código de error de Fabric (errorCode), que explica el porqué.
            raise RuntimeError(f"POST {ruta} -> {r.status_code}: {r.text}")
        if r.status_code == 202 and "Location" in r.headers:
            return self._esperar(r)
        return r.json() if r.content else {}

    def _esperar(self, r: requests.Response) -> dict:
        estado_url = r.headers["Location"]
        while True:
            time.sleep(int(r.headers.get("Retry-After", 5)))
            r = requests.get(estado_url, headers=self._headers(), timeout=60)
            r.raise_for_status()
            estado = r.json().get("status")
            if estado == "Succeeded":
                return r.json()
            if estado == "Failed":
                raise RuntimeError(f"La operación falló: {r.json()}")
