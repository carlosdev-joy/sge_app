-- =============================================================================
-- ORQUESTRA — Importação de Sequence DataStage
-- Script SQL: Tabelas de Staging + Stored Procedure de Aprovação
-- Banco: DMDB41 | Schema: dbo
-- =============================================================================

-- =============================================================================
-- 1. etl_seq_import — Cabeçalho de cada importação
-- =============================================================================
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'etl_seq_import'
)
BEGIN
    CREATE TABLE dbo.etl_seq_import (
        id                      INT          IDENTITY(1,1) PRIMARY KEY,
        dsx_filename            VARCHAR(500) NOT NULL,   -- ex: BI_CVP.dsx
        seq_name_raw            VARCHAR(500) NOT NULL,   -- nome decodificado da sequence
        seq_name                VARCHAR(500) NOT NULL,   -- mesmo campo (alias para clareza)
        project_name            VARCHAR(100) NOT NULL,   -- ex: BI_CVP
        domain                  VARCHAR(100) NULL,       -- domínio no ORQUESTRA (editável)
        pipeline_name_override  VARCHAR(300) NULL,       -- nome do pipeline no ORQUESTRA (editável)
        schedule_type           VARCHAR(20)  NULL,       -- hourly | daily | weekly | monthly
        schedule_cron           VARCHAR(100) NULL,       -- ex: 30 6 * * *
        schedule_hour           TINYINT      NULL,       -- 0-23
        schedule_minute         TINYINT      NULL,       -- 0-59
        schedule_dow            TINYINT      NULL,       -- 0=Dom ... 6=Sab (para weekly)
        schedule_dom            TINYINT      NULL,       -- 1-31 (para monthly)
        status                  VARCHAR(30)  NOT NULL DEFAULT 'pendente_aprovacao',
            -- pendente_aprovacao | aprovado | rejeitado | expirado
        obs                     VARCHAR(1000) NULL,
        imported_by             VARCHAR(100) NOT NULL,
        imported_at             DATETIME     NOT NULL DEFAULT GETDATE(),
        reviewed_by             VARCHAR(100) NULL,
        reviewed_at             DATETIME     NULL,
        pipeline_id             INT          NULL        -- FK etl_pipeline após aprovação
    );

    PRINT 'Tabela dbo.etl_seq_import criada.';
END
ELSE
    PRINT 'Tabela dbo.etl_seq_import já existe — ignorado.';
GO

-- Índice para busca por status
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_seq_import_status')
    CREATE NONCLUSTERED INDEX IX_seq_import_status
    ON dbo.etl_seq_import (status, imported_at DESC);
GO

-- =============================================================================
-- 2. etl_seq_import_job — Jobs da sequence
-- =============================================================================
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'etl_seq_import_job'
)
BEGIN
    CREATE TABLE dbo.etl_seq_import_job (
        id                  INT          IDENTITY(1,1) PRIMARY KEY,
        import_id           INT          NOT NULL
            REFERENCES dbo.etl_seq_import(id) ON DELETE CASCADE,
        execution_order     INT          NOT NULL,       -- posição na cadeia (0, 1, 2...)
        job_name_ds         VARCHAR(300) NOT NULL,       -- nome original no DataStage
        job_name_orq        VARCHAR(300) NOT NULL,       -- nome sugerido para o ORQUESTRA (editável)
        job_type            VARCHAR(30)  NOT NULL DEFAULT 'datastage',
        job_command         VARCHAR(1000) NULL,
        status              VARCHAR(30)  NOT NULL DEFAULT 'pendente',
            -- pendente | aprovado | ignorado
        lineage_extracted   BIT          NOT NULL DEFAULT 0,
        lineage_count       INT          NOT NULL DEFAULT 0,
        pipeline_job_id     INT          NULL            -- FK etl_pipeline_job após aprovação
    );

    PRINT 'Tabela dbo.etl_seq_import_job criada.';
