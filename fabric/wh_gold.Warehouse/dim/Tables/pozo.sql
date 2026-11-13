CREATE TABLE [dim].[pozo] (
    [pozo_key]           BIGINT        IDENTITY NOT NULL,
    [idpozo]             BIGINT        NOT NULL,
    [vigente_desde]      DATE          NOT NULL,
    [vigente_hasta]      DATE          NULL,
    [es_actual]          BIT           NOT NULL,
    [sigla]              VARCHAR (400) NULL,
    [tipoestado]         VARCHAR (400) NULL,
    [tipopozo]           VARCHAR (400) NULL,
    [tipoextraccion]     VARCHAR (400) NULL,
    [tipo_de_recurso]    VARCHAR (400) NULL,
    [sub_tipo_recurso]   VARCHAR (400) NULL,
    [formacion]          VARCHAR (400) NULL,
    [profundidad]        FLOAT (53)    NULL,
    [primera_produccion] DATE          NULL
);


GO

ALTER TABLE [dim].[pozo]
    ADD CONSTRAINT [pk_pozo] PRIMARY KEY NONCLUSTERED ([pozo_key] ASC) NOT ENFORCED;


GO