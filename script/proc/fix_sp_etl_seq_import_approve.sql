-- =============================================================================
-- ORQUESTRA — Correção: sp_etl_seq_import_approve
-- Problema: referências a colunas 'id' que não existem em etl_pipeline
--           e etl_pipeline_job (essas tabelas usam pipeline_name como chave)
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

    -- ── Verificações iniciais ──────────────────────────────────────────────
    IF NOT EXISTS (SELECT 1 FROM dbo.etl_seq_import WHERE id = @import_id)
        THROW 50001, 'Importação não encontrada.', 1;

    IF NOT EXISTS (
        SELECT 1 FROM dbo.etl_seq_import
        WHERE id = @import_id AND status = 'pendente_aprovacao'
    )
        THROW 50002, 'A importação não está com status pendente_aprovacao.', 1;

    DECLARE
        @pipeline_name   VARCHAR(300),
        @project_name    VARCHAR(100),
        @domain          VARCHAR(100),
        @schedule_cron   VARCHAR(100),
        @schedule_type   VARCHAR(20),
        @schedule_hour   TINYINT,
        @schedule_minute TINYINT,
        @schedule_dow    TINYINT,
        @schedule_dom    TINYINT;

    SELECT
        @pipeline_name   = COALESCE(pipeline_name_override, seq_name),
        @project_name    = project_name,
        @domain          = domain,
        @schedule_cron   = schedule_cron,
        @schedule_type   = schedule_type,
        @schedule_hour   = schedule_hour,
        @schedule_minute = schedule_minute,
        @schedule_dow    = schedule_dow,
        @schedule_dom    = schedule_dom
    FROM dbo.etl_seq_import
    WHERE id = @import_id;

    BEGIN TRANSACTION;
    BEGIN TRY

        -- ── 1. Criar o pipeline em etl_pipeline ───────────────────────────
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

        -- ── 2. Criar os jobs (apenas status != 'ignorado') ────────────────
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

        -- Marcar jobs staging como aprovados
        -- (sem FK para etl_pipeline_job.id pois essa tabela usa pipeline_name+job_name como chave)
        UPDATE dbo.etl_seq_import_job
        SET status = 'aprovado'
        WHERE import_id = @import_id
          AND status    <> 'ignorado';

        -- ── 3. Criar lineage (apenas status != 'ignorado') ────────────────
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
            l.object_name,        -- stage_name = object_name
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
          AND j.status    = 'aprovado';

        -- Marcar lineage staging como aprovada
        UPDATE l
        SET l.status = 'aprovado'
        FROM dbo.etl_seq_import_lineage l
        JOIN dbo.etl_seq_import_job     j ON l.import_job_id = j.id
        WHERE j.import_id = @import_id;

        -- ── 4. Atualizar status do cabeçalho ──────────────────────────────
        -- Sem referência a etl_pipeline.id (essa tabela usa pipeline_name como chave)
        UPDATE dbo.etl_seq_import
        SET status      = 'aprovado',
            reviewed_by = @reviewed_by,
            reviewed_at = GETDATE()
        WHERE id = @import_id;

        COMMIT TRANSACTION;
        PRINT 'Pipeline "' + @pipeline_name + '" importado com sucesso.';

    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;

        DECLARE
            @err_num  INT           = ERROR_NUMBER(),
            @err_msg  NVARCHAR(MAX) = ERROR_MESSAGE(),
            @err_line INT           = ERROR_LINE();

        UPDATE dbo.etl_seq_import
        SET obs = LEFT(
            'ERRO na aprovação (linha ' + CAST(@err_line AS VARCHAR) + '): ' + @err_msg,
            1000
        )
        WHERE id = @import_id;

        THROW;
    END CATCH
END;
GO

PRINT '==> sp_etl_seq_import_approve recriada com sucesso (sem referências a .id inexistentes).';
GO
