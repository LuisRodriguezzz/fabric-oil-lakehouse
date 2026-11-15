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

## CI/CD (F8)

### D20. A prod se despliega desde el repo con `fabric-cicd`; Azure DevOps y GitHub Actions quedan escritos

- **Qué hace:** `scripts/desplegar.py PROD` publica en `oil-prod` lo que está en `fabric/`
  (Lakehouse, SQLDatabase, Notebook y DataPipeline) con `fabric-cicd` 1.4, la librería de
  Microsoft, y borra lo que esté en prod y ya no esté en el repo. Toma el repo, no `oil-dev`:
  Git manda (D11).
- **Referencias entre items:** en Git, el pipeline nombra a sus notebooks, al lakehouse y a la SQL
  database por su `logicalId`, con `workspaceId` en ceros ("el mismo workspace"). Son portables:
  se resuelven en el workspace de destino.
- **Conexiones:** viven en el tenant, no se despliegan y el pipeline las nombra por GUID.
  `fabric/parameter.yml` lista las tres y su valor por ambiente. En el laboratorio prod usa las
  mismas (misma fuente, mismo gateway); en una empresa tendría las suyas.
- **Identidad:** en la compu, tu usuario. En CI/CD, un service principal que entra sin contraseña
  (*workload identity federation* u OIDC). Ese service principal tiene que ser Contributor de
  `oil-prod`, y además hay que prender el switch de tenant "Service principals can use Fabric
  APIs".
- **Escrito, sin correr:**
  - `azure-pipelines.yml`, para Azure DevOps (pide suscripción, D4): etapa de tests, y etapa de
    prod con environment y aprobación.
  - `.github/workflows/desplegar.yml`: el mismo circuito en GitHub. Falta crear el service
    principal, y la cuenta de GitHub está bloqueada por facturación.
- **Primer despliegue (11/11), con el deployment pipeline `dp-oil`** (interfaz de Fabric, etapas
  Development = `oil-dev` y Production = `oil-prod`), seis items, `df_prueba` afuera:
  - Llegaron los seis, más los tres SQL endpoints que Fabric crea solo.
  - El `pl_ingesta` de prod apunta a los items **de prod** (notebooks, `lh_bronze` y
    `sqldb_control`) y al workspace `oil-prod`: el *auto-binding*, verificado leyendo su
    definición por la API.
  - `sqldb_control` de prod llegó con el esquema completo: el dacpac de prod tiene las 2 tablas,
    la vista, el stored procedure y las restricciones. Los datos no viajan: `control.fuente` de
    prod está vacía y los lakehouses de prod, sin datos.
  - `oil-prod` no está conectado a Git, igual que el ADF de prod: solo recibe despliegues.
- **Pendiente:** correr `scripts/desplegar.py` (el despliegue por código). El sistema lo frenó como
  "despliegue a producción" y necesita el OK explícito de Luis.
- **En Azure:** es el release de Azure DevOps que despliega el ARM template de ADF con una
  service connection y aprobación. Para Fabric desde Azure DevOps sería este mismo script.

## Operación (F7)

### D21. Los notebooks del pipeline comparten una sesión de Spark (alta concurrencia)

