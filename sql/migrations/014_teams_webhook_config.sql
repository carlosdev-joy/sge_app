-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 014 — Webhook do Teams configurável pelo Admin
--   A API (assumir falha) passa a ler a URL do webhook de dbo.etl_app_config
--   (chave 'teams_webhook_url'), editável em Admin > Configurações,
--   sem depender de Airflow Variable.
-- ═══════════════════════════════════════════════════════════════════════════

-- 1. URLs do Power Automate podem passar de 500 chars — alarga a coluna.
IF EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
           WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_app_config'
             AND COLUMN_NAME='config_value' AND CHARACTER_MAXIMUM_LENGTH < 1000)
BEGIN
    ALTER TABLE dbo.etl_app_config ALTER COLUMN config_value VARCHAR(1000) NOT NULL;
END
GO

-- 2. Semeia o parâmetro (valor vazio — preencher no Admin)
IF NOT EXISTS (SELECT 1 FROM dbo.etl_app_config WHERE config_key = 'teams_webhook_url')
BEGIN
    INSERT INTO dbo.etl_app_config (config_key, config_value, descricao)
    VALUES ('teams_webhook_url', '',
            'URL do webhook do Teams usada pela API (assumir falha). Cole aqui a mesma URL da Variable TEAMS_WEBHOOK_URL_CVP do Airflow.');
END
GO
