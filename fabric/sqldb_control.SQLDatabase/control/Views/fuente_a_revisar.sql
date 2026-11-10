CREATE VIEW [control].[fuente_a_revisar]
AS
-- Lo que lee el Lookup del pipeline: cada fuente activa con la última versión que se cargó.
SELECT f.fuente,
       f.recurso_ckan,
       u.version      AS ultima_version,
       u.tamano_bytes AS ultimo_tamano
FROM control.fuente AS f
     OUTER APPLY (SELECT TOP (1) v.version, v.tamano_bytes
                  FROM control.version_cargada AS v
                  WHERE v.fuente = f.fuente
                  ORDER BY v.cargado_en DESC) AS u
WHERE f.activa = 1;
