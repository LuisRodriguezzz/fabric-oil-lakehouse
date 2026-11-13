CREATE TABLE [dim].[empresa] (
    [empresa_key] BIGINT        IDENTITY NOT NULL,
    [idempresa]   VARCHAR (50)  NOT NULL,
    [empresa]     VARCHAR (400) NULL
);


GO

ALTER TABLE [dim].[empresa]
    ADD CONSTRAINT [pk_empresa] PRIMARY KEY NONCLUSTERED ([empresa_key] ASC) NOT ENFORCED;


GO