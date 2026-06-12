-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 018 — Horários múltiplos por pipeline
--   etl_pipeline:
--     horarios_especificos → lista CSV de horários "HH:MM,HH:MM,..." em que o
--                            pipeline roda (ex: "09:00,10:30,13:00"). Quando
--                            preenchido, substitui o horário único.
--     dias_semana          → dias da semana em formato cron ("1-5" = seg-sex,
--                            "1,3,5" = seg/qua/sex). NULL = todos os dias.
-- Idempotente — seguro para rodar mais de uma vez.
-- ═══════════════════════════════════════════════════════════════════════════

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
               WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_pipeline' AND COLUMN_NAME='horarios_especificos')
BEGIN
    ALTER TABLE dbo.etl_pipeline ADD horarios_especificos VARCHAR(500) NULL;
    PRINT '[OK] Coluna horarios_especificos adicionada em dbo.etl_pipeline';
END
GO

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
               WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_pipeline' AND COLUMN_NAME='dias_semana')
BEGIN
    ALTER TABLE dbo.etl_pipeline ADD dias_semana VARCHAR(30) NULL;
    PRINT '[OK] Coluna dias_semana adicionada em dbo.etl_pipeline';
END
GO
