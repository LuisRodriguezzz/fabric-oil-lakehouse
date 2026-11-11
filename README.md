# fabric-oil-lakehouse

Lakehouse de producción de pozos de Argentina (datos de la Secretaría de Energía) en **Microsoft
Fabric**, construido como se haría en el stack de **Azure**: Data Lake, Data Factory, Azure SQL,
Synapse con modelo Kimball, Analysis Services y CI/CD. Es la tercera implementación del mismo
dominio, después de AWS (`argentina-oil-lakehouse-aws`) y Databricks (`databricks-oil-lakehouse`).

Las decisiones, con su porqué y su equivalente en Azure, están en
[`docs/decisiones.md`](docs/decisiones.md).

## Equivalencias con Azure

| Capa | En este proyecto (Fabric) | En Azure |
|---|---|---|
| Data Lake | Lakehouses en OneLake | ADLS Gen2 |
| Ingesta y orquestación | Pipelines de Fabric Data Factory | Azure Data Factory |
| Base de datos de origen | SQL database de Fabric | Azure SQL Database |
| Transformación | Notebooks PySpark | Databricks o Synapse Spark |
| Transformación sin código | Dataflow Gen2 | Mapping Data Flows |
| Gold (Kimball) | Warehouse en T-SQL | Synapse SQL pool |
| Capa semántica | Modelo semántico | Azure Analysis Services |
| Repo y CI/CD | GitHub + deployment pipelines + `fabric-cicd` | Azure Repos + Azure Pipelines |

## Estructura

```
docs/decisiones.md   decisiones numeradas (D1 a D18), cada una con su equivalente en Azure
fabric/              items de Fabric (integración de Git del workspace oil-dev)
  lh_bronze.Lakehouse/   landing (Files) y tablas de texto de bronze (schema energia)
  lh_silver.Lakehouse/   silver (F3)
  nb_bronze.Notebook/    landing → tablas Delta: cada archivo una vez, leído por su encabezado
  pl_ingesta.DataPipeline/   portal → landing con watermark, y después nb_bronze (F2)
  sqldb_control.SQLDatabase/ fuentes y versiones cargadas, como proyecto SQL (F2)
scripts/
  plataforma.py          workspaces oil-dev y oil-prod en la capacidad
  conectar_git.py        oil-dev ↔ main/fabric
  git_workspace.py       status, commit y update del workspace con Git
  subir_a_landing.py     deja una entrega en landing (hace de proveedor hasta la F2)
  correr.py              corre un notebook o un pipeline y espera el resultado
  contar_delta.py        cuenta filas de una tabla leyendo su _delta_log
```

## Uso diario

```
$env:FABRIC_TENANT_ID = '<id del directorio>'
.venv\Scripts\python scripts\subir_a_landing.py produccion <archivo.csv> [AAAA-MM-DD]
.venv\Scripts\python scripts\correr.py nb_bronze
.venv\Scripts\python scripts\contar_delta.py lh_bronze energia/produccion
.venv\Scripts\python scripts\git_workspace.py status
```

## Plataforma

Requiere Python 3.10 o superior y acceso a una capacidad de Fabric.

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
set FABRIC_TENANT_ID=<id del directorio de Entra ID>
.venv\Scripts\python scripts\plataforma.py
```

Crea los workspaces `oil-dev` y `oil-prod` en la capacidad. Es idempotente: se puede volver a
correr sin duplicar nada.

```
.venv\Scripts\python scripts\conectar_git.py
```

Conecta `oil-dev` a la rama `main`, carpeta `fabric/`. Necesita antes una conexión de GitHub en
Fabric con un token *fine-grained* (solo este repo, Contents: Read and write). La primera vez
inicia sesión con un código de dispositivo; después usa la caché.
