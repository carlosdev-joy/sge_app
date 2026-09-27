-- F3: configuração revisada. O nó só será ativado após integração de runtime.
IF OBJECT_ID('dbo.etl_parametro_snapshot','U') IS NULL
    THROW 50131, 'Aplique a migration 130 antes da 131.', 1;
GO
IF OBJECT_ID('dbo.etl_valida_arquivo_no','U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_valida_arquivo_no (
        pipeline_name NVARCHAR(200) NOT NULL,
        task_id NVARCHAR(200) NOT NULL,
        ssh_conn_id VARCHAR(100) NOT NULL,
        timeout_segundos INT NOT NULL,
        revisao BIGINT NOT NULL,
        atualizado_em DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_etl_valida_arquivo_no PRIMARY KEY (pipeline_name,task_id),
        CONSTRAINT FK_etl_valida_arquivo_no_job FOREIGN KEY (pipeline_name,task_id)
            REFERENCES dbo.etl_pipeline_job(pipeline_name,job_name),
        CONSTRAINT CK_etl_valida_arquivo_no_timeout CHECK (timeout_segundos BETWEEN 1 AND 600),
        CONSTRAINT CK_etl_valida_arquivo_no_revisao CHECK (revisao>0)
    );
END;
GO
IF OBJECT_ID('dbo.etl_valida_arquivo_config','U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_valida_arquivo_config (
        pipeline_name NVARCHAR(200) NOT NULL,
        task_id NVARCHAR(200) NOT NULL,
        entrada_id UNIQUEIDENTIFIER NOT NULL,
        ordem INT NOT NULL,
        tipo VARCHAR(16) NOT NULL,
        param_name VARCHAR(128) COLLATE Latin1_General_BIN2 NULL,
        diretorio_literal NVARCHAR(2000) NULL,
        arquivo NVARCHAR(300) NOT NULL,
        alvo NVARCHAR(200) NOT NULL,
        se_nao_existe VARCHAR(16) NOT NULL,
        se_zero_linhas VARCHAR(16) NOT NULL,
        ignorar_cabecalho BIT NOT NULL,
        CONSTRAINT PK_etl_valida_arquivo_config PRIMARY KEY(pipeline_name,task_id,entrada_id),
        CONSTRAINT UQ_etl_valida_arquivo_config_ordem UNIQUE(pipeline_name,task_id,ordem),
        CONSTRAINT FK_etl_valida_arquivo_config_no FOREIGN KEY(pipeline_name,task_id)
            REFERENCES dbo.etl_valida_arquivo_no(pipeline_name,task_id),
        CONSTRAINT FK_etl_valida_arquivo_config_alvo FOREIGN KEY(pipeline_name,alvo)
            REFERENCES dbo.etl_pipeline_job(pipeline_name,job_name),
        CONSTRAINT CK_etl_valida_arquivo_config_tipo CHECK(tipo IN ('arquivo','dataset')),
        CONSTRAINT CK_etl_valida_arquivo_config_ordem CHECK(ordem BETWEEN 0 AND 99),
        CONSTRAINT CK_etl_valida_arquivo_config_diretorio CHECK(NULLIF(diretorio_literal,'') IS NOT NULL OR param_name IS NOT NULL),
        CONSTRAINT CK_etl_valida_arquivo_config_ausente CHECK(se_nao_existe IN ('pular','falhar')),
        CONSTRAINT CK_etl_valida_arquivo_config_vazio CHECK(se_zero_linhas IN ('pular','falhar','executar')),
        CONSTRAINT CK_etl_valida_arquivo_config_cabecalho CHECK(tipo='arquivo' OR ignorar_cabecalho=0)
    );
END;
GO
