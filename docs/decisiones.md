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
