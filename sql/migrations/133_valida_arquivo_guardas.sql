-- Prova durável da decisão aplicada, vinculada à tentativa real do Airflow.
IF OBJECT_ID('dbo.etl_valida_arquivo_conclusao','U') IS NULL
    THROW 50133, 'Aplique a migration 132 antes da 133.', 1;
GO
IF OBJECT_ID('dbo.etl_valida_arquivo_guarda','U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_valida_arquivo_guarda (
        id BIGINT IDENTITY NOT NULL CONSTRAINT PK_valida_guarda PRIMARY KEY,
        pipeline_name NVARCHAR(200) COLLATE Latin1_General_BIN2 NOT NULL,
        run_id NVARCHAR(250) COLLATE Latin1_General_BIN2 NOT NULL,
        task_id NVARCHAR(250) COLLATE Latin1_General_BIN2 NOT NULL,
        tentativa INT NOT NULL,
        inicio_tentativa VARCHAR(40) NOT NULL,
        decisao VARCHAR(16) NOT NULL,
        origens_json NVARCHAR(MAX) NOT NULL,
        criado_em DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT UQ_valida_guarda UNIQUE NONCLUSTERED(pipeline_name,run_id,task_id,tentativa),
        CONSTRAINT CK_valida_guarda_tentativa CHECK(tentativa>0),
        CONSTRAINT CK_valida_guarda_decisao CHECK(decisao IN ('liberar','pular','bloquear')),
        CONSTRAINT CK_valida_guarda_json CHECK(ISJSON(origens_json)=1)
    );
END;
GO
-- Branches podem encerrar sem avaliar arquivos; isso não equivale a falta de dados.
IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name='CK_etl_valida_arquivo_conclusao_resultado' AND definition LIKE '%SEM_EXECUCAO%')
BEGIN
    BEGIN TRANSACTION;
    ALTER TABLE dbo.etl_valida_arquivo_conclusao DROP CONSTRAINT CK_etl_valida_arquivo_conclusao_resultado;
    ALTER TABLE dbo.etl_valida_arquivo_conclusao ADD CONSTRAINT CK_etl_valida_arquivo_conclusao_resultado
        CHECK(resultado IN ('COM_MOVIMENTO','SEM_MOVIMENTO','SEM_EXECUCAO','FALHA'));
    COMMIT;
END;
GO
