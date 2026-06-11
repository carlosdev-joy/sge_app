-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 016 — Tempo de espera em fila do DataStage Workload Manager
--   Adiciona queued_seconds em etl_ds_job_log para medir quanto tempo
--   o job ficou aguardando slot no WM antes de iniciar a execução.
-- ═══════════════════════════════════════════════════════════════════════════

IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_ds_job_log'
      AND COLUMN_NAME='queued_seconds'
)
BEGIN
    ALTER TABLE dbo.etl_ds_job_log ADD queued_seconds INT NULL;
    PRINT '[OK] Coluna queued_seconds adicionada em dbo.etl_ds_job_log';
END
GO
