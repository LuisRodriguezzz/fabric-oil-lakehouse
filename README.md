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
docs/decisiones.md   decisiones numeradas (D1, D2...)
scripts/             creación de la plataforma por la API REST de Fabric
fabric/              items de Fabric, escritos por la integración de Git del workspace oil-dev
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
