-- =============================================================================
-- ORQUESTRA — Script de Implantação Completo (Idempotente)
-- Banco: orquestra_dev / DMDB41   Schema: dbo
--
-- Pode ser executado múltiplas vezes sem efeitos colaterais.
-- Cria o que não existe e ignora o que já está correto.
--
-- Ordem de execução:
--   1. Tabelas core (base do sistema)
--   2. Stored procedures core (upsert, job, etc.)
--   3. Tabelas e colunas de configuração
--   4. Migrações incrementais 002–009
--   5. Seed de dados mínimos
--   6. Verificação final
--
-- Executar como:
--   sqlcmd -S <host> -U sa -P '<senha>' -d orquestra_dev -C -i deploy_full.sql
-- =============================================================================

PRINT '============================================================';
PRINT ' ORQUESTRA — Deploy Full (idempotente)';
PRINT ' Iniciado em: ' + CONVERT(VARCHAR(30), GETDATE(), 120);
PRINT '============================================================';
GO

-- ============================================================
-- SEÇÃO 1 — TABELAS CORE
-- ============================================================

-- ------------------------------------------------------------
-- 1.1 etl_pipeline — cadastro de pipelines
-- ------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE object_id = OBJECT_ID('dbo.etl_pipeline'))
BEGIN
    CREATE TABLE dbo.etl_pipeline (
        pipeline_name       NVARCHAR(200)  NOT NULL,
        project_name        NVARCHAR(100)  NULL,
        domain              NVARCHAR(100)  NULL,
        tags                NVARCHAR(300)  NULL,
        schedule_type       NVARCHAR(20)   NULL DEFAULT 'manual',
        schedule_hour       INT            NULL,
        schedule_minute     INT            NULL DEFAULT 0,
        schedule_dow        NVARCHAR(20)   NULL,
        schedule_dom        INT            NULL,
        active              BIT            NOT NULL DEFAULT 1,
        dag_criada          BIT            NOT NULL DEFAULT 0,
        envia_msg_inicio    BIT            NOT NULL DEFAULT 0,
        envia_msg_fim       BIT            NOT NULL DEFAULT 0,
        envia_msg_erro      BIT            NOT NULL DEFAULT 1,
        criado_em           DATETIME2      NOT NULL DEFAULT GETDATE(),
        atualizado_em       DATETIME2      NOT NULL DEFAULT GETDATE(),
        criado_por          NVARCHAR(100)  NULL,
        CONSTRAINT PK_etl_pipeline PRIMARY KEY CLUSTERED (pipeline_name ASC)
    );
    PRINT '[OK] Tabela dbo.etl_pipeline criada';
END
ELSE
    PRINT '[--] dbo.etl_pipeline já existe';
GO

-- ------------------------------------------------------------
-- 1.2 etl_pipeline_job — jobs de cada pipeline
-- ------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE object_id = OBJECT_ID('dbo.etl_pipeline_job'))
BEGIN
    CREATE TABLE dbo.etl_pipeline_job (
        id              INT IDENTITY(1,1) NOT NULL,
        pipeline_name   NVARCHAR(200) NOT NULL,
        job_name        NVARCHAR(200) NOT NULL,
        execution_order INT           NOT NULL DEFAULT 1,
        job_type        NVARCHAR(50)  NOT NULL,
        job_command     NVARCHAR(MAX) NULL,
        active          BIT           NOT NULL DEFAULT 1,
        criado_em       DATETIME2     NOT NULL DEFAULT GETDATE(),
        criado_por      NVARCHAR(100) NULL,
        CONSTRAINT PK_etl_pipeline_job PRIMARY KEY CLUSTERED (id ASC),
        CONSTRAINT UQ_etl_pipeline_job UNIQUE (pipeline_name, job_name)
    );
    CREATE NONCLUSTERED INDEX IX_etl_pipeline_job_pipeline
        ON dbo.etl_pipeline_job (pipeline_name ASC, execution_order ASC);
    PRINT '[OK] Tabela dbo.etl_pipeline_job criada';
END
ELSE
    PRINT '[--] dbo.etl_pipeline_job já existe';
GO

-- ------------------------------------------------------------
-- 1.3 etl_job_execution — log de execuções
-- ------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE object_id = OBJECT_ID('dbo.etl_job_execution'))
BEGIN
    CREATE TABLE dbo.etl_job_execution (
        id              BIGINT IDENTITY(1,1) NOT NULL,
        pipeline_name   NVARCHAR(200) NOT NULL,
        job_name        NVARCHAR(200) NULL,
        execution_id    NVARCHAR(200) NULL,
        status          NVARCHAR(20)  NULL,   -- RUNNING, SUCCESS, FAILED
        started_at      DATETIME2     NULL,
        finished_at     DATETIME2     NULL,
        log_text        NVARCHAR(MAX) NULL,
        CONSTRAINT PK_etl_job_execution PRIMARY KEY CLUSTERED (id ASC)
    );
    CREATE NONCLUSTERED INDEX IX_etl_job_execution_pipeline
        ON dbo.etl_job_execution (pipeline_name ASC, started_at DESC);
    PRINT '[OK] Tabela dbo.etl_job_execution criada';
END
ELSE
    PRINT '[--] dbo.etl_job_execution já existe';
GO

