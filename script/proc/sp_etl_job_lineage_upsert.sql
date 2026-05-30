USE [DMDB41]
GO

/****** Object:  StoredProcedure [dbo].[sp_etl_job_lineage_upsert]    Script Date: 30/05/2026 00:59:38 ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE PROCEDURE [dbo].[sp_etl_job_lineage_upsert]
(
    @pipeline_name NVARCHAR(200),
    @job_name      NVARCHAR(200),
    @direction     NVARCHAR(10),
    @object_type   NVARCHAR(20),
    @object_name   NVARCHAR(500)
)
AS
BEGIN
    SET NOCOUNT ON;

    BEGIN TRY

        IF EXISTS (
            SELECT 1 FROM dbo.etl_job_lineage
            WHERE pipeline_name = @pipeline_name
              AND job_name      = @job_name
              AND direction     = @direction
              AND object_name   = @object_name
        )
        BEGIN
            UPDATE dbo.etl_job_lineage
            SET
                object_type = @object_type,
                updated_at  = SYSDATETIME()
            WHERE pipeline_name = @pipeline_name
              AND job_name      = @job_name
              AND direction     = @direction
              AND object_name   = @object_name
        END
        ELSE
        BEGIN
            INSERT INTO dbo.etl_job_lineage
                (pipeline_name, job_name, direction, object_type, object_name, created_at, updated_at)
            VALUES
                (@pipeline_name, @job_name, @direction, @object_type, @object_name, SYSDATETIME(), SYSDATETIME())
        END

    END TRY
    BEGIN CATCH
        DECLARE @ErrorMessage  NVARCHAR(4000) = ERROR_MESSAGE();
        DECLARE @ErrorSeverity INT            = ERROR_SEVERITY();
        RAISERROR (@ErrorMessage, @ErrorSeverity, 1);
    END CATCH
END
GO


