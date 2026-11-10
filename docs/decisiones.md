# Decisiones

Cada decisión dice qué se decidió, por qué, y cómo sería en Azure, que es el stack del aviso de
Chevron. Marcas: **verificado** = leído en Microsoft Learn o probado en este proyecto;
**criterio propio** = decisión de diseño sin una fuente que la imponga.

## Base del proyecto (F0)

### D1. El mismo dominio que los proyectos de AWS y Databricks

Producción mensual por pozo y padrón de pozos con su primera producción, de la Secretaría de
Energía. El objetivo es aprender el stack de Azure del aviso: con el mismo dominio, lo único nuevo
es la tecnología, y las tres implementaciones se pueden comparar pieza por pieza.

### D2. Fabric en lugar de Azure, con la equivalencia anotada

No hay suscripción de Azure: la cuenta gratis no es elegible y el pago por uso se descartó. Fabric
tiene las mismas piezas como servicio, y Microsoft presenta a Fabric Data Factory como "la próxima
generación de Azure Data Factory" (verificado, "Differences between Data Factory in Fabric and
Azure"). Cada decisión dice cómo sería en Azure; el resumen está en el README.

### D3. Un workspace por ambiente: `oil-dev` y `oil-prod`

- **Qué es un workspace:** el contenedor de los items de Fabric (lakehouses, notebooks,
  pipelines, warehouse) con sus permisos. Se asigna a una **capacidad**, que es el cómputo que se
  paga; acá, la prueba de 60 días en Brazil South.
- **Por qué dos:** en producción no se desarrolla sobre lo que consume el negocio. Lo que se
  prueba en dev se promueve a prod con un despliegue.
- **Por qué no uno por capa:** la doc de medallion en Fabric recomienda un lakehouse por capa y,
  además, un workspace por capa (verificado, "Implement medallion lakehouse architecture"). Para
  una persona alcanza con un workspace por ambiente y un lakehouse por capa (criterio propio; se
  revisa si el equipo crece).
- **En Azure:** un resource group, o una suscripción, por ambiente, cada uno con su storage
  account, su Data Factory y su workspace de Synapse o Databricks.

### D4. GitHub como repo, con la integración de Git de Fabric en `oil-dev`

- **Qué hace la integración:** versiona el workspace. Cada item queda como una carpeta con su
  definición (un notebook como `.py`, un pipeline como JSON). Se conecta por workspace, y cada
  workspace a **una sola rama** (verificado, "Manage branches").
