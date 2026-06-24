-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 048 — Posição dos nós no editor de fluxo (canvas)
--   etl_pipeline_job.layout_x / layout_y: coordenadas (x, y) do nó no editor
--   interativo de fluxo de etapas. São COSMÉTICAS — o factory as ignora; só
--   servem para reabrir o canvas com os nós onde o usuário deixou.
--   Vazio (NULL) = sem posição salva (auto-layout no front).
-- Idempotente.
-- ═══════════════════════════════════════════════════════════════════════════

IF COL_LENGTH('dbo.etl_pipeline_job', 'layout_x') IS NULL
BEGIN
    ALTER TABLE dbo.etl_pipeline_job ADD layout_x FLOAT NULL;
    PRINT '[OK] etl_pipeline_job.layout_x adicionada';
END
GO

IF COL_LENGTH('dbo.etl_pipeline_job', 'layout_y') IS NULL
BEGIN
    ALTER TABLE dbo.etl_pipeline_job ADD layout_y FLOAT NULL;
    PRINT '[OK] etl_pipeline_job.layout_y adicionada';
END
GO
