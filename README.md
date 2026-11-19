# fabric-oil-lakehouse

Lakehouse de producción de pozos de Argentina (datos de la Secretaría de Energía) en **Microsoft
Fabric**, de punta a punta: ingesta, capas bronze, silver y gold, modelo semántico, reporte, CI/CD,
operación y un laboratorio de tiempo real. Es la tercera implementación del mismo dominio, después
de AWS (`argentina-oil-lakehouse-aws`) y Databricks (`databricks-oil-lakehouse`).

Las decisiones, con su porqué, la alternativa descartada y su equivalente en Azure, están en
[`docs/decisiones.md`](docs/decisiones.md).

## Las piezas

| Capa | En este proyecto (Fabric) | En Azure |
|---|---|---|
| Data Lake | Lakehouses en OneLake | ADLS Gen2 |
| Ingesta y orquestación | Pipeline de Fabric Data Factory, por un on-premises data gateway | Azure Data Factory con SHIR |
| Control de la ingesta | SQL database de Fabric (fuentes y versiones) | Azure SQL Database |
| Transformación | Notebooks PySpark (bronze y silver) | Databricks o Synapse Spark |
| Gold (Kimball) | Warehouse en T-SQL, carga transaccional | Synapse SQL pool |
| Marts | Materialized lake views y un dbt job | Synapse o dbt Core |
| Capa semántica y reporte | Modelo Direct Lake y reporte PBIR | Azure Analysis Services y Power BI |
| Configuración por ambiente | Variable library + `parameter.yml` | Parámetros del ARM template |
| CI/CD | GitHub Actions + `fabric-cicd`, service principal con OIDC | Azure DevOps + service connection |
| Operación | Workspace monitoring (KQL), Capacity Metrics, runbook | Azure Monitor y Log Analytics |
| Tiempo real (laboratorio) | Eventstream, Eventhouse, Real-Time Dashboard y Activator | Event Hubs, Data Explorer y Azure Monitor |

## Cómo llega un cambio a producción

```
rama + PR ──► pruebas.yml (pytest de silver) ──► merge a main ──► Update all en oil-dev
                                                     │
                                                     └──► desplegar.yml: aprobación del environment
                                                          oil-prod ──► azure/login (OIDC, sin
                                                          contraseña) ──► fabric-cicd ──► oil-prod
```

Tres workspaces: `oil-dev` (conectado a Git, rama `main`), `oil-feat` (una rama por tarea) y
`oil-prod` (sin Git: solo recibe despliegues).

## Estructura

```
docs/
  decisiones.md        decisiones numeradas (D1 a D39)
  operacion/           consultas KQL de monitoreo, runbook y postmortems (D37)
fabric/                items de Fabric, en carpetas del workspace (D31)
  00_control/
    sqldb_control.SQLDatabase/ fuentes y versiones cargadas; las fuentes, en un script post-deployment (D24)
    vl_oil.VariableLibrary/    lo que cambia por ambiente, un juego de valores por workspace (D26, D28)
  01_ingesta/
    pl_ingesta.DataPipeline/   portal → landing con watermark, bronze, silver, refresco y gold; schedule en .schedules
  02_bronze/
    lh_bronze.Lakehouse/       landing (Files) y tablas de texto de bronze (schema energia)
    nb_bronze.Notebook/        landing → tablas Delta: cada archivo una vez, leído por su encabezado
  03_silver/
    lh_silver.Lakehouse/       silver, más los marts (schemas mart y mart_dbt)
    nb_silver.Notebook/        bronze → silver: contrato, cuarentena y control de calidad
  04_gold/
    wh_gold.Warehouse/         gold: estrella en schemas dim y fact, carga en carga.cargar_gold (D27, D34)
    nb_mlv.Notebook/           marts de fractura con materialized lake views (D35)
    dbt_mart.DataBuildToolJob/ los mismos marts con dbt (D36)
  05_consumo/
    sm_oil.SemanticModel/      modelo Direct Lake on OneLake sobre wh_gold, con medidas (D29)
    rpt_oil.Report/            reporte de Power BI en formato PBIR, estilo editorial (D30)
  06_tiempo_real/              laboratorio con telemetría simulada; no va a prod (D38)
  parameter.yml                valores por ambiente para fabric-cicd (D20, D39)
tests/                 pytest de silver
.github/workflows/
  pruebas.yml          CI: los tests en cada PR y en cada push a main
  desplegar.yml        CD: oil-prod con fabric-cicd, OIDC y aprobación (D39)
azure-pipelines.yml    el mismo CD en Azure DevOps (escrito, sin correr)
```

## Scripts

| Rol | Script | Qué hace |
|---|---|---|
| Base | `fabric_api.py` | Cliente de la API de Fabric con un token de Entra ID; lo usan todos |
| Plataforma (una vez) | `plataforma.py` | Crea los workspaces en la capacidad y sus ajustes de Spark (D3, D6, D21) |
| | `conectar_git.py` | Conecta `oil-dev` a la rama `main`, carpeta `fabric/` (D4) |
| Operación | `correr.py` | Corre un notebook o un pipeline y espera el resultado |
| | `git_workspace.py` | Status, commit y update del workspace con Git, sin abrir el portal |
| | `contar_delta.py` | Cuenta las filas de una tabla leyendo su `_delta_log`, sin Spark |
| | `subir_a_landing.py` | Deja una entrega en landing, como lo haría el proveedor (D9) |
| CI/CD | `desplegar.py` | Despliega `fabric/` en un ambiente con `fabric-cicd`; `--previa` muestra los reemplazos sin publicar |
| Laboratorio | `simular_telemetria.py` | Manda telemetría simulada de pozos al Eventstream (D38) |

## Uso diario

```
$env:FABRIC_TENANT_ID = '<id del directorio>'
.venv\Scripts\python scripts\correr.py nb_bronze
.venv\Scripts\python scripts\contar_delta.py lh_bronze energia/produccion
.venv\Scripts\python scripts\git_workspace.py status
.venv\Scripts\python scripts\desplegar.py PROD --previa
```

## Plataforma

Requiere Python 3.10 o superior y acceso a una capacidad de Fabric.

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
set FABRIC_TENANT_ID=<id del directorio de Entra ID>
.venv\Scripts\python scripts\plataforma.py
```

Crea los workspaces en la capacidad. Es idempotente: se puede volver a correr sin duplicar nada.

```
.venv\Scripts\python scripts\conectar_git.py
```

Conecta `oil-dev` a la rama `main`, carpeta `fabric/`. Necesita antes una conexión de GitHub en
Fabric con un token *fine-grained* (solo este repo, Contents: Read and write). La primera vez
inicia sesión con un código de dispositivo; después usa la caché.
