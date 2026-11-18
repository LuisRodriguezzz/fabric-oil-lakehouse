"""Simulador de telemetría de pozos (SCADA) para el laboratorio de tiempo real (D38).

Manda al custom endpoint de `es_telemetria` un evento JSON por pozo cada `--intervalo` segundos:
presión en boca de pozo (bar), caudal de petróleo (m3/d) y temperatura (°C).

Los datos son SIMULADOS. Lo único real son los pozos: los 20 de Vaca Muerta con más petróleo
en su primer año (`mart_dbt.fractura_vs_produccion`, 17/11). El caudal base de cada uno es ese
petróleo dividido 365.

Autentica con el usuario de Entra ID (la misma credencial que `fabric_api.py`), sin claves.
El namespace y el nombre del event hub salen de la pestaña Entra ID de la fuente `src_simulador`.

Uso:
    python scripts/simular_telemetria.py --namespace <xxx.servicebus.windows.net> --eventhub <nombre> --minutos 5
    python scripts/simular_telemetria.py ... --falla 164941     # el pozo pierde presión a mitad de la corrida
"""

from __future__ import annotations

import argparse
import json
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone

# idpozo: petróleo del primer año (m3), de mart_dbt.fractura_vs_produccion
POZOS = {
    164941: 182096, 162246: 125136, 164127: 119509, 166862: 112984, 166916: 96592,
    163522: 94676, 162943: 93931, 166825: 91875, 166911: 90313, 163525: 90248,
    164942: 88991, 166913: 86636, 166917: 86140, 163251: 85818, 166915: 85681,
    163694: 84408, 166914: 82999, 166783: 79887, 166826: 79857, 165097: 79856,
}


@dataclass
class Pozo:
    idpozo: int
    caudal_base: float  # m3/d
    presion: float = 0.0
    caudal: float = 0.0
    temperatura: float = 0.0

    def __post_init__(self) -> None:
        self.presion = random.uniform(180, 260)
        self.caudal = self.caudal_base
        self.temperatura = random.uniform(65, 80)

    def paso(self, en_falla: bool) -> dict:
        """Avanza un intervalo: paseo aleatorio alrededor del valor base, o caída si está en falla."""
        if en_falla:
            self.presion = max(5.0, self.presion * 0.85)
            self.caudal = max(0.0, self.caudal * 0.80)
        else:
            self.presion += random.gauss(0, 1.5)
            self.caudal += random.gauss(0, self.caudal_base * 0.01) + 0.05 * (self.caudal_base - self.caudal)
        self.temperatura += random.gauss(0, 0.2)
        return {
            "idpozo": self.idpozo,
            "ts": datetime.now(timezone.utc).isoformat(),
            "presion_bar": round(self.presion, 2),
            "caudal_m3d": round(max(self.caudal, 0.0), 2),
            "temperatura_c": round(self.temperatura, 2),
        }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--namespace", required=True, help="Event hub namespace (xxx.servicebus.windows.net)")
    p.add_argument("--eventhub", required=True, help="Nombre del event hub de la fuente")
    p.add_argument("--minutos", type=float, default=5, help="Cuánto tiempo mandar eventos")
    p.add_argument("--intervalo", type=float, default=5, help="Segundos entre lecturas de cada pozo")
    p.add_argument("--falla", type=int, help="idpozo que pierde presión desde la mitad de la corrida")
    a = p.parse_args()

    from azure.eventhub import EventData, EventHubProducerClient
    from fabric_api import FabricApi

    pozos = [Pozo(i, petroleo / 365) for i, petroleo in POZOS.items()]
    cliente = EventHubProducerClient(fully_qualified_namespace=a.namespace, eventhub_name=a.eventhub,
                                     credential=FabricApi()._cred)
    fin = time.monotonic() + a.minutos * 60
    mitad = time.monotonic() + a.minutos * 30
    enviados = 0
    with cliente:
        while time.monotonic() < fin:
            lote = cliente.create_batch()
            for pozo in pozos:
                en_falla = pozo.idpozo == a.falla and time.monotonic() >= mitad
                lote.add(EventData(json.dumps(pozo.paso(en_falla))))
            cliente.send_batch(lote)
            enviados += len(pozos)
            print(f"{datetime.now():%H:%M:%S}  {enviados} eventos", flush=True)
            time.sleep(a.intervalo)


if __name__ == "__main__":
    main()