END
ELSE
    PRINT 'Tabela dbo.etl_seq_import_job já existe — ignorado.';
GO

-- =============================================================================
-- 3. etl_seq_import_lineage — Lineage staging por job
-- =============================================================================
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'etl_seq_import_lineage'
)
BEGIN
    CREATE TABLE dbo.etl_seq_import_lineage (
        id                  INT          IDENTITY(1,1) PRIMARY KEY,
        import_job_id       INT          NOT NULL
            REFERENCES dbo.etl_seq_import_job(id) ON DELETE CASCADE,
        direction           VARCHAR(20)  NOT NULL,       -- origem | destino | transformacao
        object_name         VARCHAR(300) NOT NULL,
        object_type         VARCHAR(100) NULL,
        stage_type_raw      VARCHAR(100) NULL,
        sql_expression      VARCHAR(MAX) NULL,           -- tabelas extraídas (1 por linha)
        file_path           VARCHAR(500) NULL,           -- path DataSet
        database_name       VARCHAR(255) NULL,
        dsx_source_file     VARCHAR(500) NULL,
        extraction_method   VARCHAR(50)  NULL DEFAULT 'dsx_auto',
        status              VARCHAR(30)  NOT NULL DEFAULT 'pendente',
            -- pendente | aprovado | ignorado
        lineage_id          INT          NULL            -- FK etl_job_lineage após aprovação
    );

    PRINT 'Tabela dbo.etl_seq_import_lineage criada.';
END
ELSE
    PRINT 'Tabela dbo.etl_seq_import_lineage já existe — ignorado.';
GO

