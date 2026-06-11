-- adds ssh_conn_id to etl_pipeline_job + updates upsert SP
ALTER TABLE dbo.etl_pipeline_job
    ADD ssh_conn_id VARCHAR(100) NULL;  -- NULL = use pipeline-level SSH_CONN_ID
GO

CREATE OR ALTER PROCEDURE dbo.sp_etl_pipeline_job_upsert
    @pipeline_name   VARCHAR(200),
    @job_name        VARCHAR(200),
    @execution_order INT,
    @job_type        VARCHAR(50),
    @job_command     NVARCHAR(MAX) = NULL,
    @ssh_conn_id     VARCHAR(100)  = NULL
AS
BEGIN
    SET NOCOUNT ON;
    IF EXISTS (SELECT 1 FROM dbo.etl_pipeline_job WHERE pipeline_name=@pipeline_name AND job_name=@job_name)
        UPDATE dbo.etl_pipeline_job
        SET execution_order=@execution_order, job_type=@job_type,
            job_command=@job_command, ssh_conn_id=@ssh_conn_id, updated_at=GETDATE()
        WHERE pipeline_name=@pipeline_name AND job_name=@job_name;
    ELSE
        INSERT INTO dbo.etl_pipeline_job (pipeline_name, job_name, execution_order, job_type, job_command, ssh_conn_id)
        VALUES (@pipeline_name, @job_name, @execution_order, @job_type, @job_command, @ssh_conn_id);
END
GO
