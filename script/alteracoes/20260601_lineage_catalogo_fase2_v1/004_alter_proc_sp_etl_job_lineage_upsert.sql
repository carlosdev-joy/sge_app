USE [DMDB41];
GO

/* ORQUESTRA — Lineage Catálogo (Fase 2) v1.0 — ALTER PROC sp_etl_job_lineage_upsert */

CREATE OR ALTER PROCEDURE [dbo].[sp_etl_job_lineage_upsert]
(
    @pipeline_name NVARCHAR(200),
    @job_name      NVARCHAR(200),
    @direction     NVARCHAR(30), -- origem | destino | transformacao
    @object_type   NVARCHAR(20),
    @object_name   NVARCHAR(500),

    @stage_name        VARCHAR(200)   = NULL,
    @stage_type_raw    VARCHAR(100)   = NULL,
    @database_name     VARCHAR(200)   = NULL,
    @sql_expression    NVARCHAR(MAX)  = NULL,
    @file_path         VARCHAR(500)   = NULL,
    @dsx_source_file   VARCHAR(500)   = NULL,
    @extracted_at      DATETIME2      = NULL,
    @extraction_method VARCHAR(20)    = NULL
)
AS
BEGIN
    SET NOCOUNT ON;

    BEGIN TRY
        IF @direction NOT IN ('origem','destino','transformacao')
            RAISERROR ('direction inválido: %s', 16, 1, @direction);

        IF EXISTS (
            SELECT 1
            FROM dbo.etl_job_lineage
            WHERE pipeline_name = @pipeline_name
              AND job_name      = @job_name
              AND direction     = @direction
              AND object_name   = @object_name
        )
        BEGIN
            UPDATE dbo.etl_job_lineage
            SET
                object_type = @object_type,
                stage_name = COALESCE(@stage_name, stage_name),
                stage_type_raw = COALESCE(@stage_type_raw, stage_type_raw),
                database_name = COALESCE(@database_name, database_name),
                sql_expression = COALESCE(@sql_expression, sql_expression),
                file_path = COALESCE(@file_path, file_path),
                dsx_source_file = COALESCE(@dsx_source_file, dsx_source_file),
                extracted_at = COALESCE(@extracted_at, extracted_at),
                extraction_method = COALESCE(@extraction_method, extraction_method),
                updated_at  = SYSDATETIME()
            WHERE pipeline_name = @pipeline_name
              AND job_name      = @job_name
              AND direction     = @direction
              AND object_name   = @object_name;
        END
        ELSE
        BEGIN
            INSERT INTO dbo.etl_job_lineage
            (
                pipeline_name, job_name, direction, object_type, object_name,
                stage_name, stage_type_raw, database_name, sql_expression, file_path,
                dsx_source_file, extracted_at, extraction_method,
                created_at, updated_at
            )
            VALUES
            (
                @pipeline_name, @job_name, @direction, @object_type, @object_name,
                @stage_name, @stage_type_raw, @database_name, @sql_expression, @file_path,
                @dsx_source_file, @extracted_at, @extraction_method,
                SYSDATETIME(), SYSDATETIME()
            );
        END
    END TRY
    BEGIN CATCH
        DECLARE @ErrorMessage  NVARCHAR(4000) = ERROR_MESSAGE();
        DECLARE @ErrorSeverity INT            = ERROR_SEVERITY();
        RAISERROR (@ErrorMessage, @ErrorSeverity, 1);
    END CATCH
END
GO

PRINT 'OK: sp_etl_job_lineage_upsert (Fase 2)';
GO

