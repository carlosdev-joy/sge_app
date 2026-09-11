-- sql/migrations/111_email.sql
-- Notificação por e-mail (spec docs/spec-notificacao-email.md, F1).
--
--   dbo.etl_app_config   — chaves email_* (MERGE por chave; a tabela já existe):
--     email_habilitado ('0'), email_remetente (''), email_limite_anexo_mb ('5'),
--     email_anexo_raizes ('[]' JSON), email_dominios_permitidos ('[]' JSON).
--   dbo.etl_pipeline.email_destinatarios — JSON ["a@x","b@x"]: a lista do
--     pipeline, herdada pelos nós `email` (F2).
--   dbo.etl_email_log    — uma linha por envio (ou tentativa): quem, o quê,
--     anexo resolvido, status (enviado | sem_anexo | falhou | pulado), erro.
--
-- Idempotente (roda 2×). Aplicada pela etapa 6c do deploy.sh.

IF NOT EXISTS (SELECT 1 FROM dbo.etl_app_config WHERE config_key = 'email_habilitado')
BEGIN
    INSERT INTO dbo.etl_app_config (config_key, config_value, descricao, updated_by, updated_at)
    VALUES ('email_habilitado', '0', 'E-mail: canal ligado (1) ou desligado (0)', 'migration_111', GETDATE());
    PRINT '[OK] email_habilitado = 0';
END
ELSE
    PRINT '[SKIP] email_habilitado ja existe';
GO

IF NOT EXISTS (SELECT 1 FROM dbo.etl_app_config WHERE config_key = 'email_remetente')
BEGIN
    INSERT INTO dbo.etl_app_config (config_key, config_value, descricao, updated_by, updated_at)
    VALUES ('email_remetente', '', 'E-mail: remetente unico de todos os envios do Orquestra', 'migration_111', GETDATE());
    PRINT '[OK] email_remetente vazio';
END
ELSE
    PRINT '[SKIP] email_remetente ja existe';
GO

IF NOT EXISTS (SELECT 1 FROM dbo.etl_app_config WHERE config_key = 'email_limite_anexo_mb')
BEGIN
    INSERT INTO dbo.etl_app_config (config_key, config_value, descricao, updated_by, updated_at)
    VALUES ('email_limite_anexo_mb', '5', 'E-mail: tamanho maximo do anexo em MB (1 a 25)', 'migration_111', GETDATE());
    PRINT '[OK] email_limite_anexo_mb = 5';
END
ELSE
    PRINT '[SKIP] email_limite_anexo_mb ja existe';
GO

IF NOT EXISTS (SELECT 1 FROM dbo.etl_app_config WHERE config_key = 'email_anexo_raizes')
BEGIN
    INSERT INTO dbo.etl_app_config (config_key, config_value, descricao, updated_by, updated_at)
    VALUES ('email_anexo_raizes', '[]', 'E-mail: raizes permitidas para anexos no servidor do DataStage (JSON)', 'migration_111', GETDATE());
    PRINT '[OK] email_anexo_raizes = []';
END
ELSE
    PRINT '[SKIP] email_anexo_raizes ja existe';
GO

IF NOT EXISTS (SELECT 1 FROM dbo.etl_app_config WHERE config_key = 'email_dominios_permitidos')
BEGIN
    INSERT INTO dbo.etl_app_config (config_key, config_value, descricao, updated_by, updated_at)
    VALUES ('email_dominios_permitidos', '[]', 'E-mail: dominios de destinatario permitidos (JSON; vazio = qualquer)', 'migration_111', GETDATE());
    PRINT '[OK] email_dominios_permitidos = []';
END
ELSE
    PRINT '[SKIP] email_dominios_permitidos ja existe';
GO

IF COL_LENGTH('dbo.etl_pipeline', 'email_destinatarios') IS NULL
BEGIN
    ALTER TABLE dbo.etl_pipeline ADD email_destinatarios NVARCHAR(MAX) NULL;
    PRINT '[OK] etl_pipeline.email_destinatarios criada';
END
ELSE
    PRINT '[SKIP] etl_pipeline.email_destinatarios ja existe';
GO

IF OBJECT_ID('dbo.etl_email_log', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_email_log (
        id            INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_email_log PRIMARY KEY,
        pipeline_name NVARCHAR(200) NOT NULL,       -- '_teste_admin' no botão Testar
        job_name      NVARCHAR(200) NOT NULL,
        dag_run_id    NVARCHAR(250) NULL,           -- run_id do Airflow (larguras da 109)
        execution_id  NVARCHAR(100) NULL,           -- ts_nodash (como etl_job_execution)
        remetente     NVARCHAR(200) NOT NULL,
        destinatarios NVARCHAR(MAX) NOT NULL,       -- JSON ["a@x", ...]
        assunto       NVARCHAR(500) NOT NULL,
        anexo_path    NVARCHAR(500) NULL,           -- caminho RESOLVIDO (placeholders trocados)
        anexo_bytes   INT           NULL,
        status        VARCHAR(20)   NOT NULL,       -- enviado | sem_anexo | falhou | pulado
        erro          NVARCHAR(1000) NULL,
        duracao_ms    INT           NULL,
        criado_por    NVARCHAR(100) NULL,           -- matrícula (botão Testar) ou NULL (corrida)
        criado_em     DATETIME2(0)  NOT NULL CONSTRAINT DF_etl_email_log_em DEFAULT GETDATE()
    );
    PRINT '[OK] Tabela dbo.etl_email_log criada';
END
ELSE
    PRINT '[SKIP] dbo.etl_email_log ja existe';
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_etl_email_log_pipeline'
               AND object_id = OBJECT_ID('dbo.etl_email_log'))
BEGIN
    CREATE INDEX IX_etl_email_log_pipeline ON dbo.etl_email_log (pipeline_name, criado_em DESC);
    PRINT '[OK] IX_etl_email_log_pipeline criado';
END
ELSE
    PRINT '[SKIP] IX_etl_email_log_pipeline ja existe';
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_etl_email_log_run'
               AND object_id = OBJECT_ID('dbo.etl_email_log'))
BEGIN
    CREATE INDEX IX_etl_email_log_run ON dbo.etl_email_log (dag_run_id);
    PRINT '[OK] IX_etl_email_log_run criado';
END
ELSE
    PRINT '[SKIP] IX_etl_email_log_run ja existe';
GO
