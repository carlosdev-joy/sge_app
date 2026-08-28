-- spec/sql/migrations/097_indicador_snapshot.sql
IF OBJECT_ID('dbo.etl_indicador_snapshot', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_indicador_snapshot (
        id                          INT IDENTITY(1,1) NOT NULL,
        capturado_em                DATETIME2      NOT NULL DEFAULT GETDATE(),
        total_ativos                INT            NOT NULL DEFAULT 0,
        novo                        INT            NOT NULL DEFAULT 0,
        andamento                   INT            NOT NULL DEFAULT 0,
        aguardando                  INT            NOT NULL DEFAULT 0,
        resolvido                   INT            NOT NULL DEFAULT 0,
        outros                      INT            NOT NULL DEFAULT 0,
        sla_vencidos                INT            NOT NULL DEFAULT 0,
        idade_media_dias            DECIMAL(6,1)   NULL,
        tempo_medio_resolucao_horas DECIMAL(8,1)   NULL,
        qtd_encerrados_7d           INT            NOT NULL DEFAULT 0,
        qtd_abertos_7d              INT            NOT NULL DEFAULT 0,
        qtd_iniciativas_abertas     INT            NOT NULL DEFAULT 0,
        CONSTRAINT PK_snapshot PRIMARY KEY (id)
    );
    CREATE INDEX IX_snapshot_capturado ON dbo.etl_indicador_snapshot (capturado_em DESC);
END;

IF OBJECT_ID('dbo.etl_indicador_snapshot_analista', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_indicador_snapshot_analista (
        id_snapshot       INT            NOT NULL,
        atribuido_a       NVARCHAR(120)  NOT NULL,
        atribuido_a_email NVARCHAR(200)  NOT NULL DEFAULT '',
        total_ativos      INT            NOT NULL DEFAULT 0,
        sla_vencidos      INT            NOT NULL DEFAULT 0,
        idade_media_dias  DECIMAL(6,1)   NULL,
        CONSTRAINT PK_snapshot_analista PRIMARY KEY (id_snapshot, atribuido_a_email),
        CONSTRAINT FK_snapshot_analista FOREIGN KEY (id_snapshot)
            REFERENCES dbo.etl_indicador_snapshot(id)
    );
END;

IF OBJECT_ID('dbo.etl_indicador_snapshot_grupo', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_indicador_snapshot_grupo (
        id_snapshot      INT            NOT NULL,
        grupo            NVARCHAR(120)  NOT NULL,
        total_ativos     INT            NOT NULL DEFAULT 0,
        sla_vencidos     INT            NOT NULL DEFAULT 0,
        idade_media_dias DECIMAL(6,1)   NULL,
        CONSTRAINT PK_snapshot_grupo PRIMARY KEY (id_snapshot, grupo),
        CONSTRAINT FK_snapshot_grupo FOREIGN KEY (id_snapshot)
            REFERENCES dbo.etl_indicador_snapshot(id)
    );
END;

IF OBJECT_ID('dbo.etl_indicador_meta', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_indicador_meta (
        id              INT IDENTITY(1,1) NOT NULL,
        metrica         NVARCHAR(60)   NOT NULL,
        valor_meta      DECIMAL(8,1)   NOT NULL,
        periodo_inicio  DATE           NOT NULL,
        periodo_fim     DATE           NULL,
        grupo           NVARCHAR(120)  NULL,
        criado_por      NVARCHAR(120)  NULL,
        criado_em       DATETIME2      NOT NULL DEFAULT GETDATE(),
        CONSTRAINT PK_meta PRIMARY KEY (id)
    );
END;
