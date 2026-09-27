-- F4: políticas congeláveis e resultados duráveis por tentativa.
IF OBJECT_ID('dbo.etl_valida_arquivo_config','U') IS NULL
    THROW 50132, 'Aplique a migration 131 antes da 132.', 1;
GO
IF COL_LENGTH('dbo.etl_pipeline','liberar_dependentes_sem_movimento') IS NULL
    ALTER TABLE dbo.etl_pipeline ADD liberar_dependentes_sem_movimento BIT NOT NULL
        CONSTRAINT DF_pipeline_liberar_sem_movimento DEFAULT 0 WITH VALUES;
GO
IF COL_LENGTH('dbo.etl_pipeline','notificar_sem_movimento') IS NULL
    ALTER TABLE dbo.etl_pipeline ADD notificar_sem_movimento BIT NOT NULL
        CONSTRAINT DF_pipeline_notificar_sem_movimento DEFAULT 1 WITH VALUES;
GO
IF COL_LENGTH('dbo.etl_pipeline','politica_sem_movimento_revisao') IS NULL
    ALTER TABLE dbo.etl_pipeline ADD politica_sem_movimento_revisao BIGINT NOT NULL
        CONSTRAINT DF_pipeline_politica_sem_movimento_revisao DEFAULT 0 WITH VALUES;
GO
IF OBJECT_ID('dbo.etl_valida_arquivo_tentativa','U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_valida_arquivo_tentativa (
        id BIGINT IDENTITY NOT NULL CONSTRAINT PK_etl_valida_arquivo_tentativa PRIMARY KEY,
        pipeline_name NVARCHAR(200) COLLATE Latin1_General_BIN2 NOT NULL,
        run_id NVARCHAR(250) COLLATE Latin1_General_BIN2 NOT NULL,
        task_id NVARCHAR(200) COLLATE Latin1_General_BIN2 NOT NULL,
        tentativa INT NOT NULL,
        revisao BIGINT NOT NULL,
        resultado_json NVARCHAR(MAX) NOT NULL,
        criado_em DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT UQ_etl_valida_arquivo_tentativa UNIQUE NONCLUSTERED(pipeline_name,run_id,task_id,tentativa),
        CONSTRAINT CK_etl_valida_arquivo_tentativa_num CHECK(tentativa>0 AND revisao>0),
        CONSTRAINT CK_etl_valida_arquivo_tentativa_json CHECK(ISJSON(resultado_json)=1)
    );
END;
GO
IF OBJECT_ID('dbo.etl_valida_arquivo_resultado','U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_valida_arquivo_resultado (
        tentativa_id BIGINT NOT NULL,
        entrada_id UNIQUEIDENTIFIER NOT NULL,
        alvo NVARCHAR(200) NOT NULL,
        estado VARCHAR(20) NOT NULL,
        linhas BIGINT NULL,
        linhas_fisicas BIGINT NULL,
        decisao VARCHAR(16) NOT NULL,
        motivo NVARCHAR(300) NOT NULL,
        CONSTRAINT PK_etl_valida_arquivo_resultado PRIMARY KEY(tentativa_id,entrada_id),
        CONSTRAINT FK_etl_valida_arquivo_resultado_tentativa FOREIGN KEY(tentativa_id)
            REFERENCES dbo.etl_valida_arquivo_tentativa(id),
        CONSTRAINT CK_etl_valida_arquivo_resultado_estado CHECK(estado IN ('ausente','vazio','dados','erro_tecnico','nao_avaliado')),
        CONSTRAINT CK_etl_valida_arquivo_resultado_decisao CHECK(decisao IN ('liberar','pular','bloquear')),
        CONSTRAINT CK_etl_valida_arquivo_resultado_contagem CHECK((linhas IS NULL OR linhas>=0) AND (linhas_fisicas IS NULL OR linhas_fisicas>=0))
    );
END;
GO
IF OBJECT_ID('dbo.etl_valida_arquivo_conclusao','U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_valida_arquivo_conclusao (
        pipeline_name NVARCHAR(200) COLLATE Latin1_General_BIN2 NOT NULL,
        run_id NVARCHAR(250) COLLATE Latin1_General_BIN2 NOT NULL,
        resultado VARCHAR(24) NOT NULL,
        liberar_dependentes BIT NOT NULL,
        notificar BIT NOT NULL,
        detalhes_json NVARCHAR(MAX) NOT NULL,
        atualizado_em DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_etl_valida_arquivo_conclusao PRIMARY KEY(pipeline_name,run_id),
        CONSTRAINT CK_etl_valida_arquivo_conclusao_resultado CHECK(resultado IN ('COM_MOVIMENTO','SEM_MOVIMENTO','FALHA')),
        CONSTRAINT CK_etl_valida_arquivo_conclusao_json CHECK(ISJSON(detalhes_json)=1),
        CONSTRAINT CK_etl_valida_arquivo_conclusao_falha CHECK(resultado<>'FALHA' OR liberar_dependentes=0)
    );
END;
GO