-- ------------------------------------------------------------
-- 1.4 etl_job_lineage — lineage aprovado por job
-- ------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE object_id = OBJECT_ID('dbo.etl_job_lineage'))
BEGIN
    CREATE TABLE dbo.etl_job_lineage (
        id              INT IDENTITY(1,1) NOT NULL,
        pipeline_name   NVARCHAR(200)  NOT NULL,
        job_name        NVARCHAR(200)  NOT NULL,
        execution_order INT            NOT NULL DEFAULT 1,
        direction       NVARCHAR(10)   NOT NULL DEFAULT 'INPUT',  -- INPUT / OUTPUT
        object_type     NVARCHAR(100)  NULL,
        object_name     NVARCHAR(300)  NULL,
        database_name   NVARCHAR(100)  NULL,
        columns_json    NVARCHAR(MAX)  NULL,
        criado_em       DATETIME2      NOT NULL DEFAULT GETDATE(),
        CONSTRAINT PK_etl_job_lineage PRIMARY KEY CLUSTERED (id ASC)
    );
    CREATE NONCLUSTERED INDEX IX_etl_job_lineage_pipeline
        ON dbo.etl_job_lineage (pipeline_name ASC, job_name ASC);
    PRINT '[OK] Tabela dbo.etl_job_lineage criada';
END
ELSE
    PRINT '[--] dbo.etl_job_lineage já existe';
GO

-- ------------------------------------------------------------
-- 1.5 etl_seq_import_lineage — staging de lineage (import DSX)
-- ------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE object_id = OBJECT_ID('dbo.etl_seq_import_lineage'))
BEGIN
    CREATE TABLE dbo.etl_seq_import_lineage (
        id              INT IDENTITY(1,1) NOT NULL,
        import_key      NVARCHAR(100)  NOT NULL,
        pipeline_name   NVARCHAR(200)  NULL,
        job_name        NVARCHAR(200)  NULL,
        execution_order INT            NULL DEFAULT 1,
        direction       NVARCHAR(10)   NULL DEFAULT 'INPUT',
        object_type     NVARCHAR(100)  NULL,
        object_name     NVARCHAR(300)  NULL,
        database_name   NVARCHAR(100)  NULL,
        columns_json    NVARCHAR(MAX)  NULL,
        status          NVARCHAR(20)   NULL DEFAULT 'PENDING',
        criado_em       DATETIME2      NOT NULL DEFAULT GETDATE(),
        CONSTRAINT PK_etl_seq_import_lineage PRIMARY KEY CLUSTERED (id ASC)
    );
    PRINT '[OK] Tabela dbo.etl_seq_import_lineage criada';
END
ELSE
    PRINT '[--] dbo.etl_seq_import_lineage já existe';
GO

-- ------------------------------------------------------------
-- 1.6 etl_stage_type_map — mapeamento de tipos de stage DSX → label
-- ------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE object_id = OBJECT_ID('dbo.etl_stage_type_map'))
BEGIN
    CREATE TABLE dbo.etl_stage_type_map (
        stage_type    NVARCHAR(100) NOT NULL,
        type_label    NVARCHAR(100) NOT NULL,
        type_category NVARCHAR(50)  NULL,
        role_hint     NVARCHAR(50)  NULL,
        CONSTRAINT PK_etl_stage_type_map PRIMARY KEY (stage_type)
    );
    PRINT '[OK] Tabela dbo.etl_stage_type_map criada';
END
ELSE
    PRINT '[--] dbo.etl_stage_type_map já existe';
GO

-- Adicionar colunas type_category e role_hint se não existirem
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('dbo.etl_stage_type_map') AND name='type_category')
    ALTER TABLE dbo.etl_stage_type_map ADD type_category NVARCHAR(50) NULL;
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id=OBJECT_ID('dbo.etl_stage_type_map') AND name='role_hint')
    ALTER TABLE dbo.etl_stage_type_map ADD role_hint NVARCHAR(50) NULL;
PRINT '[OK] Colunas type_category e role_hint garantidas em etl_stage_type_map';
GO

