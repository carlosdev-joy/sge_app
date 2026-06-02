USE [DMDB41];
GO

/* ============================================================
   ORQUESTRA — Importação de Sequence (v1.0)
   Aprovação: move staging -> produção
   - cria/atualiza pipeline
   - cria/atualiza jobs (ignora os marcados)
   - insere lineage em dbo.etl_job_lineage
   ============================================================ */

CREATE OR ALTER PROCEDURE [dbo].[sp_etl_seq_import_approve]
(
    @import_id   INT,
    @reviewed_by NVARCHAR(100)
)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    BEGIN TRY
        BEGIN TRAN;

        DECLARE
            @pipeline_name NVARCHAR(200),
            @project_name  NVARCHAR(50),
            @domain        NVARCHAR(100),
            @stype         VARCHAR(20),
            @shour         TINYINT,
            @smin          TINYINT,
            @sdow          TINYINT,
            @sdom          TINYINT,
            @stime         TIME(0);

        SELECT
            @pipeline_name = COALESCE(NULLIF(pipeline_name_override,''), NULLIF(pipeline_name_suggest,'')),
            @project_name  = project_name,
            @domain        = COALESCE(NULLIF(domain,''), 'GERAL'),
            @stype         = schedule_type,
            @shour         = schedule_hour,
            @smin          = schedule_minute,
            @sdow          = schedule_dow,
            @sdom          = schedule_dom,
            @stime         = scheduled_time
        FROM dbo.etl_seq_import
        WHERE id = @import_id
          AND status = 'pendente_aprovacao';

        IF @pipeline_name IS NULL
            RAISERROR('Import %d sem pipeline_name definido (suggest/override).', 16, 1, @import_id);

        -- scheduled_time: se não vier preenchido, deriva de hour/minute; fallback 06:00
        IF @stime IS NULL
        BEGIN
            DECLARE @hh INT = ISNULL(CAST(@shour AS INT), 6);
            DECLARE @mm INT = ISNULL(CAST(@smin  AS INT), 0);
            SET @stime = TIMEFROMPARTS(@hh, @mm, 0, 0, 0);
        END

        EXEC dbo.sp_etl_pipeline_upsert
            @pipeline_name    = @pipeline_name,
            @scheduled_time   = @stime,
            @schedule_type    = @stype,
            @schedule_hour    = @shour,
            @schedule_minute  = @smin,
            @schedule_dow     = @sdow,
            @schedule_dom     = @sdom,
            @active           = 1,
            @envia_msg_inicio = 1,
            @envia_msg_fim    = 1,
            @envia_msg_erro   = 1,
            @dag_criada       = 0,
            @project_name     = @project_name,
            @domain           = @domain,
            @tags             = '';

        -- Jobs
        DECLARE @jobs TABLE (
            execution_order INT,
            job_name_orq NVARCHAR(200),
            job_type NVARCHAR(50),
            job_command NVARCHAR(500)
        );

        INSERT INTO @jobs (execution_order, job_name_orq, job_type, job_command)
        SELECT
            j.execution_order,
            j.job_name_orq,
            'datastage' AS job_type,
            NULL AS job_command
        FROM dbo.etl_seq_import_job j
        WHERE j.import_id = @import_id
          AND j.ignored = 0;

        -- Recria jobs do pipeline (simplifica e evita inconsistência)
        DELETE FROM dbo.etl_pipeline_job WHERE pipeline_name = @pipeline_name;

        INSERT INTO dbo.etl_pipeline_job (pipeline_name, job_name, execution_order, job_type, job_command, active, created_at, updated_at)
        SELECT
            @pipeline_name, job_name_orq, execution_order, job_type, job_command,
            1, SYSDATETIME(), SYSDATETIME()
        FROM @jobs
        ORDER BY execution_order;

        -- Lineage: remove anterior e re-insere (idempotente)
        DELETE l
        FROM dbo.etl_job_lineage l
        WHERE l.pipeline_name = @pipeline_name;

        INSERT INTO dbo.etl_job_lineage
        (
            pipeline_name, job_name, direction, object_type, object_name,
            stage_name, stage_type_raw, database_name, sql_expression, file_path,
            dsx_source_file, extracted_at, extraction_method,
            created_at, updated_at
        )
        SELECT
            @pipeline_name,
            j.job_name_orq,
            l.direction,
            l.object_type,
            l.object_name,
            l.stage_name,
            l.stage_type_raw,
            l.database_name,
            l.sql_expression,
            l.file_path,
            l.dsx_source_file,
            l.extracted_at,
            l.extraction_method,
            SYSDATETIME(), SYSDATETIME()
        FROM dbo.etl_seq_import_lineage l
        INNER JOIN dbo.etl_seq_import_job j
            ON j.id = l.import_job_id
        WHERE l.import_id = @import_id
          AND j.ignored = 0;

        UPDATE dbo.etl_seq_import
        SET
            status = 'aprovado',
            reviewed_by = @reviewed_by,
            updated_at = SYSDATETIME()
        WHERE id = @import_id;

        COMMIT;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK;
        DECLARE @ErrorMessage NVARCHAR(4000) = ERROR_MESSAGE();
        DECLARE @ErrorSeverity INT = ERROR_SEVERITY();
        RAISERROR (@ErrorMessage, @ErrorSeverity, 1);
    END CATCH
END
GO

