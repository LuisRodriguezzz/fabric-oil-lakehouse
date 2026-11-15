-- Post-deployment: las fuentes que revisa pl_ingesta.
-- Fabric lo corre después de cada despliegue de la base, en cada ambiente.
-- Es idempotente: deja la tabla igual a esta lista, corra una vez o cien.
-- Una fuente no se borra: se apaga con activa = 0 y su historial queda.
-- produccion (solo no convencional) se apagó en la D32: la reemplaza produccion_pozo, la
-- familia "DDJJ abiertas y cerradas" completa, un recurso CKAN por año (2006-2026).
MERGE control.fuente AS destino
USING (VALUES
    ('padron',               '5578dd48-d0dd-487e-8ddc-bd3ebb1afef0', 'padron',          1),
    ('produccion',           'b5b58cdc-9e07-41f9-b392-fb9ec68b0725', 'produccion',      0),
    ('produccion_pozo_2006', '532e9b21-3826-4083-9e25-27147b003696', 'produccion_pozo', 1),
    ('produccion_pozo_2007', '9310d724-a341-4740-be18-c87f03f8a462', 'produccion_pozo', 1),
    ('produccion_pozo_2008', 'feac6698-5c88-49e8-aa8a-733e7c70d644', 'produccion_pozo', 1),
    ('produccion_pozo_2009', '1cd8d21f-b420-4fba-a3c2-233ff57587f5', 'produccion_pozo', 1),
    ('produccion_pozo_2010', '8ee68ba4-2715-467c-af6f-233555520483', 'produccion_pozo', 1),
    ('produccion_pozo_2011', 'da9d4417-2be6-4585-8f35-f2e8078c20e5', 'produccion_pozo', 1),
    ('produccion_pozo_2012', 'a6c391c5-4b88-4702-8080-72ba7106a02b', 'produccion_pozo', 1),
    ('produccion_pozo_2013', '158e5054-0c3b-478a-bbb7-f2d91c522e49', 'produccion_pozo', 1),
    ('produccion_pozo_2014', '443d7488-1614-41bd-8dbd-82506e37e853', 'produccion_pozo', 1),
    ('produccion_pozo_2015', '36c4ca2b-8f9f-4bed-8ceb-ed9c8647f861', 'produccion_pozo', 1),
    ('produccion_pozo_2016', '8a7f0dff-5a1d-4b1e-a8df-e566a85c3c69', 'produccion_pozo', 1),
    ('produccion_pozo_2017', '97c81dbc-9db4-4a61-8e78-ee0a934fa620', 'produccion_pozo', 1),
    ('produccion_pozo_2018', '13e30415-a2ac-46fe-a8ff-9810d8323ac9', 'produccion_pozo', 1),
    ('produccion_pozo_2019', 'd7dd85a5-4268-43b3-9ce5-c713cbbec2dc', 'produccion_pozo', 1),
    ('produccion_pozo_2020', '508ce39a-00d0-4164-a997-7ad25dda1c1a', 'produccion_pozo', 1),
    ('produccion_pozo_2021', 'cc966108-e577-4043-b553-81173ef83816', 'produccion_pozo', 1),
    ('produccion_pozo_2022', 'ae8d5a47-5181-4add-a836-ac19fb104fe1', 'produccion_pozo', 1),
    ('produccion_pozo_2023', '4b31fa79-dc2d-4228-a6ac-7e804cb36d1d', 'produccion_pozo', 1),
    ('produccion_pozo_2024', '0a352dee-8b4e-4e95-b01e-5b8082ce22ac', 'produccion_pozo', 1),
    ('produccion_pozo_2025', '561279bf-1b7c-4fb1-9d39-9f3fb27ab237', 'produccion_pozo', 1),
    ('produccion_pozo_2026', '85d6e021-a00d-4997-b74e-0b9b43c547fe', 'produccion_pozo', 1)
) AS origen (fuente, recurso_ckan, dataset, activa)
ON destino.fuente = origen.fuente
WHEN MATCHED AND (destino.recurso_ckan <> origen.recurso_ckan
                  OR destino.activa <> origen.activa
                  OR ISNULL(destino.dataset, '') <> origen.dataset)
    THEN UPDATE SET recurso_ckan = origen.recurso_ckan, dataset = origen.dataset, activa = origen.activa
WHEN NOT MATCHED BY TARGET
    THEN INSERT (fuente, recurso_ckan, dataset, activa)
         VALUES (origen.fuente, origen.recurso_ckan, origen.dataset, origen.activa);
