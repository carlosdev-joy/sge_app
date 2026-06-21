-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 038 — Dependência por job (grafo) dentro do pipeline
--   etl_pipeline_job.depends_on_jobs: lista (CSV) de jobs do MESMO pipeline que
--   precisam terminar com sucesso antes deste começar. Vazio = job raiz.
--   Opt-in: se nenhum job tem depends_on_jobs, o factory usa o modo de ondas
--   (execution_order) como hoje.
-- Idempotente.
-- ═══════════════════════════════════════════════════════════════════════════

IF COL_LENGTH('dbo.etl_pipeline_job', 'depends_on_jobs') IS NULL
BEGIN
    ALTER TABLE dbo.etl_pipeline_job ADD depends_on_jobs NVARCHAR(MAX) NULL;
    PRINT '[OK] etl_pipeline_job.depends_on_jobs adicionada';
END
GO
