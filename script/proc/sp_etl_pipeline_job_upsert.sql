USE [DMDB41]
GO

/****** Object:  StoredProcedure [dbo].[sp_etl_pipeline_job_upsert]    Script Date: 30/05/2026 00:59:02 ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE PROCEDURE [dbo].[sp_etl_pipeline_job_upsert]
(
    @pipeline_name   NVARCHAR(200),
    @job_name        NVARCHAR(200),
    @execution_order INT,
    @job_type        NVARCHAR(20),
    @job_command     NVARCHAR(500) = NULL
)
AS
BEGIN
    SET NOCOUNT ON;

    BEGIN TRY
        IF EXISTS (
            SELECT 1 FROM dbo.etl_pipeline_job
            WHERE pipeline_name = @pipeline_name AND job_name = @job_name
        )
        BEGIN
            UPDATE dbo.etl_pipeline_job
            SET
                execution_order = @execution_order,
                job_type        = @job_type,
                job_command     = @job_command,
                updated_at      = GETDATE()
            WHERE pipeline_name = @pipeline_name AND job_name = @job_name
        END
        ELSE
        BEGIN
            INSERT INTO dbo.etl_pipeline_job (
                pipeline_name, job_name, execution_order,
                job_type, job_command, created_at
            )
            VALUES (
                @pipeline_name, @job_name, @execution_order,
                @job_type, @job_command, GETDATE()
            )
        END
    END TRY
    BEGIN CATCH
        DECLARE @ErrorMessage NVARCHAR(4000) = ERROR_MESSAGE();
        DECLARE @ErrorSeverity INT           = ERROR_SEVERITY();
        RAISERROR (@ErrorMessage, @ErrorSeverity, 1);
    END CATCH
END
GO


