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
- Cada archivo se lee con su propio encabezado y bronze acepta columnas nuevas (D15).
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

### D13. Bronze controla el encabezado de cada archivo contra un contrato (reemplazada por la D15)

La prueba de esta decisión sigue valiendo: asignar columnas por posición mezcla datos sin avisar.
Lo que cambió es la respuesta: frenar bronze ante un archivo distinto no sirve, porque que la
fuente sume columnas es un caso muy común.

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

### D15. Bronze acepta todo y lee cada archivo por su propio encabezado

- **Por qué:** bronze guarda todo lo que llega; qué columnas valen lo decide silver con su
  contrato (F3). El problema real de la D13 era asignar columnas por posición, y eso se resuelve
  leyendo por nombre, sin frenar la carga.
- **Cómo funciona:**
  1. El stream de archivos (`binaryFile`, solo la ruta) descubre lo nuevo; el checkpoint recuerda
     qué archivos ya procesó.
  2. En cada tanda (`foreachBatch`) cada CSV se lee solo, con su encabezado. Leer varios juntos
     no sirve: Spark toma el encabezado de uno y asigna el resto por posición.
  3. `unionByName(allowMissingColumns=True)` junta los archivos de la tanda, y Delta con
     `mergeSchema` suma las columnas nuevas. Todo entra como texto, con su linaje.
  4. Cada escritura lleva `txnAppId` y `txnVersion` (el número de tanda): si una tanda se
     reintenta, Delta no la escribe dos veces (verificado, Delta Lake: idempotent writes en
     `foreachBatch`). El `txnAppId` vive dentro del checkpoint: si alguien lo borra para
     reprocesar, las tandas vuelven a empezar en 0, y con el id viejo Delta las descartaría.
- **Dónde quedan:** en el schema `energia`, el sistema de origen (el portal de la Secretaría de
  Energía): `lh_bronze.energia.produccion` y `lh_bronze.energia.padron`.
- **Probado** en el sandbox (10/11, notebook `prueba_d15` en `chevron-lab`, con el mismo
  `nb_bronze`, archivos reales del proyecto de Databricks y dos sintéticos):

  | Caso | Resultado |
  |---|---|
  | Padrón con BOM | Primera columna `idpozo`, ningún nombre con BOM o `\r`, 0 nulos en `idpozo` |
  | Segunda corrida sin archivos nuevos | Sin cambios: mismas filas, una sola versión de Delta |
  | Entrega real con la columna nueva `pozo_horizontal` | La tabla pasa de 42 a 43 columnas; las 45.943 filas nuevas tienen valor y las 45.943 anteriores quedan en `null` |
  | `prod_pet` y `prod_gas` invertidas | `prod_pet = 200` y `prod_gas = 7`, como en el archivo |
  | Sin la columna `observaciones` | `observaciones` en `null`, el resto en su lugar |
  | Nombre con schema desde SQL | `` `chevron-lab`.lh_bronze.energia.produccion `` responde (91.888 filas) |

- **En `oil-dev` (10/11):** 45.943 filas en `produccion` y 86.197 en `padron`; una segunda
  corrida no cambió nada (una sola versión de Delta).
