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
        @schedule_dom    TINYINT,
        @scheduled_time  TIME(0);

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

    -- Derivar @scheduled_time a partir de schedule_hour/schedule_minute
    SET @scheduled_time = CAST(
        RIGHT('00' + CAST(COALESCE(@schedule_hour,   0) AS VARCHAR(2)), 2) + ':' +
        RIGHT('00' + CAST(COALESCE(@schedule_minute, 0) AS VARCHAR(2)), 2) + ':00'
    AS TIME(0));

    BEGIN TRANSACTION;
    BEGIN TRY

        -- ── 1. Criar o pipeline em etl_pipeline ───────────────────────────
        EXEC dbo.sp_etl_pipeline_upsert
            @pipeline_name   = @pipeline_name,
            @project_name    = @project_name,
            @domain          = @domain,
            @scheduled_time  = @scheduled_time,
            @schedule_type   = @schedule_type,
            @schedule_hour   = @schedule_hour,
            @schedule_minute = @schedule_minute,
            @schedule_dow    = @schedule_dow,
            @schedule_dom    = @schedule_dom;

        -- ── 2. UPSERT jobs (permite reimportação sem duplicatas) ─────────
        MERGE dbo.etl_pipeline_job AS tgt
        USING (
            SELECT
                @pipeline_name  AS pipeline_name,
                j.job_name_orq  AS job_name,
                j.execution_order,
                j.job_type,
                j.job_command
            FROM dbo.etl_seq_import_job j
            WHERE j.import_id = @import_id
              AND j.status    <> 'ignorado'
        ) AS src
        ON tgt.pipeline_name = src.pipeline_name
       AND tgt.job_name      = src.job_name
        WHEN MATCHED THEN
            UPDATE SET
                execution_order = src.execution_order,
                job_type        = src.job_type,
                job_command     = src.job_command,
                updated_at      = GETDATE()
        WHEN NOT MATCHED THEN
            INSERT (pipeline_name, job_name, execution_order, job_type, job_command, created_at, updated_at)
            VALUES (src.pipeline_name, src.job_name, src.execution_order, src.job_type, src.job_command, GETDATE(), GETDATE());

        -- Marcar jobs staging como aprovados
        UPDATE dbo.etl_seq_import_job
        SET status = 'aprovado'
        WHERE import_id = @import_id
          AND status    <> 'ignorado';

        -- ── 3. UPSERT lineage (permite reimportação sem duplicatas) ──────
        -- Remove lineage existente do pipeline/job para reinserir limpa
        DELETE tgt
        FROM dbo.etl_job_lineage tgt
        WHERE tgt.pipeline_name = @pipeline_name
          AND tgt.job_name IN (
              SELECT j.job_name_orq
              FROM dbo.etl_seq_import_job j
              WHERE j.import_id = @import_id AND j.status = 'aprovado'
          );

        INSERT INTO dbo.etl_job_lineage (
            pipeline_name, job_name, direction,
            object_name, object_type, stage_name, stage_type_raw,
            database_name, sql_expression, file_path,
            dsx_source_file, extracted_at, extraction_method,
            columns_json, created_at, updated_at
        )
        SELECT
            @pipeline_name,
            j.job_name_orq,
            l.direction,
            l.object_name,
            l.object_type,
            l.object_name,
            l.stage_type_raw,
            l.database_name,
            l.sql_expression,
            l.file_path,
            l.dsx_source_file,
            GETDATE(),
            l.extraction_method,
            l.columns_json,
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
