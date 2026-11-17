# Runbook de `oil-prod`

Qué hacer cada día y cuando algo falla. Las decisiones están en la D25 (schedule) y la D37
(operación). Las consultas de este runbook están en [`consultas.kql`](consultas.kql).

## Qué corre

| Qué | Cuándo | Duración normal |
|---|---|---|
| `pl_ingesta` (Fuentes → PorFuente → Bronze → Silver → RefrescarSilver → Gold) | Todos los días a las 12:00 ART (15:00 UTC), con schedule | 4 a 15 minutos (13 al 17/11) |
| `nb_mlv`, `dbt_mart` | A mano, por ahora | Unos 7 minutos (`dbt_mart`) |

**Depende de:**
- la PC con el gateway, prendida y con internet: la actividad `Version` y la copia salen por el gateway (D18);
- el portal `datos.energia.gob.ar`;
- la capacidad trial (FTL4), que vence cerca del 2027-01-08.

## Objetivos de servicio (propios, no contractuales)

| Objetivo | Meta | Cómo se mide |
|---|---|---|
| Datos de prod actualizados antes de las 13:00 ART | 95 % de los días, en ventanas de 4 semanas | Consulta 4 (`a_tiempo_pct`) |
| Corridas programadas exitosas | 95 % | Consulta 4 (`exito_pct`) |
| Recuperación de una falla | El mismo día | Postmortem |

## Chequeo diario (13:00 ART)

No hay aviso automático de falla (D37), así que el chequeo es a mano:

1. En `oil-prod`, abrir **Monitoring KQL database** y correr la consulta 1.
2. Si `JobStatus` no es `Completed`, o no hay corrida de hoy, ir a la tabla de abajo.
3. Una vez por semana, consulta 4 (SLA) y la app **Fabric Capacity Metrics**: página *Health*, los últimos 7 días.

Sin el Eventhouse, el **Monitor hub** muestra lo mismo para una corrida suelta.

## Si falla

Primero, la consulta 3: qué actividad falló y con qué error.

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| `Version` o `BajarCSV`: *"Request didn't reach the server"* | El portal no responde, o la PC del gateway no tiene red | 1. Abrir el portal en el navegador. 2. En *Manage connections and gateways*, ver que el gateway esté **online**. 3. Guardar los logs del gateway de la PC (*On-premises data gateway* → *Diagnostics* → *Export logs*), para saber después cuál de las dos fue. 4. Cuando los dos anden, relanzar |
| El gateway figura **offline** | La PC está apagada o el servicio del gateway está parado | Prender la PC o el servicio y relanzar |
| Un notebook con 430 `TooManyRequestsForCapacity` | Todos los núcleos de Spark de la capacidad están ocupados (otra sesión abierta, `dbt_mart` corriendo) | Cerrar las sesiones interactivas, esperar y relanzar. No es falta de CU (D37) |
| `CapacityLimitExceeded` | Throttling: la capacidad consumió más de lo que tiene | En Capacity Metrics, página *Compute*: ver qué consumió. Esperar a que baje y relanzar |
| `Gold` falla en un control | `carga.cargar_gold` encontró un problema en los datos y deshizo la transacción. Gold queda con los datos anteriores | **No relanzar a ciegas.** Leer el mensaje del control, revisar silver y corregir el origen (D27) |
| `RefrescarSilver` falla | El refresco del SQL endpoint | Relanzar. Si se repite, ver la D26 |
| Todo inactivo | Venció el trial | Ver CLAUDE.md: hace falta una capacidad paga (decisión de Luis) |

## Cómo relanzar

En `oil-prod` → `pl_ingesta` → **Run**. Se hace desde el portal (prod no se toca por script).

**Relanzar es seguro:**
- la versión de cada fuente se registra después de bajar el archivo (`RegistrarVersion`, después de `BajarCSV`), así que lo que falló se vuelve a bajar;
- gold carga en una sola transacción.

## Después

Si se rompió un objetivo de servicio, se escribe un postmortem en esta carpeta, con el formato de
[`postmortem-2026-11-16.md`](postmortem-2026-11-16.md): sin culpables, con cronología, causa y acciones.

## Mantenimiento

- **Logs del monitoreo:** se guardan 30 días. Se cambia en la base KQL: *Manage* → *Data policies*.
- **Capacity Metrics:** la app refresca sola a la medianoche.
- **Trial:** vence cerca del 2027-01-08. Al vencer, los items quedan inactivos y OneLake guarda el contenido 7 días.
