-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 039 — Banco-alvo por job storedproc (mesmo servidor)
--   etl_pipeline_job.mssql_database: banco em que a proc deve rodar (no MESMO
--   servidor da conexão do ORQUESTRA). Vazio = banco padrão da conexão.
--   O operador executa EXEC [banco].schema.proc (nome de 3 partes).
-- Idempotente.
-- ═══════════════════════════════════════════════════════════════════════════

IF COL_LENGTH('dbo.etl_pipeline_job', 'mssql_database') IS NULL
BEGIN
    ALTER TABLE dbo.etl_pipeline_job ADD mssql_database NVARCHAR(128) NULL;
    PRINT '[OK] etl_pipeline_job.mssql_database adicionada';
END
GO
