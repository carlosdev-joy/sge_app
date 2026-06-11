-- Migration 010: tabela de log detalhado DataStage
-- Persiste wave_number, jobs filhos e logsum do DataStageOperator

CREATE TABLE dbo.etl_ds_job_log (
    id               INT IDENTITY(1,1) PRIMARY KEY,
    execution_id     VARCHAR(50)       NOT NULL,
    pipeline_name    VARCHAR(200)      NOT NULL,
    job_name         VARCHAR(200)      NOT NULL,
    project          VARCHAR(100)      NOT NULL,
    wave_number      INT               NULL,
    pid              VARCHAR(20)       NULL,
    status           VARCHAR(50)       NOT NULL,
    status_code      INT               NULL,
    child_jobs       NVARCHAR(MAX)     NULL,  -- JSON: [{name, status, status_code}]
    log_summary      NVARCHAR(MAX)     NULL,
    poll_snapshots   NVARCHAR(MAX)     NULL,  -- JSON: [{ts, status, status_code}]
    last_polled_at   DATETIME          NULL,
    created_at       DATETIME          NOT NULL DEFAULT GETDATE(),
    updated_at       DATETIME          NOT NULL DEFAULT GETDATE()
);

CREATE INDEX ix_ds_job_log_exec  ON dbo.etl_ds_job_log (execution_id);
CREATE INDEX ix_ds_job_log_job   ON dbo.etl_ds_job_log (job_name, created_at DESC);

GO

-- Upsert usado pelo DataStageOperator e monitor DAG
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
    @poll_snapshot  NVARCHAR(MAX)   -- JSON de um snapshot a anexar
AS
BEGIN
    SET NOCOUNT ON;

    IF EXISTS (
        SELECT 1 FROM dbo.etl_ds_job_log
        WHERE execution_id = @execution_id AND job_name = @job_name
    )
    BEGIN
        UPDATE dbo.etl_ds_job_log
        SET
            status          = @status,
            status_code     = @status_code,
            wave_number     = COALESCE(@wave_number, wave_number),
            pid             = COALESCE(@pid, pid),
            child_jobs      = CASE WHEN @child_jobs IS NOT NULL AND @child_jobs <> '' THEN @child_jobs ELSE child_jobs END,
            log_summary     = CASE WHEN @log_summary IS NOT NULL AND @log_summary <> '' THEN @log_summary ELSE log_summary END,
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
        WHERE execution_id = @execution_id AND job_name = @job_name;
    END
    ELSE
    BEGIN
        INSERT INTO dbo.etl_ds_job_log
            (execution_id, pipeline_name, job_name, project, wave_number, pid,
             status, status_code, child_jobs, log_summary, poll_snapshots, last_polled_at)
        VALUES
            (@execution_id, @pipeline_name, @job_name, @project, @wave_number, @pid,
             @status, @status_code, @child_jobs, @log_summary,
             CASE WHEN @poll_snapshot IS NOT NULL THEN '[' + @poll_snapshot + ']' ELSE NULL END,
             GETDATE());
    END
END
GO