-- Seed via EXEC (SQL dinâmico) para evitar validação de colunas em tempo de compilação
EXEC('
IF NOT EXISTS (SELECT 1 FROM dbo.etl_stage_type_map WHERE stage_type = ''CTransformerStage'')
BEGIN
    INSERT INTO dbo.etl_stage_type_map (stage_type, type_label) VALUES
        (''CTransformerStage'',      ''Transformer''),
        (''CHashPartitionStage'',    ''Hash Partition''),
        (''CSeqFileStage'',          ''Arquivo Sequencial''),
        (''CDataSetStage'',          ''Arquivo DataSet (.ds/.dx)''),
        (''COracleConnectorPX'',     ''Oracle''),
        (''DB2ConnectorPX'',         ''DB2''),
        (''CODBCConnectorPX'',       ''ODBC / SQL Server''),
        (''CNetezzaConnectorPX'',    ''Netezza''),
        (''SAPConnectorPX'',         ''SAP''),
        (''CBMSOraBulkLoaderStage'', ''Oracle Bulk Loader''),
        (''CRowGeneratorStage'',     ''Row Generator''),
        (''CLookupStage'',           ''Lookup''),
        (''CSortStage'',             ''Sort''),
        (''CFilterStage'',           ''Filter''),
        (''CJoinStage'',             ''Join''),
        (''CFunnelStage'',           ''Funnel''),
        (''CSampleStage'',           ''Sample''),
        (''CRemoveDuplicatesStage'', ''Remove Duplicates''),
        (''CChangeApplyStage'',      ''Change Apply''),
        (''CChangeCaptureStage'',    ''Change Capture'');
    PRINT ''[OK] Seed de etl_stage_type_map aplicado'';
END
ELSE
    PRINT ''[--] etl_stage_type_map ja possui dados'';
');
GO

-- Classificar type_category e role_hint
UPDATE dbo.etl_stage_type_map SET type_category='storage',   role_hint='source'
WHERE stage_type IN ('CSeqFileStage','CDataSetStage');

UPDATE dbo.etl_stage_type_map SET type_category='database',  role_hint='source'
WHERE stage_type IN ('COracleConnectorPX','DB2ConnectorPX','CODBCConnectorPX',
                     'CNetezzaConnectorPX','SAPConnectorPX','CBMSOraBulkLoaderStage');

UPDATE dbo.etl_stage_type_map SET type_category='transform', role_hint='transform'
WHERE stage_type IN ('CTransformerStage','CHashPartitionStage','CLookupStage',
                     'CSortStage','CFilterStage','CJoinStage','CFunnelStage',
                     'CSampleStage','CRemoveDuplicatesStage','CChangeApplyStage',
                     'CChangeCaptureStage','CRowGeneratorStage');
PRINT '[OK] type_category e role_hint atualizados em etl_stage_type_map';
GO

-- ------------------------------------------------------------
-- 1.7 etl_configuracao — parâmetros gerais da aplicação
-- ------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE object_id = OBJECT_ID('dbo.etl_configuracao'))
BEGIN
    CREATE TABLE dbo.etl_configuracao (
        chave       NVARCHAR(100) NOT NULL,
        valor       NVARCHAR(MAX) NULL,
        descricao   NVARCHAR(500) NULL,
        atualizado_em DATETIME2   NOT NULL DEFAULT GETDATE(),
        CONSTRAINT PK_etl_configuracao PRIMARY KEY (chave)
    );
    PRINT '[OK] Tabela dbo.etl_configuracao criada';
END
ELSE
    PRINT '[--] dbo.etl_configuracao já existe';
GO


-- ============================================================
-- SEÇÃO 2 — STORED PROCEDURES CORE
-- ============================================================

