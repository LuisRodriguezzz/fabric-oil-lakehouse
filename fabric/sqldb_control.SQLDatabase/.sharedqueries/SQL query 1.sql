-- Post-deployment: las fuentes que revisa pl_ingesta.
-- Fabric lo corre después de cada despliegue de la base, en cada ambiente.
-- Es idempotente: deja la tabla igual a esta lista, corra una vez o cien.
-- Una fuente no se borra: se apaga con activa = 0 y su historial queda.
MERGE control.fuente AS destino
USING (VALUES
    ('padron',     '5578dd48-d0dd-487e-8ddc-bd3ebb1afef0', 1),
    ('produccion', 'b5b58cdc-9e07-41f9-b392-fb9ec68b0725', 1)
) AS origen (fuente, recurso_ckan, activa)
ON destino.fuente = origen.fuente
WHEN MATCHED AND (destino.recurso_ckan <> origen.recurso_ckan OR destino.activa <> origen.activa)
    THEN UPDATE SET recurso_ckan = origen.recurso_ckan, activa = origen.activa
WHEN NOT MATCHED BY TARGET
    THEN INSERT (fuente, recurso_ckan, activa)
         VALUES (origen.fuente, origen.recurso_ckan, origen.activa);
