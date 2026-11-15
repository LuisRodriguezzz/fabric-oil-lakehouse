CREATE TABLE [fact].[produccion_mensual] (
    [fecha_key]      INT        NOT NULL,
    [pozo_key]       BIGINT     NOT NULL,
    [empresa_key]    BIGINT     NOT NULL,
    [yacimiento_key] BIGINT     NOT NULL,
    [prod_pet]       FLOAT (53) NULL,
    [prod_gas]       FLOAT (53) NULL,
    [prod_agua]      FLOAT (53) NULL,
    [iny_agua]       FLOAT (53) NULL,
    [iny_gas]        FLOAT (53) NULL,
    [tef]            FLOAT (53) NULL,
    [edad_meses]     INT        NULL
);


GO