-- ------------------------------------------------------------
-- 2.1 sp_etl_pipeline_upsert
-- ------------------------------------------------------------
IF OBJECT_ID('dbo.sp_etl_pipeline_upsert', 'P') IS NULL
BEGIN
    EXEC('
    CREATE PROCEDURE dbo.sp_etl_pipeline_upsert
        @pipeline_name         NVARCHAR(200),
        @project_name          NVARCHAR(100)  = NULL,
        @domain                NVARCHAR(100)  = NULL,
        @tags                  NVARCHAR(300)  = NULL,
        @schedule_type         NVARCHAR(20)   = ''manual'',
        @schedule_hour         INT            = 6,
        @schedule_minute       INT            = 0,
        @schedule_dow          NVARCHAR(20)   = NULL,
        @schedule_dom          INT            = NULL,
        @active                BIT            = 1,
        @dag_criada            BIT            = 0,
        @envia_msg_inicio      BIT            = 0,
        @envia_msg_fim         BIT            = 0,
        @envia_msg_erro        BIT            = 1,
        @depends_on            NVARCHAR(2000) = NULL,
        @dag_start_date        DATE           = NULL,
        @descricao             NVARCHAR(500)  = NULL,
        @criticidade           NVARCHAR(10)   = ''Media'',
        @sla_minutos           INT            = NULL,
        @ambiente              NVARCHAR(10)   = ''PROD'',
        @max_active_runs       INT            = 1,
        @retries_count         INT            = 1,
        @retry_delay_seconds   INT            = 300,
        @pool_name             NVARCHAR(100)  = NULL,
        @user_name             NVARCHAR(100)  = ''system''
    AS
    BEGIN
        SET NOCOUNT ON;
        IF EXISTS (SELECT 1 FROM dbo.etl_pipeline WHERE pipeline_name = @pipeline_name)
        BEGIN
            UPDATE dbo.etl_pipeline SET
                project_name       = ISNULL(@project_name, project_name),
                domain             = ISNULL(@domain, domain),
                tags               = ISNULL(@tags, tags),
                schedule_type      = ISNULL(@schedule_type, schedule_type),
                schedule_hour      = ISNULL(@schedule_hour, schedule_hour),
                schedule_minute    = ISNULL(@schedule_minute, schedule_minute),
                schedule_dow       = @schedule_dow,
                schedule_dom       = @schedule_dom,
                active             = ISNULL(@active, active),
                dag_criada         = ISNULL(@dag_criada, dag_criada),
                envia_msg_inicio   = ISNULL(@envia_msg_inicio, envia_msg_inicio),
                envia_msg_fim      = ISNULL(@envia_msg_fim, envia_msg_fim),
                envia_msg_erro     = ISNULL(@envia_msg_erro, envia_msg_erro),
                depends_on         = @depends_on,
                dag_start_date     = @dag_start_date,
                descricao          = @descricao,
                criticidade        = ISNULL(@criticidade, criticidade),
                sla_minutos        = @sla_minutos,
                ambiente           = ISNULL(@ambiente, ambiente),
                max_active_runs    = ISNULL(@max_active_runs, max_active_runs),
                retries_count      = ISNULL(@retries_count, retries_count),
                retry_delay_seconds= ISNULL(@retry_delay_seconds, retry_delay_seconds),
                pool_name          = @pool_name,
                atualizado_em      = GETDATE()
            WHERE pipeline_name = @pipeline_name;
        END
        ELSE
        BEGIN
            INSERT INTO dbo.etl_pipeline (
                pipeline_name, project_name, domain, tags,
                schedule_type, schedule_hour, schedule_minute, schedule_dow, schedule_dom,
                active, dag_criada, envia_msg_inicio, envia_msg_fim, envia_msg_erro,
                depends_on, dag_start_date, descricao, criticidade, sla_minutos,
                ambiente, max_active_runs, retries_count, retry_delay_seconds, pool_name,
                criado_por
            ) VALUES (
                @pipeline_name, @project_name, @domain, @tags,
                @schedule_type, @schedule_hour, @schedule_minute, @schedule_dow, @schedule_dom,
                @active, @dag_criada, @envia_msg_inicio, @envia_msg_fim, @envia_msg_erro,
                @depends_on, @dag_start_date, @descricao, @criticidade, @sla_minutos,
                @ambiente, @max_active_runs, @retries_count, @retry_delay_seconds, @pool_name,
                @user_name
            );
        END
    END
    ');
    PRINT '[OK] sp_etl_pipeline_upsert criada';
END
ELSE
    PRINT '[--] sp_etl_pipeline_upsert já existe';
GO

-- ------------------------------------------------------------
-- 2.2 sp_etl_pipeline_job_upsert
-- ------------------------------------------------------------
IF OBJECT_ID('dbo.sp_etl_pipeline_job_upsert', 'P') IS NULL
BEGIN
    EXEC('
    CREATE PROCEDURE dbo.sp_etl_pipeline_job_upsert
        @pipeline_name  NVARCHAR(200),
        @job_name       NVARCHAR(200),
        @execution_order INT           = 1,
        @job_type       NVARCHAR(50)  = ''SQL'',
        @job_command    NVARCHAR(MAX) = NULL,
        @user_name      NVARCHAR(100) = ''system''
    AS
    BEGIN
        SET NOCOUNT ON;
        IF EXISTS (SELECT 1 FROM dbo.etl_pipeline_job
                   WHERE pipeline_name = @pipeline_name AND job_name = @job_name)
            UPDATE dbo.etl_pipeline_job SET
                execution_order = @execution_order,
                job_type        = @job_type,
                job_command     = @job_command
            WHERE pipeline_name = @pipeline_name AND job_name = @job_name;
        ELSE
            INSERT INTO dbo.etl_pipeline_job
                (pipeline_name, job_name, execution_order, job_type, job_command, criado_por)
            VALUES
                (@pipeline_name, @job_name, @execution_order, @job_type, @job_command, @user_name);
    END
    ');
    PRINT '[OK] sp_etl_pipeline_job_upsert criada';
END
ELSE
    PRINT '[--] sp_etl_pipeline_job_upsert já existe';
GO


-- ============================================================
-- SEÇÃO 3 — COLUNAS INCREMENTAIS em etl_pipeline
-- (Migrações 002, 003, 007)
-- ============================================================

-- depends_on (Mig 002)
IF NOT EXISTS (SELECT 1 FROM sys.columns
               WHERE object_id = OBJECT_ID('dbo.etl_pipeline') AND name = 'depends_on')
BEGIN
    ALTER TABLE dbo.etl_pipeline ADD depends_on NVARCHAR(2000) NULL;
    PRINT '[OK] Coluna depends_on adicionada';
END
ELSE IF COL_LENGTH('dbo.etl_pipeline', 'depends_on') < 2000
BEGIN
    ALTER TABLE dbo.etl_pipeline ALTER COLUMN depends_on NVARCHAR(2000) NULL;
    PRINT '[OK] Coluna depends_on expandida para NVARCHAR(2000)';
END
ELSE
    PRINT '[--] depends_on já existe e está correta';
GO

-- dag_start_date (Mig 003)
IF NOT EXISTS (SELECT 1 FROM sys.columns
               WHERE object_id = OBJECT_ID('dbo.etl_pipeline') AND name = 'dag_start_date')
BEGIN
    ALTER TABLE dbo.etl_pipeline ADD dag_start_date DATE NULL;
    PRINT '[OK] Coluna dag_start_date adicionada';
END
ELSE
    PRINT '[--] dag_start_date já existe';
GO

-- descricao (Mig 007)
IF NOT EXISTS (SELECT 1 FROM sys.columns
               WHERE object_id = OBJECT_ID('dbo.etl_pipeline') AND name = 'descricao')
BEGIN
    ALTER TABLE dbo.etl_pipeline ADD descricao NVARCHAR(500) NULL;
    PRINT '[OK] Coluna descricao adicionada';
END
ELSE
    PRINT '[--] descricao já existe';
GO

-- criticidade (Mig 007)
IF NOT EXISTS (SELECT 1 FROM sys.columns
               WHERE object_id = OBJECT_ID('dbo.etl_pipeline') AND name = 'criticidade')
BEGIN
    ALTER TABLE dbo.etl_pipeline ADD criticidade NVARCHAR(10) NULL DEFAULT 'Media';
    PRINT '[OK] Coluna criticidade adicionada';
END
ELSE
    PRINT '[--] criticidade já existe';
GO

-- sla_minutos (Mig 007)
IF NOT EXISTS (SELECT 1 FROM sys.columns
               WHERE object_id = OBJECT_ID('dbo.etl_pipeline') AND name = 'sla_minutos')
BEGIN
    ALTER TABLE dbo.etl_pipeline ADD sla_minutos INT NULL;
    PRINT '[OK] Coluna sla_minutos adicionada';
END
ELSE
    PRINT '[--] sla_minutos já existe';
GO

-- ambiente (Mig 007)
IF NOT EXISTS (SELECT 1 FROM sys.columns
               WHERE object_id = OBJECT_ID('dbo.etl_pipeline') AND name = 'ambiente')
BEGIN
    ALTER TABLE dbo.etl_pipeline ADD ambiente NVARCHAR(10) NULL DEFAULT 'PROD';
    PRINT '[OK] Coluna ambiente adicionada';
END
ELSE
    PRINT '[--] ambiente já existe';
GO

-- max_active_runs (Mig 007)
IF NOT EXISTS (SELECT 1 FROM sys.columns
               WHERE object_id = OBJECT_ID('dbo.etl_pipeline') AND name = 'max_active_runs')
BEGIN
    ALTER TABLE dbo.etl_pipeline ADD max_active_runs INT NULL DEFAULT 1;
    PRINT '[OK] Coluna max_active_runs adicionada';
END
ELSE
    PRINT '[--] max_active_runs já existe';
GO

-- retries_count (Mig 007)
IF NOT EXISTS (SELECT 1 FROM sys.columns
               WHERE object_id = OBJECT_ID('dbo.etl_pipeline') AND name = 'retries_count')
BEGIN
    ALTER TABLE dbo.etl_pipeline ADD retries_count INT NULL DEFAULT 1;
    PRINT '[OK] Coluna retries_count adicionada';
END
ELSE
    PRINT '[--] retries_count já existe';
GO

-- retry_delay_seconds (Mig 007)
IF NOT EXISTS (SELECT 1 FROM sys.columns
               WHERE object_id = OBJECT_ID('dbo.etl_pipeline') AND name = 'retry_delay_seconds')
BEGIN
    ALTER TABLE dbo.etl_pipeline ADD retry_delay_seconds INT NULL DEFAULT 300;
    PRINT '[OK] Coluna retry_delay_seconds adicionada';
END
ELSE
    PRINT '[--] retry_delay_seconds já existe';
GO

-- pool_name (Mig 007)
IF NOT EXISTS (SELECT 1 FROM sys.columns
               WHERE object_id = OBJECT_ID('dbo.etl_pipeline') AND name = 'pool_name')
BEGIN
    ALTER TABLE dbo.etl_pipeline ADD pool_name NVARCHAR(100) NULL;
    PRINT '[OK] Coluna pool_name adicionada';
END
ELSE
    PRINT '[--] pool_name já existe';
GO


-- ============================================================
-- SEÇÃO 4 — COLUNAS EM TABELAS DE LINEAGE
-- (Migrações 004, 005)
-- ============================================================

-- columns_json em etl_job_lineage (Mig 004)
IF NOT EXISTS (SELECT 1 FROM sys.columns
               WHERE object_id = OBJECT_ID('dbo.etl_job_lineage') AND name = 'columns_json')
BEGIN
    ALTER TABLE dbo.etl_job_lineage ADD columns_json NVARCHAR(MAX) NULL;
    PRINT '[OK] columns_json adicionado em etl_job_lineage';
END
ELSE
    PRINT '[--] etl_job_lineage.columns_json já existe';
GO

-- columns_json em etl_seq_import_lineage (Mig 004)
IF NOT EXISTS (SELECT 1 FROM sys.columns
               WHERE object_id = OBJECT_ID('dbo.etl_seq_import_lineage') AND name = 'columns_json')
BEGIN
    ALTER TABLE dbo.etl_seq_import_lineage ADD columns_json NVARCHAR(MAX) NULL;
    PRINT '[OK] columns_json adicionado em etl_seq_import_lineage';
END
ELSE
    PRINT '[--] etl_seq_import_lineage.columns_json já existe';
GO

-- Expandir object_type para NVARCHAR(100) (Mig 005)
IF COL_LENGTH('dbo.etl_job_lineage', 'object_type') < 100
BEGIN
    ALTER TABLE dbo.etl_job_lineage ALTER COLUMN object_type NVARCHAR(100) NULL;
    PRINT '[OK] etl_job_lineage.object_type expandido para NVARCHAR(100)';
END
ELSE
    PRINT '[--] etl_job_lineage.object_type já está correto';
GO

IF COL_LENGTH('dbo.etl_seq_import_lineage', 'object_type') < 100
BEGIN
    ALTER TABLE dbo.etl_seq_import_lineage ALTER COLUMN object_type NVARCHAR(100) NULL;
    PRINT '[OK] etl_seq_import_lineage.object_type expandido para NVARCHAR(100)';
END
ELSE
    PRINT '[--] etl_seq_import_lineage.object_type já está correto';
GO


-- ============================================================
-- SEÇÃO 5 — TABELAS DE GOVERNANÇA E METADADOS
-- (Migrações 006, 007, 008)
-- ============================================================

-- etl_pipeline_audit (Mig 002)
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE object_id = OBJECT_ID('dbo.etl_pipeline_audit'))
BEGIN
    CREATE TABLE dbo.etl_pipeline_audit (
        id            BIGINT IDENTITY(1,1) NOT NULL,
        pipeline_name NVARCHAR(200)        NOT NULL,
        changed_by    NVARCHAR(100)        NOT NULL DEFAULT 'system',
        field_name    NVARCHAR(100)        NOT NULL,
        old_value     NVARCHAR(MAX)        NULL,
        new_value     NVARCHAR(MAX)        NULL,
        changed_at    DATETIME2            NOT NULL DEFAULT GETDATE(),
        CONSTRAINT PK_etl_pipeline_audit PRIMARY KEY CLUSTERED (id ASC)
    );
    CREATE NONCLUSTERED INDEX IX_etl_pipeline_audit_pipeline
        ON dbo.etl_pipeline_audit (pipeline_name ASC, changed_at DESC);
    CREATE NONCLUSTERED INDEX IX_etl_pipeline_audit_user
        ON dbo.etl_pipeline_audit (changed_by ASC, changed_at DESC);
    PRINT '[OK] Tabela etl_pipeline_audit criada';
END
ELSE
    PRINT '[--] etl_pipeline_audit já existe';
GO

-- etl_versao_ferramenta (Mig 003)
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE object_id = OBJECT_ID('dbo.etl_versao_ferramenta'))
BEGIN
    CREATE TABLE dbo.etl_versao_ferramenta (
        id           INT IDENTITY(1,1) NOT NULL,
        versao       NVARCHAR(20)  NOT NULL,
        titulo       NVARCHAR(200) NOT NULL,
        descricao_md NVARCHAR(MAX) NULL,
        criado_em    DATETIME2     NOT NULL DEFAULT GETDATE(),
        criado_por   NVARCHAR(100) NOT NULL DEFAULT 'admin',
        CONSTRAINT PK_etl_versao_ferramenta PRIMARY KEY CLUSTERED (id ASC)
    );
    CREATE NONCLUSTERED INDEX IX_etl_versao_ferramenta_criado
        ON dbo.etl_versao_ferramenta (criado_em DESC);
    PRINT '[OK] Tabela etl_versao_ferramenta criada';
