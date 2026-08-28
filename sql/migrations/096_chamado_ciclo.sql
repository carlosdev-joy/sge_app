-- spec/sql/migrations/096_chamado_ciclo.sql
IF OBJECT_ID('dbo.etl_chamado_ciclo', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_chamado_ciclo (
        id               INT IDENTITY(1,1) NOT NULL,
        modo             NVARCHAR(10)   NOT NULL,   -- 'delta' | 'full'
        iniciado_em      DATETIME2      NOT NULL,
        terminado_em     DATETIME2      NULL,
        status           NVARCHAR(10)   NOT NULL DEFAULT 'ERRO',
        qtd_chamados     INT            NULL,
        qtd_notas        INT            NULL,
        qtd_anexos       INT            NULL,
        qtd_desativados  INT            NULL,
        disparado_por    NVARCHAR(50)   NULL,
        erro             NVARCHAR(1000) NULL,
        CONSTRAINT PK_etl_chamado_ciclo PRIMARY KEY (id)
    );
    CREATE INDEX IX_ciclo_modo_status
        ON dbo.etl_chamado_ciclo (modo, status, iniciado_em DESC);
END;
