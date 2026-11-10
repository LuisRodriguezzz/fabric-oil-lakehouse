CREATE TABLE [control].[version_cargada] (
    [fuente]       VARCHAR (50)  NOT NULL,
    [version]      VARCHAR (40)  NOT NULL,
    [tamano_bytes] BIGINT        NOT NULL,
    [archivo]      VARCHAR (400) NOT NULL,
    [corrida]      VARCHAR (64)  NULL,
    [cargado_en]   DATETIME2 (3) CONSTRAINT [df_version_cargada_cargado_en] DEFAULT (sysutcdatetime()) NOT NULL,
    CONSTRAINT [pk_version_cargada] PRIMARY KEY CLUSTERED ([fuente] ASC, [version] ASC, [tamano_bytes] ASC),
    CONSTRAINT [fk_version_cargada_fuente] FOREIGN KEY ([fuente]) REFERENCES [control].[fuente] ([fuente])
);
