USE [DMDB41]
GO

/****** Object:  StoredProcedure [dbo].[sp_etl_job_execution_log]    Script Date: 30/05/2026 01:00:16 ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE PROCEDURE [dbo].[sp_etl_job_execution_log]
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

------------------------------------------------
-- TRATAMENTO DE DATAS
------------------------------------------------

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

------------------------------------------------
-- INSERT (START) OU UPDATE (END)
------------------------------------------------

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