- **Cómo:** `oil-dev` conectado a `main`, en la carpeta `fabric/`. Lo que no se versiona son los
  datos: de un lakehouse solo se guardan metadatos, no tablas ni archivos (verificado, "Lakehouse
  git integration").
- **Por qué GitHub y no Azure DevOps:** crear una organización de Azure DevOps exige una
  suscripción de Azure (verificado, "Create an organization", 3/3/2026).
- **Cómo se conecta:** con `scripts/conectar_git.py`, por la API (`git/connect` y
  `git/initializeConnection`), idempotente. El token de GitHub no pasa por el repo: vive en una
  **conexión** de Fabric (`luis-github`, tipo GitHubSourceControl) que se crea una vez desde el
  portal. Es un token *fine-grained* con un solo repo y solo **Contents: Read and write**, el mínimo
  que pide la doc.
- **Lo que costó (9/11):**
  - El switch de tenant "Users can sync workspace items with GitHub repositories" venía apagado;
    lo prende un administrador de Fabric (rol de Entra ID). Con GitHub no se aplican las
    restricciones multi-geo, así que el switch de "otras ubicaciones geográficas" no hace falta.
  - Por la API, la carpeta tiene que existir en la rama: sin `fabric/` respondió
    `GitProviderResourceNotFound`. Por eso `fabric/README.md`.
  - Verificado: estado `ConnectedAndInitialized`, rama `main`, carpeta `/fabric`; la segunda
    corrida del script no cambia nada.
- **En Azure:** Azure Repos, con la misma integración de Git, sin token: se autentica con la cuenta
  de Entra ID o con un service principal. Los switches de tenant equivalen a lo que en Azure se
  gobierna con Azure Policy.

### D5. Despliegue a prod: deployment pipelines y `fabric-cicd`; Azure Pipelines queda escrito

- Microsoft documenta varias opciones y no impone una (verificado, "CI/CD workflow options in
  Fabric"). La de "release compartido" despliega con `fabric-cicd`, una librería de Python de
  Microsoft, y cambia los valores de cada ambiente con un `parameter.yml`.
- Usamos los **deployment pipelines** de Fabric (lo nativo, de workspace a workspace) para
  entender la promoción, y `fabric-cicd` desde la laptop para el despliegue por código.
- El `azure-pipelines.yml` queda escrito como correría en Azure DevOps y marcado como "sin correr".
- **En Azure:** Data Factory se despliega con los ARM templates que genera al publicar, desde un
  pipeline de Azure DevOps con una service connection.

### D6. La plataforma se crea con la API REST, con un script idempotente

- `scripts/plataforma.py` crea los workspaces de cada ambiente y los asigna a la capacidad. Si ya
  existen, no los toca.
- **Por qué no a mano:** lo que se hace a mano no se puede repetir ni revisar.
- **Por qué no Terraform:** el aviso no lo pide. Microsoft lo documenta para Fabric, pero el
  proveedor "no está cubierto por las políticas de soporte de Microsoft" (verificado, README de
  `microsoft/terraform-provider-fabric`).
- **En Azure:** Bicep o ARM templates, que son lo nativo, o la CLI `az`.

### D7. Autenticación: tu usuario de Microsoft Entra ID, por ahora

- Los scripts piden un token de Entra ID con `azure-identity`, con **código de dispositivo**: la
  primera vez imprimen una dirección y un código para iniciar sesión, y después toman el token de
  una caché cifrada que queda fuera del repo. Se eligió este flujo porque el que abre el navegador
  dependía de que la ventana apareciera y se cortó a los 5 minutos (probado el 9/11).
- El mismo inicio de sesión sirve para la API de Fabric y para OneLake, que solo acepta tokens con
  audiencia Storage, igual que ADLS (verificado, "How do I connect to OneLake?").
- Para desplegar desde un pipeline de CI/CD hace falta un service principal (F8).
- **En Azure:** igual, con Entra ID. En Azure DevOps, el service principal va en una service
  connection.

## Data Lake y bronze (F1)

### D8. Un lakehouse por capa: `lh_bronze` y `lh_silver`

- **Qué es un lakehouse:** un item de Fabric con dos zonas en OneLake: `Files/` para archivos
  sueltos (cualquier formato) y `Tables/` para tablas Delta, que se pueden consultar con Spark y
  con SQL.
- **Por qué uno por capa:** la doc de medallion en Fabric pide separar cada capa en su propio
  lakehouse (verificado). Así cada capa tiene sus permisos y no se mezclan datos crudos con datos
  limpios. Gold va a ser un **Warehouse** (F5), el segundo patrón de esa doc.
- **Cómo se crearon:** por la API en `oil-dev` y guardados en Git desde el workspace
  (`git_workspace.py commit`). En el repo, un lakehouse es solo metadatos (`.platform`,
  `lakehouse.metadata.json`): sus datos nunca van a Git (verificado en el commit `a20ae4a`).
- **En Azure:** un storage account de ADLS Gen2 con un container por capa (o un storage account
  por capa si se necesitan permisos o redes distintas).

### D9. Landing dentro de `lh_bronze/Files`, por fuente y fecha de entrega, inmutable

- Ruta: `Files/landing/<fuente>/ingest_date=AAAA-MM-DD/<archivo>`.
- **Por qué `ingest_date=` en la carpeta:** Spark la lee como una columna (`ingest_date`), así
  cada fila sabe de qué entrega vino. Es lo mismo que la D4 del proyecto de Databricks.
- **Por qué inmutable:** si la fuente corrige datos, llega un archivo nuevo en otra fecha y bronze
  guarda las dos versiones; elegir la vigente es trabajo de silver. `subir_a_landing.py` se niega
  a pisar un archivo que ya existe (probado el 9/11).
- **Quién escribe en landing:** en producción, el pipeline de Data Factory que copia desde el
  portal (F2). Hasta entonces, `subir_a_landing.py` hace de proveedor.
- **En Azure:** un container `landing` en ADLS con las mismas carpetas; la actividad Copy de Azure
  Data Factory escribe ahí.

### D10. Bronze con Structured Streaming y checkpoint: cada archivo entra una sola vez

- `nb_bronze` lee landing como un stream de archivos con `trigger(availableNow=True)`: procesa
  lo que todavía no procesó y termina. El **checkpoint** (`Files/_checkpoints/bronze_<fuente>`)
  guarda qué archivos ya leyó; volver a correr el notebook no duplica filas.
- Todo como texto, más el linaje: `_archivo`, `ingest_date`, `_cargado_en`. Tipar y validar es
  trabajo de silver, igual que en Databricks.
- **Por qué no Auto Loader:** es de Databricks; Fabric corre Spark abierto, y el stream de
  archivos con checkpoint es la versión de Spark de la misma idea.
- El esquema sale de un contrato por fuente (D13), no de los archivos.
- **En Azure:** Databricks con Auto Loader, o Synapse Spark con este mismo código.

### D11. Los notebooks son código en el repo; el workspace se actualiza desde Git

- `fabric/nb_bronze.Notebook/notebook-content.py` se escribe en el repo y se lleva a `oil-dev`
  con `git_workspace.py update`. El repo es la fuente de verdad.
- **Sin IDs en el código:** el notebook arma las rutas con el nombre del workspace donde corre
  (`notebookutils.runtime.context`), así el mismo código sirve en `oil-dev` y en `oil-prod`.
- **En Azure:** Synapse y ADF tienen la misma integración de Git; en Databricks, el bundle.

### D12. Operar desde la terminal con la API

- `git_workspace.py` (status, commit, update) es el panel "Source control" del portal.
- `correr.py` corre un notebook o un pipeline y espera el resultado (API de Job Scheduler).
- **En Azure:** `az datafactory pipeline create-run` o la API de ADF; en Databricks, la CLI.

### D13. Bronze controla el encabezado de cada archivo contra un contrato

- **El problema:** cuando se le da el esquema a un lector de CSV, Spark por defecto
  (`enforceSchema=True`) ignora el encabezado y asigna las columnas **por posición**. Si la
  fuente invierte dos columnas, bronze las mezcla sin avisar; si agrega una, la descarta.
- **Probado** en el sandbox (9/11, notebook `prueba_encabezados` en `chevron-lab`): con el
  encabezado `idpozo,prod_gas,prod_pet`, el pozo con 200 de petróleo y 7 de gas quedó con
  `prod_pet = 7`, y la columna extra `prod_agua` desapareció. Con `enforceSchema=False`, los dos
  casos fallan nombrando el archivo, y un archivo correcto pasa.
- **La decisión:** cada fuente declara su contrato (`CONTRATOS` en `nb_bronze`: las columnas en
  orden) y el stream lee con `enforceSchema=False`. Si un archivo no coincide, la carga falla; el
  archivo queda en landing, alguien decide, cambia el contrato con un commit y vuelve a correr.
  El checkpoint no registra la tanda fallida, así que el archivo se reprocesa.
- **Costo aceptado:** un archivo distinto frena la carga de esa fuente hasta que alguien lo mire.
  Con una entrega por mes, es preferible a datos mezclados.
- **El BOM no estorba:** el archivo del padrón empieza con los bytes `EF BB BF`, pero el lector
  de líneas de Spark los saca antes de comparar. Ya no hace falta limpiarlo a mano.
- **Verificar el verificador:** `count()` no sirve para probar el contrato, porque sin columnas
  pedidas Spark no parsea el CSV y no controla el encabezado (un contrato mal a propósito dio OK).
  La prueba válida lee todas las columnas.
- **En Azure:** con Databricks, Auto Loader trae evolución de esquema y la columna
  `_rescued_data` para lo que no encaja; con Synapse Spark o este mismo código, el contrato y
  `enforceSchema=False` como acá.

### D14. Lakehouses con schemas: se recrearon `lh_bronze` y `lh_silver`

- **Qué es un schema en un lakehouse:** un nivel de nombres dentro de `Tables/`, como el schema de
  SQL. La tabla queda en `Tables/<schema>/<tabla>` y se nombra `lh_bronze.dbo.produccion`.
- **Por qué:** ordena las tablas por fuente o por tema, y las *materialized lake views* (el extra
  después de la F5) los exigen (verificado, "Lakehouse schemas").
- **Por qué recrear:** un lakehouse sin schemas no se convierte (verificado). En el portal vienen
  activados; por la API, solo si se pide `"creationPayload": {"enableSchemas": true}`, y los
  nuestros se habían creado sin eso.
- **Cómo (10/11):**
  1. Se compararon los dos CSV de landing con sus copias locales: SHA-256 idéntico, así que no
     se perdía ninguna entrega.
  2. Se borraron los dos lakehouses y se crearon de nuevo con la API.
  3. Se devolvieron las entregas del 9/11 a landing con `subir_a_landing.py`.
  4. Commit desde el workspace (`d8ca117`).
- **En Git:** la marca es `lakehouse.metadata.json` = `{"defaultSchema":"dbo"}`.
- **Lo que costó:**
  - El nombre de un item borrado no queda libre al instante (`ItemDisplayNameNotAvailableYet`), y
    el SQL endpoint de `lh_silver` falló tres veces antes de crearse: se reintenta cada 30
    segundos.
  - Como el commit tenía el item viejo borrado y el nuevo con el mismo nombre, Fabric guardó las
    carpetas con el GUID. Se renombraron en el repo (`ca86abf`) y el workspace se actualizó sin
    cambios: Fabric reconoce cada item por el `logicalId` de su `.platform`, no por la carpeta
    (probado).
- **Pendiente:** las tablas de bronze se reconstruyen con el `nb_bronze` nuevo (D15), ya con
  schema. Hasta entonces `nb_bronze` no se corre: todavía escribe en `Tables/<fuente>`.
- **En Azure:** en Databricks, los schemas de Unity Catalog (`catalogo.schema.tabla`, como en el
  proyecto de Databricks); en Synapse o Azure SQL, los schemas de SQL.
