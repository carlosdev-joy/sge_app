-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 031 — Motivo de inativação do pipeline
--   etl_pipeline ganha 3 colunas para registrar POR QUE um fluxo foi inativado,
--   facilitando o diagnóstico quando o fluxo "não está disponível para execução":
--     motivo_inativacao → texto obrigatório informado ao inativar (na UI)
--     inativado_por     → matrícula de quem inativou
--     inativado_em      → data/hora da inativação
--   Ao reativar o pipeline, a aplicação limpa esses três campos.
-- Idempotente — seguro para rodar mais de uma vez.
-- ═══════════════════════════════════════════════════════════════════════════

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
               WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_pipeline' AND COLUMN_NAME='motivo_inativacao')
BEGIN
    ALTER TABLE dbo.etl_pipeline ADD motivo_inativacao NVARCHAR(500) NULL;
    PRINT '[OK] Coluna motivo_inativacao adicionada em dbo.etl_pipeline';
END
GO

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
               WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_pipeline' AND COLUMN_NAME='inativado_por')
BEGIN
    ALTER TABLE dbo.etl_pipeline ADD inativado_por NVARCHAR(64) NULL;
    PRINT '[OK] Coluna inativado_por adicionada em dbo.etl_pipeline';
END
GO

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
               WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_pipeline' AND COLUMN_NAME='inativado_em')
BEGIN
    ALTER TABLE dbo.etl_pipeline ADD inativado_em DATETIME NULL;
    PRINT '[OK] Coluna inativado_em adicionada em dbo.etl_pipeline';
END
GO
