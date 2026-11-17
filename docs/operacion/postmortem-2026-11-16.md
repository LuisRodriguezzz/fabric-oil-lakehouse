# Postmortem: la corrida programada del 16/11 falló al consultar el portal

Formato sin culpables: qué pasó, por qué y qué cambia. Horarios en ART (UTC-3).

## Resumen

La corrida programada de `pl_ingesta` en `oil-prod` falló a las 13:25. La actividad `Version`
no pudo llegar a `datos.energia.gob.ar` en ninguna de sus 69 llamadas. Prod quedó sin actualizar
hasta las 17:34, cuando una corrida manual terminó bien.

**Impacto:**
- Se rompió el objetivo de las 13:00 por 4 horas y media.
- El impacto en los datos fue bajo: el portal publica una vez por mes y ese día no había versiones nuevas que perder.

## Cronología

| Hora | Qué pasó |
|---|---|
| 12:00:31 | Arranca la corrida programada |
| 12:01 | `PorFuente` (ForEach secuencial sobre las 23 fuentes) llama a `Version` para la primera fuente: falla después de unos 30 s |
| 12:01 a 13:25 | 69 llamadas fallidas: 23 fuentes × 3 intentos (`retry: 2`, 60 s de espera). Todas con el mismo error |
| 13:25:38 | `pl_ingesta` termina en *Failed* |
| — | El aviso de falla configurado en el schedule no llegó al Gmail |
| 17:20 | Luis relanza a mano |
| 17:34 | La corrida manual termina bien |

## Qué decía el error

> Error calling the endpoint 'http://datos.energia.gob.ar' … Request didn't reach the server from
> the client. This could happen because of an underlying issue such as network connectivity, a
> DNS failure, a server certificate validation or a timeout.

El código fue `2108`. El error se repitió durante 84 minutos seguidos, así que no fue un corte de segundos.

## Causa

**No se pudo determinar.** Hay dos hipótesis compatibles con el error:

1. **El portal no respondía** desde la red del gateway: estaba caído o cortaba conexiones, como ya hace con las IPs de Azure (D18).
2. **La PC del gateway estaba prendida pero sin red**, o con un problema de DNS.

Es una inferencia, pero lo más probable es que el gateway en sí estuviera **online**. Si estaba
offline, el error habría sido otro: el de gateway no disponible. Para distinguir las dos
hipótesis faltaron los logs del gateway en la PC de ese momento.

## Qué salió bien

- Los reintentos funcionaron como estaban configurados.
- La corrida manual de la tarde anduvo sin cambios. Relanzar es seguro (ver el runbook).

## Qué salió mal

- **No se cortó a tiempo.** Con el portal inalcanzable, el ForEach siguió con las 23 fuentes y gastó 84 minutos en llamadas que no podían andar. Un ForEach secuencial no corta cuando falla un elemento.
- **Nadie se enteró en el momento.** El aviso del schedule no llegó al Gmail: Fabric avisa a usuarios del tenant, y el del tenant no tiene buzón (D37).
- **No había monitoreo** para reconstruir el incidente con consultas. Se armó con la API.

## Acciones

| Acción | Estado |
|---|---|
| Workspace monitoring en `oil-prod` y consultas KQL (`consultas.kql`) | Hecho, 17/11 |
| Chequeo diario a las 13:00 en el runbook, en lugar del aviso que no llega | Hecho, 17/11 |
| Cortar antes: una llamada de prueba al portal antes del ForEach, que haga fallar la corrida en un solo intento si no responde | Pendiente (cambio en `pl_ingesta`) |
| Ante el próximo error de red, guardar los logs del gateway de la PC para distinguir las dos hipótesis | Anotado en el runbook |