END
ELSE
    PRINT '[--] etl_versao_ferramenta já existe';
GO

-- etl_pipeline_owner (Mig 006)
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE object_id = OBJECT_ID('dbo.etl_pipeline_owner'))
BEGIN
    CREATE TABLE dbo.etl_pipeline_owner (
        pipeline_name  NVARCHAR(300) NOT NULL,
        owner_name     NVARCHAR(100) NULL,
        owner_email    NVARCHAR(150) NULL,
        steward_name   NVARCHAR(100) NULL,
        steward_email  NVARCHAR(150) NULL,
        updated_at     DATETIME      NOT NULL DEFAULT GETDATE(),
        updated_by     NVARCHAR(100) NULL,
        CONSTRAINT PK_etl_pipeline_owner PRIMARY KEY (pipeline_name)
    );
    PRINT '[OK] Tabela etl_pipeline_owner criada';
END
ELSE
    PRINT '[--] etl_pipeline_owner já existe';
GO

-- etl_object_tag (Mig 006)
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE object_id = OBJECT_ID('dbo.etl_object_tag'))
BEGIN
    CREATE TABLE dbo.etl_object_tag (
        id            INT IDENTITY(1,1) NOT NULL,
        object_key    VARCHAR(400)  NOT NULL,
        tag           VARCHAR(50)   NOT NULL,
        added_by      VARCHAR(100)  NULL,
        added_at      DATETIME      NOT NULL DEFAULT GETDATE(),
        CONSTRAINT PK_etl_object_tag PRIMARY KEY CLUSTERED (id ASC),
        CONSTRAINT UQ_object_tag UNIQUE (object_key, tag)
    );
    PRINT '[OK] Tabela etl_object_tag criada';
