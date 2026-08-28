-- spec/sql/migrations/098_sn_grupo_gatilho.sql
IF OBJECT_ID('dbo.etl_servicenow_grupo', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_servicenow_grupo (
        id           INT IDENTITY(1,1) NOT NULL,
        nome         NVARCHAR(200)  NOT NULL,
        ativo        TINYINT        NOT NULL DEFAULT 1,
        criado_em    DATETIME2      NOT NULL DEFAULT GETDATE(),
        alterado_em  DATETIME2      NOT NULL DEFAULT GETDATE(),
        CONSTRAINT PK_sn_grupo PRIMARY KEY (id),
        CONSTRAINT UQ_sn_grupo_nome UNIQUE (nome)
    );
END;

IF OBJECT_ID('dbo.etl_servicenow_gatilho', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_servicenow_gatilho (
        id            INT IDENTITY(1,1) NOT NULL,
        tipo          NVARCHAR(60)   NOT NULL,
        condicao_json NVARCHAR(500)  NULL,
        webhook_url   NVARCHAR(500)  NULL,
        ativo         TINYINT        NOT NULL DEFAULT 0,
        grupo         NVARCHAR(120)  NULL,
        criado_em     DATETIME2      NOT NULL DEFAULT GETDATE(),
        CONSTRAINT PK_sn_gatilho PRIMARY KEY (id)
    );
END;
