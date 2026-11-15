CREATE TABLE [dim].[yacimiento] (
    [yacimiento_key]   BIGINT        IDENTITY NOT NULL,
    [idareayacimiento] VARCHAR (50)  NOT NULL,
    [areayacimiento]   VARCHAR (400) NULL,
    [cuenca]           VARCHAR (400) NULL,
    [provincia]        VARCHAR (400) NULL
);


GO

ALTER TABLE [dim].[yacimiento]
    ADD CONSTRAINT [pk_yacimiento] PRIMARY KEY NONCLUSTERED ([yacimiento_key] ASC) NOT ENFORCED;


GO