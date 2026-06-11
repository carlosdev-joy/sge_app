-- Migration 011: adiciona ds_start_time e ds_end_time em etl_ds_job_log
-- Permite exibir horário real de início/fim do job DataStage no DS Log modal

ALTER TABLE dbo.etl_ds_job_log
    ADD ds_start_time VARCHAR(50) NULL,   -- "Job Start Time" do dsjob -jobinfo
        ds_end_time   DATETIME    NULL;   -- momento em que _finish() detectou conclusão

GO

-- Atualiza SP para aceitar e persistir os novos campos
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
        WHERE execution_id = @execution_id AND job_name = @job_name
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
        WHERE execution_id = @execution_id AND job_name = @job_name;
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
