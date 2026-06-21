-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 037 — Liga o run da factory ao pendente de ativação
--   Adiciona dag_run_id em etl_dag_pendente para o reconciliador atualizar o
--   estado do registro correto em etl_factory_log (GERADA → SUCCESS/TIMEOUT).
-- Idempotente.
-- ═══════════════════════════════════════════════════════════════════════════

IF COL_LENGTH('dbo.etl_dag_pendente', 'dag_run_id') IS NULL
BEGIN
    ALTER TABLE dbo.etl_dag_pendente ADD dag_run_id NVARCHAR(200) NULL;
    PRINT '[OK] etl_dag_pendente.dag_run_id adicionada';
END
GO