-- =============================================================================
-- 4. sp_etl_seq_import_approve — Move staging → produção em transação única
-- =============================================================================
IF OBJECT_ID('dbo.sp_etl_seq_import_approve', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_etl_seq_import_approve;
GO

CREATE PROCEDURE dbo.sp_etl_seq_import_approve
    @import_id   INT,
    @reviewed_by VARCHAR(100)
AS
BEGIN
    SET NOCOUNT ON;

    -- Verificações iniciais
    IF NOT EXISTS (SELECT 1 FROM dbo.etl_seq_import WHERE id = @import_id)
        THROW 50001, 'Importação não encontrada.', 1;

    IF NOT EXISTS (
        SELECT 1 FROM dbo.etl_seq_import
        WHERE id = @import_id AND status = 'pendente_aprovacao'
    )
        THROW 50002, 'A importação não está com status pendente_aprovacao.', 1;

    DECLARE
        @pipeline_name  VARCHAR(300),
        @project_name   VARCHAR(100),
        @domain         VARCHAR(100),
        @schedule_cron  VARCHAR(100),
        @schedule_type  VARCHAR(20),
        @schedule_hour  TINYINT,
        @schedule_minute TINYINT,
        @schedule_dow   TINYINT,
        @schedule_dom   TINYINT;

    SELECT
        @pipeline_name  = COALESCE(pipeline_name_override, seq_name),
        @project_name   = project_name,
        @domain         = domain,
        @schedule_cron  = schedule_cron,
        @schedule_type  = schedule_type,
        @schedule_hour  = schedule_hour,
        @schedule_minute= schedule_minute,
        @schedule_dow   = schedule_dow,
        @schedule_dom   = schedule_dom
    FROM dbo.etl_seq_import
    WHERE id = @import_id;

    BEGIN TRANSACTION;
    BEGIN TRY

        -- ── 1. Criar o pipeline em etl_pipeline ─────────────────────────────
        EXEC dbo.sp_etl_pipeline_upsert
            @pipeline_name   = @pipeline_name,
            @project_name    = @project_name,
            @domain          = @domain,
            @schedule        = @schedule_cron,
            @schedule_type   = @schedule_type,
            @schedule_hour   = @schedule_hour,
            @schedule_minute = @schedule_minute,
            @schedule_dow    = @schedule_dow,
            @schedule_dom    = @schedule_dom;

        -- ── 2. Criar os jobs (apenas status != 'ignorado') ──────────────────
        INSERT INTO dbo.etl_pipeline_job (
            pipeline_name, job_name, execution_order, job_type, job_command,
            created_at, updated_at
        )
        SELECT
            @pipeline_name,
            j.job_name_orq,
            j.execution_order,
            j.job_type,
            j.job_command,
            GETDATE(),
            GETDATE()
        FROM dbo.etl_seq_import_job j
        WHERE j.import_id = @import_id
          AND j.status    <> 'ignorado'
        ORDER BY j.execution_order;

        -- Atualizar FK nos staging jobs
        UPDATE sj
        SET sj.pipeline_job_id = pj.id,
            sj.status          = 'aprovado'
        FROM dbo.etl_seq_import_job sj
        JOIN dbo.etl_pipeline_job   pj
            ON pj.pipeline_name = @pipeline_name
           AND pj.job_name       = sj.job_name_orq
        WHERE sj.import_id = @import_id
          AND sj.status    <> 'ignorado';

        -- ── 3. Criar lineage (apenas status != 'ignorado') ──────────────────
        INSERT INTO dbo.etl_job_lineage (
            pipeline_name, job_name, direction,
            object_name, object_type, stage_name, stage_type_raw,
            database_name, sql_expression, file_path,
            dsx_source_file, extracted_at, extraction_method,
            created_at, updated_at
        )
        SELECT
            @pipeline_name,
            j.job_name_orq,
            l.direction,
            l.object_name,
            l.object_type,
            l.object_name,         -- stage_name = object_name
            l.stage_type_raw,
            l.database_name,
            l.sql_expression,
            l.file_path,
            l.dsx_source_file,
            GETDATE(),
            l.extraction_method,
            GETDATE(),
            GETDATE()
        FROM dbo.etl_seq_import_lineage l
        JOIN dbo.etl_seq_import_job     j ON l.import_job_id = j.id
        WHERE j.import_id = @import_id
          AND l.status    <> 'ignorado'
          AND j.status    <> 'ignorado';

        -- Atualizar FK nos staging lineage
        UPDATE sl
        SET sl.lineage_id = jl.id,
            sl.status     = 'aprovado'
        FROM dbo.etl_seq_import_lineage sl
        JOIN dbo.etl_seq_import_job     sj  ON sl.import_job_id = sj.id
        JOIN dbo.etl_job_lineage        jl
            ON  jl.pipeline_name = @pipeline_name
            AND jl.job_name      = sj.job_name_orq
            AND jl.direction     = sl.direction
            AND jl.object_name   = sl.object_name
        WHERE sj.import_id = @import_id;

        -- ── 4. Atualizar etl_pipeline.id no cabeçalho ───────────────────────
        UPDATE dbo.etl_seq_import
        SET status      = 'aprovado',
            reviewed_by = @reviewed_by,
            reviewed_at = GETDATE(),
            pipeline_id = (
                SELECT id FROM dbo.etl_pipeline
                WHERE pipeline_name = @pipeline_name
            )
        WHERE id = @import_id;

        COMMIT TRANSACTION;

        PRINT 'Pipeline "' + @pipeline_name + '" importado com sucesso.';

    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;

        DECLARE
            @err_num  INT          = ERROR_NUMBER(),
            @err_msg  NVARCHAR(MAX)= ERROR_MESSAGE(),
            @err_line INT          = ERROR_LINE();

        -- Marcar importação como erro (sem alterar para evitar perda dos dados)
        UPDATE dbo.etl_seq_import
        SET obs = LEFT('ERRO na aprovação (linha ' + CAST(@err_line AS VARCHAR) + '): ' + @err_msg, 1000)
        WHERE id = @import_id;

        THROW;
    END CATCH
END;
GO

PRINT '==> sp_etl_seq_import_approve criada com sucesso.';
GO
