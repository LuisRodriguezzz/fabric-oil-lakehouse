CREATE PROCEDURE [control].[registrar_version]
@fuente VARCHAR (50), @version VARCHAR (40), @tamano_bytes BIGINT, @archivo VARCHAR (400), @corrida VARCHAR (64)
AS
BEGIN
    SET NOCOUNT ON;
    -- Anota una versión que ya quedó copiada en landing. Se llama después de la Copy, nunca antes:
    -- si la copia falla, la versión sigue sin anotar y la próxima corrida la vuelve a bajar.
    -- Si el pipeline se reintenta, no la anota dos veces.
    IF NOT EXISTS (SELECT 1
                   FROM control.version_cargada
                   WHERE fuente = @fuente AND version = @version AND tamano_bytes = @tamano_bytes)
        INSERT INTO control.version_cargada (fuente, version, tamano_bytes, archivo, corrida)
        VALUES (@fuente, @version, @tamano_bytes, @archivo, @corrida);
END
