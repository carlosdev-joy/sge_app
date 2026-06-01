USE [DMDB41];
GO

/* ============================================================
   ORQUESTRA — Schema Lineage v2.0
   ALTER TABLE dbo.etl_job_lineage — 7 colunas de enriquecimento

   Regras:
   - Todas NULL (retrocompatível com registros manuais existentes)
   - Script idempotente (adiciona somente se a coluna não existir)
   ============================================================ */

IF COL_LENGTH('dbo.etl_job_lineage', 'stage_name') IS NULL
    ALTER TABLE [dbo].[etl_job_lineage] ADD [stage_name] VARCHAR(200) NULL;
IF COL_LENGTH('dbo.etl_job_lineage', 'stage_type_raw') IS NULL
    ALTER TABLE [dbo].[etl_job_lineage] ADD [stage_type_raw] VARCHAR(100) NULL;
IF COL_LENGTH('dbo.etl_job_lineage', 'database_name') IS NULL
    ALTER TABLE [dbo].[etl_job_lineage] ADD [database_name] VARCHAR(200) NULL;
IF COL_LENGTH('dbo.etl_job_lineage', 'sql_expression') IS NULL
    ALTER TABLE [dbo].[etl_job_lineage] ADD [sql_expression] NVARCHAR(MAX) NULL;
IF COL_LENGTH('dbo.etl_job_lineage', 'dsx_source_file') IS NULL
    ALTER TABLE [dbo].[etl_job_lineage] ADD [dsx_source_file] VARCHAR(500) NULL;
IF COL_LENGTH('dbo.etl_job_lineage', 'extracted_at') IS NULL
    ALTER TABLE [dbo].[etl_job_lineage] ADD [extracted_at] DATETIME2 NULL;
IF COL_LENGTH('dbo.etl_job_lineage', 'extraction_method') IS NULL
    ALTER TABLE [dbo].[etl_job_lineage] ADD [extraction_method] VARCHAR(20) NULL; -- 'manual' | 'dsx_auto'
GO

PRINT 'OK: Schema Lineage v2 — colunas garantidas em dbo.etl_job_lineage';
GO

