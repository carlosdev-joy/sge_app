-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 024 — Agendamento "Dia + Hora Específico"
--   etl_pipeline:
--     dias_horarios_mes → JSON com até 5 dias do mês (1-28), cada um com até
--                          5 horários "HH:MM" independentes. Usado quando
--                          schedule_type = 'monthly_days_times'.
--                          Ex: [{"dia":1,"horarios":["09:00"]},
--                               {"dia":15,"horarios":["14:00","18:00"]}]
-- Idempotente — seguro para rodar mais de uma vez.
-- ═══════════════════════════════════════════════════════════════════════════

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
               WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_pipeline' AND COLUMN_NAME='dias_horarios_mes')
BEGIN
    ALTER TABLE dbo.etl_pipeline ADD dias_horarios_mes VARCHAR(1000) NULL;
    PRINT '[OK] Coluna dias_horarios_mes adicionada em dbo.etl_pipeline';
END
GO
