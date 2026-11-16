CREATE TABLE [dim].[estado] (
    [estado_key] BIGINT        IDENTITY NOT NULL,
    [tipoestado] VARCHAR (400) NOT NULL
);


GO

ALTER TABLE [dim].[estado]
    ADD CONSTRAINT [pk_estado] PRIMARY KEY NONCLUSTERED ([estado_key] ASC) NOT ENFORCED;


GO