END
ELSE
    PRINT '[--] etl_object_tag já existe';
GO

-- etl_project (Mig 007)
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE object_id = OBJECT_ID('dbo.etl_project'))
BEGIN
    CREATE TABLE dbo.etl_project (
        project_name  NVARCHAR(100) NOT NULL,
        descricao     NVARCHAR(300) NULL,
        ativo         BIT           NOT NULL DEFAULT 1,
        criado_em     DATETIME      NOT NULL DEFAULT GETDATE(),
        CONSTRAINT PK_etl_project PRIMARY KEY (project_name)
    );
    PRINT '[OK] Tabela etl_project criada';
END
ELSE
    PRINT '[--] etl_project já existe';
GO

-- etl_job_type (Mig 008)
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE object_id = OBJECT_ID('dbo.etl_job_type'))
BEGIN
    CREATE TABLE dbo.etl_job_type (
        id              INT IDENTITY(1,1) NOT NULL,
        nome            NVARCHAR(100)     NOT NULL,
        descricao       NVARCHAR(500)     NULL,
        lineage_enabled BIT               NOT NULL DEFAULT 1,
        status          BIT               NOT NULL DEFAULT 1,
        criado_em       DATETIME2         NOT NULL DEFAULT GETDATE(),
        criado_por      NVARCHAR(100)     NOT NULL DEFAULT 'admin',
        CONSTRAINT PK_etl_job_type PRIMARY KEY CLUSTERED (id ASC),
        CONSTRAINT UQ_etl_job_type_nome UNIQUE (nome)
    );
    PRINT '[OK] Tabela etl_job_type criada';
