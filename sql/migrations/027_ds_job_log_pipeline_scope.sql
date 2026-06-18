-- Migration 027 — Corrige upserts de log/execução para considerar pipeline
--
-- Bug: execution_id é derivado de ts_nodash (timestamp da DAG run), sem
-- nenhuma referência ao pipeline. Duas pipelines diferentes agendadas para
-- o mesmo horário podem gerar o MESMO execution_id. Os upserts de
-- etl_ds_job_log e etl_job_execution filtravam apenas por
-- (execution_id, job_name[, task_id]), então o log/execução de uma
-- pipeline podia sobrescrever ou aparecer no lugar do log da outra quando
-- ambas tinham um job com o mesmo nome.
--
-- Fase 1 da correção (mitigação de baixo risco, sem mudança de schema):
-- inclui pipeline/pipeline_name no WHERE de busca/atualização dos upserts.

CREATE OR ALTER PROCEDURE dbo.sp_etl_ds_job_log_upsert
    @execution_id   VARCHAR(50),
    @pipeline_name  VARCHAR(200),
    @job_name       VARCHAR(200),
    @project        VARCHAR(100),
    @wave_number    INT,
    @pid            VARCHAR(20),
    @status         VARCHAR(50),
    @status_code    INT,
    @child_jobs     NVARCHAR(MAX),
    @log_summary    NVARCHAR(MAX),
    @poll_snapshot  NVARCHAR(MAX),
    @ds_start_time  VARCHAR(50)  = NULL,
    @ds_end_time    DATETIME     = NULL
AS
BEGIN
    SET NOCOUNT ON;

    IF EXISTS (
        SELECT 1 FROM dbo.etl_ds_job_log
        WHERE execution_id = @execution_id AND pipeline_name = @pipeline_name AND job_name = @job_name
    )
    BEGIN
        UPDATE dbo.etl_ds_job_log
        SET
            status          = @status,
            status_code     = @status_code,
            wave_number     = COALESCE(@wave_number, wave_number),
            pid             = COALESCE(@pid, pid),
            child_jobs      = CASE WHEN @child_jobs     IS NOT NULL AND @child_jobs     <> '' THEN @child_jobs     ELSE child_jobs     END,
            log_summary     = CASE WHEN @log_summary    IS NOT NULL AND @log_summary    <> '' THEN @log_summary    ELSE log_summary    END,
            ds_start_time   = CASE WHEN @ds_start_time  IS NOT NULL                           THEN @ds_start_time  ELSE ds_start_time  END,
            ds_end_time     = CASE WHEN @ds_end_time     IS NOT NULL                           THEN @ds_end_time    ELSE ds_end_time    END,
            poll_snapshots  = CASE
                                WHEN @poll_snapshot IS NOT NULL AND @poll_snapshot <> ''
                                THEN COALESCE(
                                    LEFT(poll_snapshots, LEN(poll_snapshots) - 1) + ',' + @poll_snapshot + ']',
                                    '[' + @poll_snapshot + ']'
                                )
                                ELSE poll_snapshots
                              END,
            last_polled_at  = GETDATE(),
            updated_at      = GETDATE()
        WHERE execution_id = @execution_id AND pipeline_name = @pipeline_name AND job_name = @job_name;
    END
    ELSE
    BEGIN
        INSERT INTO dbo.etl_ds_job_log
            (execution_id, pipeline_name, job_name, project, wave_number, pid,
             status, status_code, child_jobs, log_summary,
             ds_start_time, ds_end_time,
             poll_snapshots, last_polled_at)
        VALUES
            (@execution_id, @pipeline_name, @job_name, @project, @wave_number, @pid,
             @status, @status_code, @child_jobs, @log_summary,
             @ds_start_time, @ds_end_time,
             CASE WHEN @poll_snapshot IS NOT NULL THEN '[' + @poll_snapshot + ']' ELSE NULL END,
             GETDATE());
    END
END
GO

-- Mesmo problema na tabela principal etl_job_execution (usada por todos os
-- job_type, não só DataStage): o upsert via sp_etl_job_execution_log
-- também não considerava pipeline no WHERE.
CREATE OR ALTER PROCEDURE [dbo].[sp_etl_job_execution_log]
(
 @execution_id       VARCHAR(50),
 @project            VARCHAR(100),
 @job_name           VARCHAR(200),
 @pipeline           VARCHAR(200),
 @host               VARCHAR(200),
 @start_time         VARCHAR(30),
 @end_time           VARCHAR(30),
 @duration_seconds   INT,
 @status             VARCHAR(20),
 @log_file           VARCHAR(500),
 @task_id            VARCHAR(200)
)
AS
BEGIN

SET NOCOUNT ON;

DECLARE @start_dt DATETIME2
DECLARE @end_dt   DATETIME2

SET @start_dt =
    CASE
        WHEN @start_time IS NULL OR @start_time = '' THEN NULL
        ELSE CAST(@start_time AS DATETIME2)
    END

SET @end_dt =
    CASE
        WHEN @end_time IS NULL OR @end_time = '' OR @end_time = '1900-01-01 00:00:00'
        THEN NULL
        ELSE CAST(@end_time AS DATETIME2)
    END

IF NOT EXISTS (
    SELECT 1
    FROM dbo.etl_job_execution
    WHERE execution_id = @execution_id
      AND pipeline = @pipeline
      AND job_name = @job_name
      AND task_id = @task_id
)
BEGIN

    INSERT INTO dbo.etl_job_execution
    (
        execution_id,
        project,
        job_name,
        pipeline,
        host,
        start_time,
        end_time,
        duration_seconds,
        status,
        log_file,
        task_id,
        created_at,
        updated_at
    )
    VALUES
    (
        @execution_id,
        @project,
        @job_name,
        @pipeline,
        @host,
        @start_dt,
        @end_dt,
        @duration_seconds,
        @status,
        @log_file,
        @task_id,
        GETDATE(),
        GETDATE()
    )

END
ELSE
BEGIN

    UPDATE dbo.etl_job_execution
    SET
        end_time = COALESCE(@end_dt, end_time),

        duration_seconds =
            CASE
                WHEN @end_dt IS NOT NULL
                THEN DATEDIFF(SECOND, start_time, @end_dt)
                ELSE duration_seconds
            END,

        status = @status,
        log_file = @log_file,
        updated_at = GETDATE()

    WHERE execution_id = @execution_id
      AND pipeline = @pipeline
      AND job_name = @job_name
      AND task_id = @task_id

END

END
GO