- **Qué es:** con el modo de alta concurrencia para pipelines, las actividades Notebook de un
  pipeline que llevan el mismo `sessionTag` (`ingesta`) corren en la misma sesión de Spark. La
  sesión arranca una vez y se factura solo la actividad que la inicia (verificado, [High
  concurrency in pipelines](https://learn.microsoft.com/en-us/fabric/data-engineering/configure-high-concurrency-session-notebooks-in-pipelines)
  y [High concurrency overview](https://learn.microsoft.com/en-us/fabric/data-engineering/high-concurrency-overview)).
- **Por qué:** `nb_bronze` y `nb_silver` corren seguidos. Con una sesión cada uno, la capacidad
  (4 CU) recibe dos pedidos de Spark por corrida, y ya devolvió errores 430.
- **Condiciones para compartir** (verificado): el mismo usuario, el mismo lakehouse por defecto (o
  ninguno: los dos notebooks no tienen), la misma configuración de Spark y las mismas librerías.
  Hasta 5 notebooks por sesión.
- **Es un ajuste del workspace, no un item:** el despliegue lleva items, no ajustes. `oil-dev` lo
  tenía y `oil-prod` no. Se prendió a mano en el portal el 12/11 (Workspace settings > Data
  Engineering/Science > Spark settings > High concurrency > "For pipeline running multiple
  notebooks") y se verificó por la API: `GET /workspaces/{id}/spark/settings` devuelve
  `highConcurrency.notebookPipelineRunEnabled = true`.
- **También como código:** `plataforma.py` lo revisa en cada workspace y lo prende si está apagado
  (D6). Se probó en dev, donde no cambió nada; el camino que lo prende no se probó, porque prod se
  prendió a mano.
- **Probado en dev:** en la corrida del 11/11 a las 19:33 UTC, `nb_bronze` y `nb_silver` tienen el
  mismo `livyId` con `isHighConcurrency: true` (API `notebooks/{id}/livySessions`). Antes, cada uno
  tenía su propia sesión. En prod se comprueba en la primera corrida.
- **Alternativa descartada:** sacar el `sessionTag` y dejar una sesión por notebook, con dos
  arranques y dos pedidos a la capacidad por corrida.
- **En Azure:** no encontré en la doc oficial de Synapse un ajuste equivalente para compartir la
  sesión entre las actividades Notebook de un pipeline.

### D22. El SQL endpoint no se refresca desde el pipeline (reemplazada por la D26)

Lo que sigue vale como historia: el refresco volvió como actividad nativa, con una Variable
library (D26), cuando gold empezó a leer silver por SQL.

- **Qué pasó:** F7 había sumado dos actividades "Refresh SQL endpoint" con el `workspaceId` y el
  `sqlEndpointId` de dev. Al desplegar con `dp-oil` (12/11), el *auto-binding* reasignó las
  actividades Notebook a los notebooks de prod, pero esas dos siguieron apuntando a dev
  (probado leyendo la definición por la API). Para pipelines no hay deployment rules (verificado,
  [create-rules](https://learn.microsoft.com/en-us/fabric/cicd/deployment-pipelines/create-rules)).
- **Primer arreglo:** `nb_refrescar_sql`, que refresca con semantic link
  (`refresh_sql_endpoint_metadata(warehouse="lh_silver", warehouse_type="Lakehouse")`) y resuelve
  el endpoint por el nombre del lakehouse en el workspace donde corre: sin IDs (D11). Anduvo en
  dev y en prod.
- **Lo que mostró prod (13/11):** en la primera corrida falló dos veces y anduvo a la tercera:
  1. `energia.produccion_cuarentena` devolvió el error 2714, *"There is already an object named
     'energia'… CREATE SCHEMA failed"*. Era la primera sincronización del schema en ese endpoint;
     que chocara con la sincronización de fondo es una deducción.
  2. El reintento pidió una sesión de Spark nueva y recibió 430 `TooManyRequestsForCapacity`: la
     excepción dejó la sesión compartida en estado Failed y la F4 todavía no la había liberado.
- **La decisión:** sacar el refresco del pipeline. La sincronización es automática y en general
  tarda menos de un minuto (verificado, [metadata sync](https://learn.microsoft.com/en-us/fabric/data-engineering/sql-analytics-endpoint-metadata-sync));
  forzarla solo sirve para un paso siguiente que lea por SQL, y hoy no hay ninguno. El notebook
  queda en el repo para la fase 4, antes de gold. Cuando vuelva: reintentar dentro de la misma
  sesión antes de fallar e imprimir una línea por tabla.
- **Costo aceptado:** el proceso de fondo se detiene tras 15 minutos sin consultas; la primera
  consulta después de un rato puede tardar en ver lo último.
- **Alternativas descartadas:**
  - Variable library con los GUID de cada ambiente: hay que cargarlos y cambian si el lakehouse se
    recrea (pasó en la D14). Además, la doc no confirma que ese campo acepte variables.
  - `$items.Lakehouse.lh_silver.$sqlendpointid` en `parameter.yml`: sirve con `fabric-cicd`
    (fase 2), no con `dp-oil`.
  - Corregir el GUID a mano en prod después de cada despliegue.
- **En Azure:** en Data Factory, lo que cambia por ambiente se reemplaza con los parámetros del
  ARM template al desplegar.

### D23. Cada cambio entra por una rama y un PR, desde un workspace de feature

- **Qué dice la doc:** *"Git best practice is for developers to have a separate runtime
  environment - a different workspace"* (verificado, [manage-branches](https://learn.microsoft.com/en-us/fabric/cicd/git-integration/manage-branches)).
  Después del merge, dev se actualiza desde Git y se promueve con el deployment pipeline
  ([manage-deployment](https://learn.microsoft.com/en-us/fabric/cicd/manage-deployment), opción 3).
- **Cómo:** `oil-feat` se creó con *Branch out* desde `oil-dev` y se reutiliza cambiándole la rama,
  como admite la doc para un solo desarrollador. El ciclo: rama → cambio y prueba en `oil-feat` →
  commit → PR en GitHub → merge → *Update all* en `oil-dev` → `dp-oil` a prod.
- **Límites:**
  - En `oil-feat` los lakehouses llegan vacíos, porque Git solo versiona metadatos. La prueba con
    datos se hace en `oil-dev` después del merge (criterio propio).
  - El trial admite 3 SQL databases: dev, prod y feat.
  - `main` no queda protegida por una regla: GitHub no aplica rulesets en un repo privado de una
    cuenta gratuita. La convención se sostiene por disciplina.
- **Lo que costó:** al actualizar dev, `DuplicateQueryName`: una consulta personal "SQL query 1"
  chocaba con el script que venía de Git. Se renombró la de dev, y el script pasó a llamarse
  `PostDeployment_fuentes`.
- **En Azure:** igual con Azure Repos: rama de feature, PR con branch policies, y Data Factory
  publica desde la collaboration branch.

### D24. `control.fuente` viaja como código: un script post-deployment

- **Qué hace:** `PostDeployment_fuentes.sql` es un `MERGE` que deja `control.fuente` igual a la
  lista del script. Fabric lo corre *"as part of any update from source control or deployment
  pipeline deployment"* (verificado, [source control de SQL database](https://learn.microsoft.com/en-us/fabric/database/sql/source-control)).
  Sin él, los despliegues llevan la estructura y no los datos: prod tenía la tabla vacía.
- **Cómo se registra:** en el editor de consultas, *Shared queries* > *Set as Post-deployment
  script*. Fabric escribe el `PostDeploy` en el `.sqlproj`; la doc avisa que lo que se edite a
  mano en ese archivo se pisa.
- **Idempotente y sin borrar:** se puede correr cuantas veces sea. Una fuente se apaga con
  `activa = 0`, así su historial en `version_cargada` (que tiene una clave foránea a `fuente`)
  queda.
- **Por qué los IDs de CKAN van escritos:** son los mismos en todos los ambientes y no son
  secretos: son la configuración del pipeline guiado por metadatos (D16), y su lugar es Git.
- **Probado:** el dacpac de prod incluye `postdeploy.sql` con el `MERGE`, y la primera corrida de
  prod leyó las 2 fuentes.
- **Alternativa descartada:** cargar las filas a mano en prod: no quedan en Git, cada ambiente
  puede terminar distinto y se pierden si la base se recrea.
- **En Azure:** igual, con un SQL project (dacpac) y su post-deployment script, desplegado con
  SqlPackage desde Azure DevOps.

### D25. Prod corre todos los días a las 12:00, con aviso de falla por mail

- **Schedule:** `pl_ingesta` de `oil-prod`, diario a las 12:00 (UTC-03:00). Solo prod: dev se
  corre a mano.
- **Por qué diario**, aunque el portal publique una vez por mes: con el watermark, un día sin
  cambios no baja nada, y cada corrida suma historial de operación (la fase 6 pide 4 semanas o
  más). Es a una hora con la compu prendida, por el gateway (D18).
- **Aviso de falla:** llega solo en corridas programadas (verificado, [alertas](https://learn.microsoft.com/en-us/fabric/data-factory/create-alerts-for-pipeline-runs)).
  La doc habla de *"users or groups"*; el usuario del tenant no tiene buzón (sin mail ni Exchange,
  verificado por Graph) y la dirección de Gmail queda marcada como externa. Que llegue se
  comprueba con la prueba de falla.
- **Primera corrida en prod (13/11, 02:08 UTC, manual):** 8,5 minutos; padrón 1.172.135 bytes y
  producción 148.923.474 bytes (leído = escrito); bronze 431.322 filas de producción y 86.386 de
  padrón; silver 431.319 vigentes y 3 en cuarentena, como dev.
- **Costo aceptado:** Bronze y Silver corren aunque no haya archivos nuevos. Saltearlos no es
  trivial: si una corrida baja un archivo y falla después, la siguiente no vería versión nueva y
  el archivo quedaría sin procesar.
- **En Azure:** un schedule trigger de Data Factory, con las alertas en Azure Monitor.

### D26. El refresco del SQL endpoint vuelve como actividad nativa, con una Variable library

- **Qué:** `RefrescarSilver` (actividad *Refresh SQL analytics endpoint*) con el workspace en
  `@pipeline().DataFactory` y el endpoint en `vl_oil.sql_endpoint_silver`, que tiene un valor por
  ambiente: Default (dev), FEAT y PROD. Cada workspace activa su juego una sola vez, y el
  despliegue no lo pisa (verificado, [Variable library CI/CD](https://learn.microsoft.com/en-us/fabric/cicd/variable-library/variable-library-cicd)).
  `@pipeline().DataFactory` devuelve el ID del workspace donde corre el pipeline (verificado,
  [expression language](https://learn.microsoft.com/en-us/fabric/data-factory/expression-language)).
- **Por qué volvió:** gold lee silver por el SQL endpoint y necesita que ya vea lo último. Entre
  las opciones, la actividad nativa es mejor que un notebook que prende una sesión de Spark para
  llamar a una API (y que, si falla, deja en Failed la sesión compartida) y mejor que una espera
  fija, que no garantiza nada. La doc recomienda una sola actividad de refresco, al final.
- **Probado:** en `oil-feat` resolvió el endpoint y el workspace de feat (13/11).
- **Alternativas descartadas:** el notebook con semantic link (D22), un *Wait*, y `parameter.yml`
  (sirve solo con `fabric-cicd`).
- **Riesgos a tener presentes:**
  - Si se recrea `lh_silver`, cambia el ID de su endpoint: se actualiza el valor en `vl_oil` por
    el ciclo de rama y PR.
  - Una variable nueva hereda el valor Default (el de dev) en todos los juegos y no da error: cada
    juego necesita su propio valor.
- **En Azure:** en Data Factory, lo que cambia por ambiente se reemplaza con los parámetros del
  ARM template al desplegar.

### D27. Gold en un Warehouse: estrella cargada por un stored procedure, en una transacción, con controles

- **Patrón:** bronze y silver en lakehouses, gold en un Warehouse (verificado, patrón 2 de
  [medallion](https://learn.microsoft.com/en-us/fabric/onelake/onelake-medallion-lakehouse-architecture)).
  Schemas `dim` y `fact` para lo que se lee y `carga` para el procedure: permiten dar permisos por
  schema y dejan nombres cortos en Power BI (criterio propio).
- **Tablas:** `dim.fecha` (clave `AAAAMM`); `dim.empresa` y `dim.yacimiento` (SCD tipo 1 con
  `MERGE`, más una fila `-1` "Sin dato"); `dim.pozo` (SCD tipo 2); `fact.produccion_mensual`.
- **SCD2:** los tramos se recalculan desde la historia mensual de silver (`LAG` para ver si
  cambió algo respecto del mes anterior y una suma acumulada para numerar los tramos), y se
  sincronizan con `MERGE` por `(idpozo, vigente_desde)`. Así entra una rectificación de un mes
  viejo, que un SCD2 incremental de "hoy contra ayer" no vería. Es el criterio de AWS.
- **Todo en una transacción**, con aislamiento snapshot: quien consulta durante la carga ve la
  versión anterior hasta el `COMMIT` (verificado, [transactions](https://learn.microsoft.com/en-us/fabric/data-warehouse/transactions)).
- **Controles antes de publicar:** filas del fact = filas de silver, un solo tramo actual por pozo
  y ningún tramo superpuesto. Si uno falla: `THROW`, `ROLLBACK`, y gold queda como estaba. Silver
  valida el dato que llega (con cuarentena); gold valida que el modelo quedó bien armado.
- **Lo que no tiene el Warehouse:** scripts post-deployment (los que se agregan por Git no se
  conservan), así que la fila `-1` la asegura el procedure con `IDENTITY_INSERT`. `IDENTITY` es
  solo `BIGINT` y no correlativo; PK y FK solo `NOT ENFORCED`.
- **Por qué recálculo completo y no incremental:** silver se pisa entera, el portal rectifica meses
  viejos y 431 mil filas se recalculan en segundos. Con los 21 años: una señal en silver
  (`_actualizado_en` y `_borrado`), un watermark de gold en su tabla de control, recálculo por
  pozo afectado y reconciliación contra el recálculo completo.
- **Imperativo y no declarativo:** el Warehouse no tiene tablas declarativas, y las lake views no
  hacen `MERGE` ni SCD2. El *dbt job* de Fabric existe (con estado contradictorio entre GA y
  preview) y queda como extra para comparar.
- **Resultado en `oil-feat` (14/11):** 431.319 filas en el fact, igual que silver; 23.032 tramos
  para 5.164 pozos. Pendiente: revisar qué atributo abre tantos tramos (unos 4,5 por pozo).
- **En prod (14/11):** la corrida completa cargó 431.319 filas en el fact del `wh_gold` de prod;
  RefrescarSilver y Gold resolvieron los valores de prod desde `vl_oil`.
- **Preview:** la integración de Git y los deployment pipelines del Warehouse.
- **En Azure:** es el *dedicated SQL pool* de Synapse: el mismo T-SQL, `IDENTITY` no correlativo
  y claves `NOT ENFORCED`.

### D28. Referencias entre ambientes: qué traduce Fabric y qué hay que parametrizar

- **La regla:** al commitear, Fabric cambia las referencias a items que están en Git por su
  `logicalId`, y el workspace por ceros ("este mismo workspace"). Al actualizar o desplegar, las
  vuelve a resolver en el workspace de destino. Todo lo demás (un GUID en un campo suelto, una
  dirección, una URL) viaja literal y sigue apuntando al ambiente donde se creó.
- **Lo que pasó en este proyecto:**

  | Referencia | ¿Se tradujo? |
  |---|---|
  | Actividades Notebook; Lookup y stored procedure a `sqldb_control`; Copy a `lh_bronze` | Sí |
  | *Refresh SQL endpoint* | No: el SQL endpoint no está en Git (D22, D26) |
  | Stored procedure a `wh_gold` | El ID sí; la dirección SQL (`endpoint`) no |
  | Conexiones del tenant | No, a propósito: son las mismas en todos los ambientes |

- **El caso de Gold (14/11):** en dev se conectó a la dirección de feat y pidió el warehouse de
  dev: error 18456, *"database was not found"*. Falló sin escribir en feat (verificado en su
  `_delta_log`). La dirección SQL es una por workspace: el lakehouse y el warehouse de un mismo
  workspace la comparten (verificado por la API).
- **El arreglo:** la conexión de Gold con contenido dinámico. *Connection (Warehouse ID)* =
  `vl_oil.wh_gold_id`, *SQL connection string* = `vl_oil.sql_host` y workspace =
  `@pipeline().DataFactory`. Con contenido dinámico, Fabric no completa ningún campo de esa
  conexión. Probado en feat (14/11): cargó el warehouse de feat y no tocó el de dev.
- **`PROD` de `wh_gold_id` en ceros** hasta que exista el `wh_gold` de prod: un valor de relleno
  tiene que fallar, nunca apuntar a otro ambiente.
- **Cómo detectarlo:**
  1. En el JSON de Git, buscar GUIDs que no sean un `logicalId`, ni ceros, ni una conexión, y
     direcciones `*.fabric.microsoft.com`.
  2. Abrir la actividad en el ambiente de destino y mirar a qué workspace apunta.
  3. Correr en el ambiente de abajo y ver dónde quedaron los datos.

  El primer punto se puede automatizar en CI (fase 2). La doc de `fabric-cicd` dice que las
  actividades que no usan el `logicalId` *"require parameterization"*.
- **Corrección:** la doc de la actividad Copy pide el ID de una conexión para un Warehouse
  dinámico; la actividad Stored procedure pide en ese campo el ID del warehouse. La conexión
  `oil-warehouse luis` quedó sin uso (limpieza).
- **En Azure:** los linked services de Data Factory se parametrizan, y el ARM template cambia los
  valores por ambiente.

## Consumo (fase 5)

### D29. Modelo semántico `sm_oil`: Direct Lake on OneLake sobre `wh_gold`, con parámetros por ambiente

- **Qué es:** un modelo creado desde el warehouse (*New semantic model*) en modo **Direct Lake on
  OneLake**: Power BI lee los archivos Delta de gold directo a memoria, sin copiarlos y sin pasar
  por SQL. Es *"the recommended Direct Lake option"* para modelos nuevos, y no cae a DirectQuery:
  si algo falla, da error (verificado, [Direct Lake](https://learn.microsoft.com/en-us/fabric/fundamentals/direct-lake-how-it-works)).
  Los *default semantic models* del warehouse ya no existen: el modelo se crea a propósito.
- **Tablas:** `fecha`, `empresa`, `yacimiento`, `pozo` y `produccion_mensual`. Toman los nombres
  cortos gracias a los schemas `dim` y `fact`. Que Direct Lake lea un schema distinto de `dbo` la
  doc no lo decía explícito: probado (`schemaName: dim`).
- **El modelo:**
  - 4 relaciones muchos a uno, en una sola dirección, de cada dimensión al fact.
  - Claves ocultas, sin suma en los atributos numéricos, y `fecha` marcada como tabla de fechas.
  - 6 medidas explícitas en la carpeta *Producción*, con la unidad en el nombre: m³, miles de m³ y
    barriles (m³ × 6,28981).
  - *Pozos que declararon* cuenta `pozo[idpozo]` y no `pozo_key`, porque `pozo_key` es un tramo
    del SCD2: un pozo que cambió de estado contaría dos veces.
- **Ambientes:** *"When you deploy a Direct Lake semantic model, it doesn't automatically bind to
  items in the target stage"*, y los modelos no están entre los items que usan la Variable library
  (verificado). Por eso la fuente se arma con dos parámetros M de texto, `WorkspaceId` y
  `WarehouseId`. En Git van los valores de dev, porque las reglas no se pueden crear en la etapa
  de desarrollo; en la etapa Production de `dp-oil`, una regla de parámetros pone los de prod.
  Consecuencia: el modelo de `oil-feat` lee el warehouse de dev mientras se desarrolla.
- **Refresco:** queda prendido *"Keep your Direct Lake data up to date"* (el default y lo que
  recomienda la doc): el modelo se reencuadra solo cuando cambia gold, que se carga en una sola
  transacción. Hace falta un refresh después del primer deploy a cada ambiente.
- **Probado en `oil-feat` (15/11):** 147.188.383 m³ de petróleo y 5.164 pozos, consultados con DAX.
- **Preview:** el modelo semántico en Git (TMDL).
- **Alternativas descartadas:**
  - Direct Lake on SQL endpoint: cae a DirectQuery sin avisar.
  - Import: copia los datos y necesita un refresco que los vuelva a copiar.
  - Un workspace aparte para consumo: queda para cuando haya usuarios de negocio con permisos
    propios.
- **En Azure:** un modelo de Azure Analysis Services, o de Power BI Premium en Import o DirectQuery
  sobre Synapse. Es una equivalencia general: la doc de Fabric no la compara.

### D30. Reporte `rpt_oil`: PBIR armado por código, con estilo editorial

- **Cómo se armó:** Fabric creó un reporte vacío sobre `sm_oil`, y a esa base se le agregaron por
  la API una página (1280×720), 10 visuales y un tema propio (`EditorialOil.json` en
  `RegisteredResources`). Se partió de una base real porque la doc no documenta los nombres
  internos de cada tipo de visual (verificado: PBIR es GA y es el formato por defecto,
  [projects-report](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-report)).
- **Estilo:** títulos en Georgia, textos y ejes en Segoe UI y grises, azul tinta `#2B5C8A` como
  único color de datos, sin bordes ni sombras y con grillas punteadas. Los títulos dicen algo, como
  en un artículo.
- **Contenido:** título y bajada; tarjetas de petróleo, gas y pozos que declararon; la evolución
  mensual del petróleo; el petróleo por cuenca; filtros de empresa y año; y la fuente al pie.
- **El título dice lo que muestran los datos:** "El petróleo no convencional en Argentina". La
  fuente de producción de hoy es la no convencional (la cuenca Neuquina tiene el 99,7 %); la
  producción completa es la fase 3.
- **"(Blank)" en los filtros:** no había datos vacíos ni filas huérfanas (verificado con DAX). Era
  la fila "desconocida" que el motor agrega a una dimensión por si el fact trae claves sin pareja.
  Se prendió *Assume referential integrity* en las 4 relaciones, porque gold la garantiza: claves
  `NOT NULL`, un *join* que exige el tramo del pozo, filas `-1` y el control de filas del fact
  ([relationships troubleshooting](https://learn.microsoft.com/en-us/power-bi/guidance/relationships-troubleshoot)).
  Con esa opción, una fila huérfana desaparecería en silencio: la responsabilidad pasa a gold.
- **Ambientes:** en Git, el reporte apunta al modelo por ruta (`byPath: ../sm_oil.SemanticModel`);
  `dp-oil` lo enlazó solo al `sm_oil` de prod. No necesita regla.
- **Probado (15/11):** `dp-oil` desplegó el reporte PBIR a prod, aunque la doc de deployment
  pipelines dice "PBIR reports aren't supported".
- **En Azure:** un reporte de Power BI sobre Azure Analysis Services, publicado con su archivo PBIX.

### D31. Los items del workspace se ordenan en carpetas por capa

- **Qué:** `00_control`, `01_ingesta`, `02_bronze`, `03_silver`, `04_gold` y `05_consumo`. Los
  números mantienen el orden del flujo.
- **Cómo viaja:** Git refleja las carpetas del workspace como subcarpetas de `fabric/` (verificado,
  [git-integration-process](https://learn.microsoft.com/en-us/fabric/cicd/git-integration/git-integration-process)).
  Los deployment pipelines crean la carpeta en el destino y mueven el item emparejado
  ([deployment process](https://learn.microsoft.com/en-us/fabric/cicd/deployment-pipelines/understand-the-deployment-process));
  una parte de eso figura como preview o como función de la interfaz nueva.
- **Lo que hubo que tocar:** el test de silver buscaba el notebook en una ruta fija; ahora lo busca
  dentro de `fabric/`, esté en la carpeta que esté.
- **Un PR aparte**, porque mover carpetas toca todos los items: si algo sale mal, se vuelve atrás
  sin arrastrar otros cambios.
- **Pendiente:** confirmar en la fase 2 que `fabric-cicd` publica items que están en subcarpetas.
- **En Azure:** las carpetas de Data Factory y de Synapse, que también se guardan en Git.
- **Comprobado (15/11):** `dp-oil` creó las 6 carpetas en prod y dejó cada item en la suya. El
  schedule de `pl_ingesta` en prod sobrevivió al deploy desde dev, que no tiene schedule.

### D32. Producción completa: 21 años, incremental por archivo y por año

- **Qué:** la fuente de producción pasa a ser la familia "DDJJ abiertas y cerradas" completa
  (2006-2026), la misma que usa el proyecto de AWS. El portal la publica en 21 CSV, uno por año, de
  unos 300 MB (6 GB en total). La fuente anterior (`produccion`, solo no convencional) se apaga con
  `activa = 0`; su tabla de bronze queda sin archivos nuevos.
- **Ingesta, incremental por archivo:** cada año es una fuente en `control.fuente`
  (`produccion_pozo_2006` … `_2026`), con la columna nueva `dataset = produccion_pozo`, que es la
  carpeta de landing y la tabla de bronze. Se baja solo el archivo cuya fecha o tamaño cambió.
  Los años viejos también cambian: en el último mes se rectificaron 9 de los 21.
  Alternativa descartada: bajar los 21 cada día (6 GB diarios por el gateway).
- **Bronze, append-only:** cada archivo es una versión completa del año. Se agrega
  `_version_origen` (la fecha de modificación del portal, sacada del nombre del archivo).
  Alternativa descartada: reemplazar el año en bronze, que pierde la historia y no se puede leer en
  streaming.
- **Silver, `MERGE` por año:** lee bronze en streaming (`availableNow` + checkpoint), se queda con la
  última foto de cada año (`_version_origen`) y, dentro de la foto, con la última declaración
  (`fechaingreso`). El `MERGE` borra lo que ya no viene con `WHEN NOT MATCHED BY SOURCE AND anio =
  <año>`: sin esa condición borraría los otros años. Alternativa descartada: reemplazar el año, que
  es más simple pero informa "cambió todo el año" y deja sin incremental a las capas de abajo. CDF
  prendido para las materialized lake views.
- **Cómo quedó construido:**
  - Bronze agrega `_fuente` (el recurso: `produccion_pozo_2006`) y le pone **liquid clustering**
    por `_fuente` (con estadísticas en esa columna, que por estar al final no las tendría), así
    silver lee la foto de un año sin recorrer los otros 20. Alternativa descartada: particionar.
    La doc de Fabric dice "avoid partitioning by default", pide al menos 1 GB por partición y
    desde el Runtime 2.0 recomienda liquid clustering para lecturas; la partición queda para
    aislar escritores concurrentes ([partitioning](https://learn.microsoft.com/en-us/fabric/data-engineering/delta-lake-partitioning),
    [liquid clustering](https://learn.microsoft.com/en-us/fabric/data-engineering/liquid-clustering)).
    Los archivos se agrupan con OPTIMIZE: va con el mantenimiento de bronze (retención).
  - El stream de silver solo avisa **qué años llegaron**; la foto se lee entera de bronze. Así, si
    un archivo quedara partido en dos tandas o llegara tarde una foto vieja, el resultado no cambia.
  - `_huella` (hash de los datos sin linaje): el `MERGE` actualiza solo si cambió el dato.
    `_actualizado_en` marca cuándo cambió de verdad: sirve para un gold incremental.
  - Si un año falla el control, la tanda falla y el checkpoint no avanza: la próxima corrida la
    repite, y el `MERGE` de los años que pasaron da el mismo resultado.
  - Regla nueva `anio_del_archivo`: una fila de otro año que el del archivo va a cuarentena,
    porque rompería el borrado acotado al año.
  - **Gold se cambia en un segundo PR (expandir y después contraer).** Al actualizar el Warehouse
    desde Git o con `dp-oil`, Fabric compila el proyecto SQL y exige que existan las tablas que el
    procedimiento lee en otro lakehouse (error SQL71561, "unresolved reference"). Si gold apunta a
    `produccion_pozo` antes de que silver la cree, el update falla. Orden: PR 1 (control, bronze,
    silver) → correr el pipeline en cada ambiente, que crea `produccion_pozo` → PR 2 (gold lee
    `produccion_pozo`) → más adelante, borrar `produccion` con OK. Mientras tanto gold sigue
    leyendo `produccion`, que queda congelada.
- **Primera corrida en `oil-feat` (15/11, 43 min):** 21 descargas de ~40 s cada una por el gateway
  (~8,7 MB/s), bronze 2,5 min, silver 9,8 min. Bronze `produccion_pozo` quedó con 18.409.048 filas
  y silver con 18.408.823 vigentes + 225 en cuarentena (suman exacto). Los 21 años pasaron el
  control (la cuarentena más alta, 2009 con 0,0044 %). AWS midió 18.234.202 filas el 2026-09-12:
  la diferencia son los meses de 2026 publicados después. Pendiente: silver quedó en 200 archivos
  (las particiones por defecto del MERGE); va con el mantenimiento (OPTIMIZE).
- **Supuestos:** cada CSV es la foto completa de un año; el portal cambia la fecha cuando cambia el
  archivo; la versión del origen se ordena por tiempo del origen, no por el de proceso
  (`_cargado_en`).
- **Gold:** sigue full (TRUNCATE + INSERT) hasta medirlo con 18 M de filas. Abierto: si el
  Warehouse puede leer el CDF de silver; si no, el incremental de gold necesita `_actualizado_en` y
  borrado lógico en silver.
- **Doc:** Runtime 2.0 trae Delta 4.2
  ([runtime-2-0](https://learn.microsoft.com/en-us/fabric/data-engineering/runtime-2-0)); `NOT
  MATCHED BY SOURCE` es de Delta 2.3 en adelante
  ([delta-update](https://docs.delta.io/latest/delta-update.html)); VACUUM borra también el CDF
  ([table maintenance](https://learn.microsoft.com/en-us/fabric/data-engineering/lakehouse-table-maintenance)).
- **En Azure:** ADF con tabla de control (Lookup + ForEach por archivo) y Databricks con Auto Loader
  y `MERGE` desde un stream con `foreachBatch`.

### D33. Fractura (Adjunto IV): una foto diaria que reemplaza silver entero

- **Qué:** el dataset `datos-de-fractura-de-pozos-adjunto-iv`, un CSV de ~1,3 MB (unas 5 mil
  operaciones de fractura) que el portal reemplaza entero todos los días, con la leyenda "datos
  preliminares sujetos a revisión". Se cruza con producción por `idpozo`.
- **Modo foto, no `MERGE`:** silver se reemplaza entero con la última entrega, como el padrón.
  Mismo criterio que en la D32, al revés: el `MERGE` se justifica cuando hay mucho volumen y
  alguien aguas abajo necesita saber qué cambió. Con 5 mil filas, reescribir todo cuesta segundos
  y es más simple. Alternativa descartada: `MERGE` con CDF.
- **Contrato:** clave `id_base_fractura_adjiv` (única; `idpozo` + fecha no alcanza: hay pozos con
  varias declaraciones el mismo día). Versión `fecha_data`. Rangos del contrato de AWS: presión
  hasta 20.000 psi (arriba es error de unidad, hay filas con 209.640), potencia hasta 100.000 HP,
  rama horizontal hasta 10.000 m, de 1 a 200 etapas. Las 41 filas con fin antes del inicio no se
  rechazan (el contrato valida columna por columna).
- **Bronze crece:** el archivo cambia todos los días, así que bronze suma ~5 mil filas por día
  (~1,8 M por año). Va con la retención de bronze, igual que producción.
- **Lo que sigue:** cruzar fractura con producción (la curva por pozo según su fractura) es el
  primer candidato a materialized lake view.
- **En Azure:** ADF con Copy diario a ADLS y un notebook de Databricks o Synapse que reemplaza la tabla.
