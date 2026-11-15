CREATE TABLE [control].[fuente] (
    [fuente]       VARCHAR (50) NOT NULL,
    [recurso_ckan] CHAR (36)    NOT NULL,
    [dataset]      VARCHAR (50) NULL,
    [activa]       BIT          CONSTRAINT [df_fuente_activa] DEFAULT ((1)) NOT NULL,
    CONSTRAINT [pk_fuente] PRIMARY KEY CLUSTERED ([fuente] ASC)
);


GO