END
ELSE
    PRINT '[--] etl_job_type já existe';
GO

-- etl_teste_execucao (Mig 009)
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE object_id = OBJECT_ID('dbo.etl_teste_execucao'))
BEGIN
    CREATE TABLE dbo.etl_teste_execucao (
        id            INT IDENTITY(1,1) NOT NULL,
        tipo_teste    NVARCHAR(50)  NOT NULL,
        resultado     NVARCHAR(500) NOT NULL,
        executado_em  DATETIME2     NOT NULL DEFAULT GETDATE(),
        CONSTRAINT PK_etl_teste_execucao PRIMARY KEY (id)
    );
    PRINT '[OK] Tabela etl_teste_execucao criada';
END
ELSE
    PRINT '[--] etl_teste_execucao já existe';
GO


-- ============================================================
-- SEÇÃO 6 — SEED DE DADOS
-- ============================================================

-- Projetos padrão
IF NOT EXISTS (SELECT 1 FROM dbo.etl_project WHERE project_name = 'BI_CVP')
    INSERT INTO dbo.etl_project (project_name) VALUES ('BI_CVP');
IF NOT EXISTS (SELECT 1 FROM dbo.etl_project WHERE project_name = 'BI_VIDA')
    INSERT INTO dbo.etl_project (project_name) VALUES ('BI_VIDA');
IF NOT EXISTS (SELECT 1 FROM dbo.etl_project WHERE project_name = 'BI_PRESTAMISTA')
    INSERT INTO dbo.etl_project (project_name) VALUES ('BI_PRESTAMISTA');
IF NOT EXISTS (SELECT 1 FROM dbo.etl_project WHERE project_name = 'BI_PREVIDENCIA')
    INSERT INTO dbo.etl_project (project_name) VALUES ('BI_PREVIDENCIA');
IF NOT EXISTS (SELECT 1 FROM dbo.etl_project WHERE project_name = 'PORTAL_ECONOMIARIO')
    INSERT INTO dbo.etl_project (project_name) VALUES ('PORTAL_ECONOMIARIO');
IF NOT EXISTS (SELECT 1 FROM dbo.etl_project WHERE project_name = 'TESTE_ORQUESTRA')
    INSERT INTO dbo.etl_project (project_name, ativo) VALUES ('TESTE_ORQUESTRA', 1);
PRINT '[OK] Seed de projetos aplicado';
GO

-- Tipos de job padrão (inserção individual para idempotência)
IF NOT EXISTS (SELECT 1 FROM dbo.etl_job_type WHERE nome = 'SQL')
    INSERT INTO dbo.etl_job_type (nome, descricao, lineage_enabled, status)
    VALUES ('SQL', 'Script SQL em banco relacional (SELECT/INSERT/UPDATE/MERGE)', 1, 1);

IF NOT EXISTS (SELECT 1 FROM dbo.etl_job_type WHERE nome = 'Python')
    INSERT INTO dbo.etl_job_type (nome, descricao, lineage_enabled, status)
    VALUES ('Python', 'Script Python — pandas, requests, transformações customizadas', 1, 1);

IF NOT EXISTS (SELECT 1 FROM dbo.etl_job_type WHERE nome = 'Bash')
    INSERT INTO dbo.etl_job_type (nome, descricao, lineage_enabled, status)
    VALUES ('Bash', 'Script shell / bash para operações de sistema ou chamadas externas', 0, 1);

IF NOT EXISTS (SELECT 1 FROM dbo.etl_job_type WHERE nome = 'Spark')
    INSERT INTO dbo.etl_job_type (nome, descricao, lineage_enabled, status)
    VALUES ('Spark', 'Job PySpark / Spark SQL para processamento distribuído', 1, 1);

IF NOT EXISTS (SELECT 1 FROM dbo.etl_job_type WHERE nome = 'dbt')
    INSERT INTO dbo.etl_job_type (nome, descricao, lineage_enabled, status)
    VALUES ('dbt', 'Modelo dbt (Data Build Tool) para transformações declarativas', 1, 1);

IF NOT EXISTS (SELECT 1 FROM dbo.etl_job_type WHERE nome = 'DataStage')
    INSERT INTO dbo.etl_job_type (nome, descricao, lineage_enabled, status)
    VALUES ('DataStage', 'Job IBM DataStage exportado via arquivo .dsx', 1, 1);

IF NOT EXISTS (SELECT 1 FROM dbo.etl_job_type WHERE nome = 'SSIS')
    INSERT INTO dbo.etl_job_type (nome, descricao, lineage_enabled, status)
    VALUES ('SSIS', 'Pacote SSIS (SQL Server Integration Services)', 1, 1);