- **Lo que costó:** un stream necesita el esquema por adelantado aunque solo lea rutas ("Schema
  must be specified when creating a streaming source DataFrame"): se le da el esquema fijo de
  `binaryFile`.
- **No probado:** el reintento después de una falla a mitad de la escritura; se apoya en la
  garantía de Delta.
- **Casos borde abiertos:** un nombre de columna con caracteres que Delta no acepta (espacio,
  coma, punto y coma, llaves, paréntesis, `=`) haría fallar la escritura; y con miles de archivos
  por tanda, leer uno por uno sería lento (hoy llegan dos por mes).
- **En Azure:** en Databricks, Auto Loader lo trae armado: con `addNewColumns` (el modo por
  defecto) el stream se detiene al ver una columna nueva y, al reiniciar, la incluye; lo que no
  encaja va a `_rescued_data`. En ADF, los Mapping Data Flows tienen *Allow schema drift*. En
  Synapse Spark, este mismo código.

## Ingesta con Data Factory (F2)

### D16. `pl_ingesta`: watermark con una tabla de control en una SQL database

- **El problema:** el portal publica cada CSV siempre en la misma URL y lo reemplaza cuando
  corrige. Hay que darse cuenta del cambio y bajar la versión nueva sin perder la anterior.
- **La versión de una fuente** es el `last_modified` que informa la API CKAN (`resource_show`)
  más el tamaño (`size`). Si cambia cualquiera de los dos, es una versión nueva. Se compara por
  igualdad, como texto, nunca por orden: es la misma regla del manifiesto del proyecto de AWS.
  El tamaño cubre el caso de un contenido que cambia sin cambiar la fecha.
- **La tabla de control** vive en la SQL database `sqldb_control` (schema `control`):
  `fuente` (qué revisar: una fila por recurso de CKAN), `version_cargada` (qué se bajó, con
  archivo y corrida), la vista `fuente_a_revisar` (la última versión por fuente) y el stored
  procedure `registrar_version` (anota sin duplicar). Sumar una fuente es agregar una fila:
  pipeline guiado por metadatos.
- **La base es código:** Fabric la guarda en Git como proyecto `.sqlproj`; los objetos se
  escribieron como `.sql` y se aplicaron desde Git (Fabric compila un dacpac y publica solo las
  diferencias). Las filas de `control.fuente` no van en el proyecto: se cargaron a mano.
- **El pipeline** (armado en el lienzo):
  1. `Fuentes` (Lookup) lee `control.fuente_a_revisar`.
  2. `PorFuente` (ForEach, secuencial) recorre las filas.
  3. `Version` (Web) consulta `resource_show?id=<recurso>`.
  4. `CambioVersion` (If): `@or(not(equals(item().ultima_version, …last_modified)),
     not(equals(item().ultimo_tamano, …size)))`.
  5. Si cambió: `BajarCSV` (Copy binaria del portal a landing) y después `RegistrarVersion`
     (stored procedure). Primero se copia y después se anota: si la copia falla, la versión no
     queda anotada y la próxima corrida la vuelve a bajar.
  6. `Bronze` (Notebook `nb_bronze`), una vez, al terminar el ForEach.
- **Verificado (10/11):**
  - Primera corrida: padrón 1.172.135 bytes y producción 148.923.474 bytes; leídos = escritos =
    tamaño de CKAN.
  - Segunda corrida: `CambioVersion` dio falso en las dos fuentes y no se bajó nada.
  - Bronze sumó solo los archivos nuevos: `energia.produccion` pasó a 477.265 filas y
    `energia.padron` a 172.583.
- **Observado:** el monitor muestra `last_modified` con una "Z" final, pero lo que se guarda y se
  compara no la tiene (en `version_cargada` quedó `2026-11-10T09:02:43.691128`). Funciona porque
  siempre se compara lo que leyó el pipeline con lo que anotó el pipeline; nunca hay que comparar
  versiones leídas por dos herramientas distintas.
- **Casos borde abiertos:**
  - Si el stored procedure falla después de la Copy y el reintento es otro día, la misma versión
    se baja a otra carpeta de fecha y bronze la tiene dos veces. Silver se queda con una versión
    por pozo y mes, así que no cambia el resultado.
  - Las conexiones no van a Git: el pipeline las nombra por su ID. Para prod hay que cambiarlas
    (F8).
- **En Azure:** es el tutorial de carga incremental de ADF (tabla de watermark en Azure SQL,
  Lookup, Copy y Stored procedure). Diferencias:
  - La conexión de Fabric equivale al linked service.
  - En ADF la Copy usa datasets.
  - Las conexiones de Fabric viven fuera del workspace; los linked services, dentro del factory
    y en Git.

### D17. En landing, la carpeta es el día de descarga y el nombre es la versión

- Ruta: `landing/<fuente>/ingest_date=<AAAA-MM-DD>/<fuente>_<AAAAMMDDTHHMMSS>_<bytes>.csv`.
  Ejemplo: `padron/ingest_date=2026-11-11/padron_20261110T090243_1172135.csv`.
- **Por qué:** la carpeta dice cuándo lo bajamos; el nombre, qué versión es. Una corrección
  entra como archivo nuevo, al lado del anterior, y nada se pisa (D9). Pisar sería peor que
  perder historia: bronze recuerda los archivos por su ruta y no vería la corrección.
- **La fecha de ingesta va en UTC** (`pipeline().TriggerTime`): una corrida de las 21:15 de
  Argentina quedó en `ingest_date=2026-11-11`. Todas las fuentes de una corrida quedan con la
  misma fecha, y no depende de dónde ni a qué hora corre.
- **En Azure:** igual, con la expresión en el dataset de destino de la Copy.

### D18. El portal no acepta conexiones desde Azure: gateway en la compu

- **Lo que pasó:** la primera corrida falló en `Version` con "Request didn't reach the server".
- **La prueba** (notebook `prueba_red` en el sandbox, desde Spark de Fabric, IP pública
  `20.206.89.10`): el nombre del portal resuelve (`168.101.26.134`), pero las conexiones a los
  puertos 80 y 443 se cortan a los 15 s; `learn.microsoft.com` responde en 0,3 s. Desde una red
  de Argentina el portal responde. La causa exacta (filtro de IPs del portal) es una deducción.
- **La decisión:** un *on-premises data gateway* en la compu de Luis. El gateway sale hacia
  Azure y toma el trabajo: no hay que abrir puertos de entrada. La Web y la Copy usan conexiones
  "a través del gateway" (`oil-portal-energia-api-gw`, `oil-portal-energia-http-gw`); el Lookup,
  el stored procedure y el notebook siguen en la nube.
- **Lo que costó:** se registró primero en Brazil South, la región de la capacidad. El instalador
  avisó "Microsoft Fabric · No disponible fuera del entorno predeterminado" y la API
  `/gateways` vino vacía. Registrado en la región por defecto del tenant (South Central US),
  Fabric lo ve y la capacidad de Brazil South lo usa.
- **Costo aceptado:** la compu tiene que estar prendida cuando corre el pipeline. En producción
  va en una máquina siempre prendida, con dos o más nodos en clúster.
- **En Azure:** el *Self-hosted Integration Runtime*. El linked service HTTP lo usa con
  `connectVia`; es lo que se usa para traer datos de dentro de la red de la empresa.

## Silver (F3)

### D19. Silver: la última entrega, tipada y validada contra un contrato, con cuarentena

- **Qué hace `nb_silver`:** por cada fuente lee `lh_bronze.energia.<fuente>` y escribe
  `lh_silver.energia.<fuente>` (vigente), `<fuente>_cuarentena` y una fila en
  `control_calidad`. Es el diseño del proyecto de Databricks llevado a Fabric:
  1. **La última entrega manda.** Cada archivo del portal es una foto completa de la fuente:
     gana el de carpeta más nueva (y, el mismo día, el de nombre mayor).
  2. **Tipos con `try_cast`.** Lo que no convierte no rompe la carga: queda anotado en
     `_no_convierte` y el texto original en `_original`. Una columna del contrato que no vino
     queda nula y las reglas deciden.
  3. **Una versión por clave.** En producción gana la `fechaingreso` más nueva (la
     rectificativa); dos versiones distintas con la misma fecha van a cuarentena.
  4. **Reglas del contrato** como condiciones SQL; si una da falso o nulo, el nombre de la regla
     queda en `_motivos` y la fila va a cuarentena.
- **Control antes de publicar:** si una fuente no tiene filas vigentes o su cuarentena supera el
  umbral (1 %), la tabla vigente de esa fuente no se toca y el notebook falla al final: el
  pipeline se corta y lo que sigue queda con la última versión buena. La cuarentena se escribe
  igual, porque es lo que alguien tiene que mirar para entender la falla (cada fila trae su
  `_archivo`). Cada corrida suma su fila a `control_calidad`, con los motivos y las columnas que
  el contrato no conoce.
- **Qué se hace con la cuarentena y con una corrida que falla:**
  - Si el error es de la fuente (un valor negativo), se le avisa al proveedor. Cuando llega la
    entrega corregida, la fila sale sola de la cuarentena, porque silver se recalcula.
  - Si el error es del contrato (un valor válido que no previmos), se cambia la regla con un
    commit revisado y se vuelve a correr silver: bronze guarda todo, no hace falta volver a
    bajar nada.
  - Si una corrección es regla de negocio (por ejemplo, tratar −0,001 como 0), se escribe como
    transformación explícita en el contrato, nunca a mano sobre la tabla.
  - Si hay que volver atrás, Delta tiene `RESTORE TABLE … TO VERSION AS OF n`.
- **Se reescribe entera en cada corrida** (`overwrite`): silver es la foto de la última entrega
  y son menos de medio millón de filas. Delta guarda las versiones anteriores (time travel).
- **Un archivo Parquet por millón de filas:** la primera corrida dejó 431 mil filas en 200
  archivos (las 200 particiones por defecto de Spark después de las ventanas). Ahora se
  reparte antes de escribir: un archivo por tabla.
- **Las funciones se prueban con pytest** (`tests/test_silver.py`, 16 tests). El notebook es un
  `.py` válido: los tests lo importan y el bloque que escribe solo corre dentro de Fabric
  (`if __name__ == "__main__"`). Corrieron dentro del Spark de Fabric en el sandbox (Spark 4.1.1,
  Python 3.13): 16 pasaron. En GitHub los corre `.github/workflows/pruebas.yml`.
- **Resultado en `oil-dev` (10/11):**
  - `produccion`: 431.319 vigentes y 3 en cuarentena (0,0007 %), todas por
    `produccion_no_negativa`: gas de −12,267 y −7,519 en dos pozos de Pluspetrol (mayo de
    2020) y petróleo de −0,001 en uno de Petrobras (diciembre de 2008).
  - `padron`: 86.386 vigentes, ninguna en cuarentena.
  - El archivo completo de producción trae `coordenadax` y `coordenaday`, que el contrato no
    conoce: el control las informa y silver no las usa hasta decidir.
- **En Azure:** en Databricks son materialized views con *expectations* (el proyecto de
  Databricks); en Synapse Spark, este mismo notebook. En ADF, los Mapping Data Flows también
  pueden separar filas buenas y malas, sin código.
