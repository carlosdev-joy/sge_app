USE [DMDB41];
GO

/* ============================================================
   ORQUESTRA — Schema Lineage v2.0
   ALTER PROC dbo.sp_etl_job_lineage_upsert — 7 parâmetros opcionais

   Regras:
   - Compatível com chamadas antigas (somente 5 parâmetros originais)
   - Em UPDATE usa COALESCE para NÃO sobrescrever valores existentes com NULL
   ============================================================ */

CREATE OR ALTER PROCEDURE [dbo].[sp_etl_job_lineage_upsert]
(
    @pipeline_name NVARCHAR(200),
    @job_name NVARCHAR(200),
    @direction NVARCHAR(10),
    @object_type NVARCHAR(20),
    @object_name NVARCHAR(500),

    -- Campos novos opcionais (default NULL para manter compatibilidade)
    @stage_name VARCHAR(200) = NULL,
    @stage_type_raw VARCHAR(100) = NULL,
    @database_name VARCHAR(200) = NULL,
    @sql_expression NVARCHAR(MAX) = NULL,
    @dsx_source_file VARCHAR(500) = NULL,
    @extracted_at DATETIME2 = NULL,
    @extraction_method VARCHAR(20) = NULL
)
AS
BEGIN
    SET NOCOUNT ON;

    BEGIN TRY

        IF EXISTS (
            SELECT 1
            FROM dbo.etl_job_lineage
            WHERE pipeline_name = @pipeline_name
              AND job_name = @job_name
              AND direction = @direction
              AND object_name = @object_name
        )
        BEGIN
            UPDATE dbo.etl_job_lineage
            SET
                object_type = @object_type,
                stage_name = COALESCE(@stage_name, stage_name),
                stage_type_raw = COALESCE(@stage_type_raw, stage_type_raw),
                database_name = COALESCE(@database_name, database_name),
                sql_expression = COALESCE(@sql_expression, sql_expression),
                dsx_source_file = COALESCE(@dsx_source_file, dsx_source_file),
                extracted_at = COALESCE(@extracted_at, extracted_at),
                extraction_method = COALESCE(@extraction_method, extraction_method),
                updated_at = SYSDATETIME()
            WHERE pipeline_name = @pipeline_name
              AND job_name = @job_name
              AND direction = @direction
              AND object_name = @object_name
        END
        ELSE
        BEGIN
            INSERT INTO dbo.etl_job_lineage
            (
                pipeline_name, job_name, direction, object_type, object_name,
                stage_name, stage_type_raw, database_name, sql_expression, dsx_source_file, extracted_at, extraction_method,
                created_at, updated_at
            )
            VALUES
            (
                @pipeline_name, @job_name, @direction, @object_type, @object_name,
                @stage_name, @stage_type_raw, @database_name, @sql_expression, @dsx_source_file, @extracted_at, @extraction_method,
                SYSDATETIME(), SYSDATETIME()
            )
        END

    END TRY
    BEGIN CATCH
        DECLARE @Msg NVARCHAR(4000) = ERROR_MESSAGE();
        DECLARE @Sev INT = ERROR_SEVERITY();
        RAISERROR (@Msg, @Sev, 1);
    END CATCH
END
GO

PRINT 'OK: sp_etl_job_lineage_upsert atualizada (Schema Lineage v2)';
GO

