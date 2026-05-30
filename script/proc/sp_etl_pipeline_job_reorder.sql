USE [DMDB41]
GO

/****** Object:  StoredProcedure [dbo].[sp_etl_pipeline_job_reorder] ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

/*
Objetivo:
  Atualizar SOMENTE a ordem de execução (execution_order) de um job,
  sem tocar em lineage e sem exigir origens/destinos.

Uso esperado pela UI:
  - Reordenar jobs em lote (um UPDATE por job)
*/

CREATE OR ALTER PROCEDURE [dbo].[sp_etl_pipeline_job_reorder]
(
    @pipeline_name   NVARCHAR(200),
    @job_name        NVARCHAR(200),
    @execution_order INT
)
AS
BEGIN
    SET NOCOUNT ON;

    BEGIN TRY
        IF NOT EXISTS (
            SELECT 1
            FROM dbo.etl_pipeline_job
            WHERE pipeline_name = @pipeline_name
              AND job_name      = @job_name
        )
        BEGIN
            RAISERROR('Job não encontrado para reorder (pipeline=%s, job=%s)', 16, 1, @pipeline_name, @job_name);
            RETURN;
        END

        UPDATE dbo.etl_pipeline_job
        SET
            execution_order = @execution_order,
            updated_at      = GETDATE()
        WHERE pipeline_name = @pipeline_name
          AND job_name      = @job_name;
    END TRY
    BEGIN CATCH
        DECLARE @ErrorMessage  NVARCHAR(4000) = ERROR_MESSAGE();
        DECLARE @ErrorSeverity INT            = ERROR_SEVERITY();
        RAISERROR (@ErrorMessage, @ErrorSeverity, 1);
    END CATCH
END
GO

