CREATE TABLE [dim].[fecha] (
    [fecha_key] INT  NOT NULL,
    [fecha]     DATE NOT NULL,
    [anio]      INT  NOT NULL,
    [mes]       INT  NOT NULL,
    [trimestre] INT  NOT NULL
);


GO

ALTER TABLE [dim].[fecha]
    ADD CONSTRAINT [pk_fecha] PRIMARY KEY NONCLUSTERED ([fecha_key] ASC) NOT ENFORCED;


GO