IF NOT EXISTS (SELECT 1 FROM dbo.etl_job_type WHERE nome = 'HTTP')
    INSERT INTO dbo.etl_job_type (nome, descricao, lineage_enabled, status)
    VALUES ('HTTP', 'Chamada de API REST / webhook externo', 0, 1);

IF NOT EXISTS (SELECT 1 FROM dbo.etl_job_type WHERE nome = 'StoredProc')
    INSERT INTO dbo.etl_job_type (nome, descricao, lineage_enabled, status)
    VALUES ('StoredProc', 'Stored Procedure SQL Server', 1, 1);

PRINT '[OK] Seed de tipos de job aplicado';
GO

-- Parâmetros de configuração
IF NOT EXISTS (SELECT 1 FROM dbo.etl_configuracao WHERE chave = 'audit_history_limit')
    INSERT INTO dbo.etl_configuracao (chave, valor, descricao)
    VALUES ('audit_history_limit', '9',
            'Número máximo de registros de alteração mantidos por pipeline no audit trail (excluindo o registro de criação).');

IF NOT EXISTS (SELECT 1 FROM dbo.etl_configuracao WHERE chave = 'dashboard_refresh_interval_sec')
    INSERT INTO dbo.etl_configuracao (chave, valor, descricao)
    VALUES ('dashboard_refresh_interval_sec', '60', 'Intervalo de auto-refresh do dashboard em segundos.');

IF NOT EXISTS (SELECT 1 FROM dbo.etl_configuracao WHERE chave = 'app_version')
    INSERT INTO dbo.etl_configuracao (chave, valor, descricao)
    VALUES ('app_version', '2.1.0', 'Versão atual do ORQUESTRA.');

PRINT '[OK] Seed de configurações aplicado';
GO

-- Ambiente padrão PROD para pipelines sem ambiente
UPDATE dbo.etl_pipeline
SET ambiente = 'PROD'
WHERE ambiente IS NULL OR LTRIM(RTRIM(ambiente)) = '';
PRINT '[OK] Pipelines sem ambiente definido atualizados para PROD';
GO


-- ============================================================
-- SEÇÃO 7 — STORED PROCEDURES DE TESTE (DEV/HML apenas)
-- ============================================================

IF OBJECT_ID('dbo.sp_teste_orquestra_sql', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_teste_orquestra_sql;
GO

CREATE PROCEDURE dbo.sp_teste_orquestra_sql
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @resultado NVARCHAR(200);
    SET @resultado = 'ORQUESTRA_TEST_OK — executado em ' + CONVERT(VARCHAR(30), GETDATE(), 120);

    IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE object_id = OBJECT_ID('dbo.etl_teste_execucao'))
    BEGIN
        CREATE TABLE dbo.etl_teste_execucao (
            id           INT IDENTITY(1,1) PRIMARY KEY,
            tipo_teste   NVARCHAR(50)  NOT NULL,
            resultado    NVARCHAR(500) NOT NULL,
            executado_em DATETIME2     NOT NULL DEFAULT GETDATE()
        );
    END

    INSERT INTO dbo.etl_teste_execucao (tipo_teste, resultado)
    VALUES ('SQL_STOREDPROC', @resultado);

    SELECT @resultado AS resultado, GETDATE() AS executado_em;
    PRINT 'Job Status Code: 1';
END;
GO
PRINT '[OK] sp_teste_orquestra_sql criada/atualizada';
GO


-- ============================================================
-- SEÇÃO 8 — VERIFICAÇÃO FINAL
-- ============================================================

PRINT '';
PRINT '============================================================';
PRINT ' Verificação de tabelas e contagens';
PRINT '============================================================';

SELECT
    t.name                          AS tabela,
    p.rows                          AS total_linhas,
    CASE WHEN t.name IN (
        'etl_pipeline','etl_pipeline_job','etl_job_execution',
        'etl_job_lineage','etl_seq_import_lineage','etl_stage_type_map',
        'etl_configuracao','etl_pipeline_audit','etl_versao_ferramenta',
        'etl_pipeline_owner','etl_object_tag','etl_project',
        'etl_job_type','etl_teste_execucao'
    ) THEN 'CORE' ELSE 'EXTRA' END  AS tipo
FROM sys.tables t
JOIN sys.partitions p ON p.object_id = t.object_id AND p.index_id IN (0,1)
WHERE t.schema_id = SCHEMA_ID('dbo')
  AND t.name LIKE 'etl_%'
ORDER BY t.name;
GO

PRINT '';
PRINT ' Colunas extras em etl_pipeline:';
SELECT name, TYPE_NAME(user_type_id) AS tipo, max_length, is_nullable
FROM sys.columns
WHERE object_id = OBJECT_ID('dbo.etl_pipeline')
ORDER BY column_id;
GO

PRINT '';
PRINT ' Stored procedures registradas:';
SELECT name, create_date, modify_date
FROM sys.procedures
WHERE schema_id = SCHEMA_ID('dbo')
  AND name LIKE '%etl%' OR name LIKE '%orquestra%'
ORDER BY name;
GO

PRINT '';
PRINT '============================================================';
PRINT ' Deploy concluído em: ' + CONVERT(VARCHAR(30), GETDATE(), 120);
PRINT '============================================================';
GO
