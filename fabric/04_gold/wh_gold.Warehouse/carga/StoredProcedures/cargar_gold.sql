CREATE PROCEDURE carga.cargar_gold
AS
BEGIN
    SET NOCOUNT ON;
    BEGIN TRY
        BEGIN TRANSACTION;

        -- 1. dim.fecha: un mes por fila, del primer año con datos a diciembre del año que viene.
        TRUNCATE TABLE dim.fecha;
        WITH d AS (SELECT n FROM (VALUES (0),(1),(2),(3),(4),(5),(6),(7),(8),(9)) AS t(n)),
             numeros AS (SELECT a.n + 10 * b.n + 100 * c.n AS i FROM d a CROSS JOIN d b CROSS JOIN d c),
             meses AS (
                 SELECT DATEADD(MONTH, i, (SELECT DATEFROMPARTS(MIN(anio), 1, 1) FROM lh_silver.energia.produccion_pozo)) AS fecha
                 FROM numeros
             )
        INSERT INTO dim.fecha (fecha_key, fecha, anio, mes, trimestre)
        SELECT YEAR(fecha) * 100 + MONTH(fecha), fecha, YEAR(fecha), MONTH(fecha), DATEPART(QUARTER, fecha)
        FROM meses
        WHERE fecha <= DATEFROMPARTS(YEAR(GETDATE()) + 1, 12, 1);

        -- 2. Filas "Sin dato" (-1): el warehouse no corre scripts post-deployment, las asegura la carga.
        IF NOT EXISTS (SELECT 1 FROM dim.empresa WHERE empresa_key = -1)
        BEGIN
            SET IDENTITY_INSERT dim.empresa ON;
            INSERT INTO dim.empresa (empresa_key, idempresa, empresa) VALUES (-1, 'N/D', 'Sin dato');
            SET IDENTITY_INSERT dim.empresa OFF;
        END;
        IF NOT EXISTS (SELECT 1 FROM dim.yacimiento WHERE yacimiento_key = -1)
        BEGIN
            SET IDENTITY_INSERT dim.yacimiento ON;
            INSERT INTO dim.yacimiento (yacimiento_key, idareayacimiento, areayacimiento, cuenca, provincia)
            VALUES (-1, 'N/D', 'Sin dato', 'Sin dato', 'Sin dato');
            SET IDENTITY_INSERT dim.yacimiento OFF;
        END;
        IF NOT EXISTS (SELECT 1 FROM dim.estado WHERE estado_key = -1)
        BEGIN
            SET IDENTITY_INSERT dim.estado ON;
            INSERT INTO dim.estado (estado_key, tipoestado) VALUES (-1, 'Sin dato');
            SET IDENTITY_INSERT dim.estado OFF;
        END;

        -- 3b. dim.estado: el estado del pozo en el mes (Extracción Efectiva, Parado Transitoriamente...).
        --     Es una mini-dimensión: cambia casi todos los meses, así que cuelga del fact y no del
        --     SCD2 de dim.pozo, donde abría un tramo por cada parada (D34).
        INSERT INTO dim.estado (tipoestado)
        SELECT DISTINCT s.tipoestado
        FROM lh_silver.energia.produccion_pozo AS s
        WHERE s.tipoestado IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM dim.estado AS d WHERE d.tipoestado = s.tipoestado);

        -- 3. dim.empresa (SCD tipo 1): el nombre más reciente de cada idempresa.
        MERGE dim.empresa AS d
        USING (
            SELECT idempresa, empresa
            FROM (SELECT idempresa, empresa,
                         ROW_NUMBER() OVER (PARTITION BY idempresa ORDER BY anio DESC, mes DESC) AS rn
                  FROM lh_silver.energia.produccion_pozo
                  WHERE idempresa IS NOT NULL) AS x
            WHERE rn = 1
        ) AS s
        ON d.idempresa = s.idempresa
        WHEN MATCHED AND ISNULL(d.empresa, '') <> ISNULL(s.empresa, '')
            THEN UPDATE SET empresa = s.empresa
        WHEN NOT MATCHED BY TARGET
            THEN INSERT (idempresa, empresa) VALUES (s.idempresa, s.empresa);

        -- 4. dim.yacimiento (SCD tipo 1): los datos más recientes de cada yacimiento.
        MERGE dim.yacimiento AS d
        USING (
            SELECT idareayacimiento, areayacimiento, cuenca, provincia
            FROM (SELECT idareayacimiento, areayacimiento, cuenca, provincia,
                         ROW_NUMBER() OVER (PARTITION BY idareayacimiento ORDER BY anio DESC, mes DESC) AS rn
                  FROM lh_silver.energia.produccion_pozo
                  WHERE idareayacimiento IS NOT NULL) AS x
            WHERE rn = 1
        ) AS s
        ON d.idareayacimiento = s.idareayacimiento
        WHEN MATCHED AND CONCAT(d.areayacimiento, '|', d.cuenca, '|', d.provincia)
                      <> CONCAT(s.areayacimiento, '|', s.cuenca, '|', s.provincia)
            THEN UPDATE SET areayacimiento = s.areayacimiento, cuenca = s.cuenca, provincia = s.provincia
        WHEN NOT MATCHED BY TARGET
            THEN INSERT (idareayacimiento, areayacimiento, cuenca, provincia)
                 VALUES (s.idareayacimiento, s.areayacimiento, s.cuenca, s.provincia);

        -- 5. dim.pozo (SCD tipo 2): tramos recalculados desde la historia de silver, sincronizados por
        --    (idpozo, vigente_desde). Así entra una rectificación de un mes viejo.
        --    tipoestado ya no abre tramos (pasó a dim.estado) y queda en NULL: Git del Warehouse no
        --    deja borrar una columna de una tabla con datos (BlockOnPossibleDataLoss). D34.
        WITH historia AS (
            SELECT idpozo, DATEFROMPARTS(anio, mes, 1) AS mes_declarado,
                   sigla, tipopozo, tipoextraccion, tipo_de_recurso, sub_tipo_recurso,
                   formacion, profundidad, prod_pet, prod_gas,
                   CONCAT(sigla, '|', tipopozo, '|', tipoextraccion, '|', tipo_de_recurso,
                          '|', sub_tipo_recurso, '|', formacion, '|', CAST(profundidad AS VARCHAR(50))) AS huella
            FROM lh_silver.energia.produccion_pozo
        ),
        cambios AS (
            SELECT *, CASE WHEN LAG(huella) OVER (PARTITION BY idpozo ORDER BY mes_declarado) = huella
                           THEN 0 ELSE 1 END AS abre_tramo
            FROM historia
        ),
        numerados AS (
            SELECT *, SUM(abre_tramo) OVER (PARTITION BY idpozo ORDER BY mes_declarado
                                            ROWS UNBOUNDED PRECEDING) AS n_tramo
            FROM cambios
        ),
        tramos AS (
            SELECT idpozo, n_tramo, MIN(mes_declarado) AS vigente_desde,
                   MAX(sigla) AS sigla, MAX(tipopozo) AS tipopozo,
                   MAX(tipoextraccion) AS tipoextraccion, MAX(tipo_de_recurso) AS tipo_de_recurso,
                   MAX(sub_tipo_recurso) AS sub_tipo_recurso, MAX(formacion) AS formacion,
                   MAX(profundidad) AS profundidad
            FROM numerados
            GROUP BY idpozo, n_tramo
        ),
        primera AS (
            SELECT idpozo,
                   MIN(CASE WHEN ISNULL(prod_pet, 0) > 0 OR ISNULL(prod_gas, 0) > 0 THEN mes_declarado END)
                       AS primera_produccion
            FROM historia
            GROUP BY idpozo
        ),
        origen AS (
            SELECT t.idpozo, t.vigente_desde,
                   DATEADD(DAY, -1, LEAD(t.vigente_desde) OVER (PARTITION BY t.idpozo ORDER BY t.vigente_desde))
                       AS vigente_hasta,
                   CASE WHEN LEAD(t.vigente_desde) OVER (PARTITION BY t.idpozo ORDER BY t.vigente_desde) IS NULL
                        THEN CAST(1 AS BIT) ELSE CAST(0 AS BIT) END AS es_actual,
                   t.sigla, t.tipopozo, t.tipoextraccion, t.tipo_de_recurso,
                   t.sub_tipo_recurso, t.formacion, t.profundidad, p.primera_produccion
            FROM tramos t
            JOIN primera p ON p.idpozo = t.idpozo
        )
        MERGE dim.pozo AS d
        USING origen AS s
        ON d.idpozo = s.idpozo AND d.vigente_desde = s.vigente_desde
        WHEN MATCHED AND (
                 ISNULL(d.vigente_hasta, '9999-12-31') <> ISNULL(s.vigente_hasta, '9999-12-31')
              OR d.es_actual <> s.es_actual
              OR ISNULL(d.primera_produccion, '1900-01-01') <> ISNULL(s.primera_produccion, '1900-01-01')
              OR d.tipoestado IS NOT NULL
              OR CONCAT(d.sigla, '|', d.tipopozo, '|', d.tipoextraccion, '|', d.tipo_de_recurso,
                        '|', d.sub_tipo_recurso, '|', d.formacion, '|', CAST(d.profundidad AS VARCHAR(50)))
              <> CONCAT(s.sigla, '|', s.tipopozo, '|', s.tipoextraccion, '|', s.tipo_de_recurso,
                        '|', s.sub_tipo_recurso, '|', s.formacion, '|', CAST(s.profundidad AS VARCHAR(50))))
            THEN UPDATE SET vigente_hasta = s.vigente_hasta, es_actual = s.es_actual,
                            sigla = s.sigla, tipoestado = NULL, tipopozo = s.tipopozo,
                            tipoextraccion = s.tipoextraccion, tipo_de_recurso = s.tipo_de_recurso,
                            sub_tipo_recurso = s.sub_tipo_recurso, formacion = s.formacion,
                            profundidad = s.profundidad, primera_produccion = s.primera_produccion
        WHEN NOT MATCHED BY TARGET
            THEN INSERT (idpozo, vigente_desde, vigente_hasta, es_actual, sigla, tipoestado, tipopozo,
                         tipoextraccion, tipo_de_recurso, sub_tipo_recurso, formacion, profundidad,
                         primera_produccion)
                 VALUES (s.idpozo, s.vigente_desde, s.vigente_hasta, s.es_actual, s.sigla, NULL,
                         s.tipopozo, s.tipoextraccion, s.tipo_de_recurso, s.sub_tipo_recurso, s.formacion,
                         s.profundidad, s.primera_produccion)
        WHEN NOT MATCHED BY SOURCE
            THEN DELETE;

        -- 6. fact.produccion_mensual: se reescribe entera; cada mes va al tramo vigente del pozo.
        TRUNCATE TABLE fact.produccion_mensual;
        INSERT INTO fact.produccion_mensual (fecha_key, pozo_key, empresa_key, yacimiento_key,
                                             prod_pet, prod_gas, prod_agua, iny_agua, iny_gas, tef, edad_meses,
                                             estado_key)
        SELECT s.anio * 100 + s.mes,
               p.pozo_key,
               ISNULL(e.empresa_key, -1),
               ISNULL(y.yacimiento_key, -1),
               s.prod_pet, s.prod_gas, s.prod_agua, s.iny_agua, s.iny_gas, s.tef,
               DATEDIFF(MONTH, p.primera_produccion, DATEFROMPARTS(s.anio, s.mes, 1)),
               ISNULL(st.estado_key, -1)
        FROM lh_silver.energia.produccion_pozo AS s
        JOIN dim.pozo AS p
          ON p.idpozo = s.idpozo
         AND DATEFROMPARTS(s.anio, s.mes, 1) >= p.vigente_desde
         AND (p.vigente_hasta IS NULL OR DATEFROMPARTS(s.anio, s.mes, 1) <= p.vigente_hasta)
        LEFT JOIN dim.empresa AS e ON e.idempresa = s.idempresa
        LEFT JOIN dim.yacimiento AS y ON y.idareayacimiento = s.idareayacimiento
        LEFT JOIN dim.estado AS st ON st.tipoestado = s.tipoestado;

        -- 7. Controles antes de publicar: si alguno falla, THROW -> ROLLBACK y gold queda como estaba.
        DECLARE @silver BIGINT = (SELECT COUNT(*) FROM lh_silver.energia.produccion_pozo);
        DECLARE @fact   BIGINT = (SELECT COUNT(*) FROM fact.produccion_mensual);
        IF @fact <> @silver
            THROW 50001, 'gold: fact.produccion_mensual no tiene las mismas filas que silver (un mes sin tramo o con dos).', 1;

        IF EXISTS (SELECT idpozo FROM dim.pozo GROUP BY idpozo HAVING SUM(CAST(es_actual AS INT)) <> 1)
            THROW 50002, 'gold: hay pozos sin tramo actual o con mas de uno.', 1;

        IF EXISTS (SELECT 1
                   FROM (SELECT vigente_desde,
                                LAG(vigente_hasta) OVER (PARTITION BY idpozo ORDER BY vigente_desde) AS hasta_anterior
                         FROM dim.pozo) AS t
                   WHERE t.hasta_anterior >= t.vigente_desde)
            THROW 50003, 'gold: hay tramos de dim.pozo que se superponen.', 1;

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
        THROW;
    END CATCH;
END;

GO