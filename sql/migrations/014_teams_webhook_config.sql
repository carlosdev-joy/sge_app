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

-- 2. Semeia os parâmetros (valor vazio — preencher no Admin)
--    Nomeados por finalidade: cada tipo de notificação pode apontar para um
--    canal/time distinto. Se o webhook específico estiver vazio, a API usa
--    o 'teams_webhook_url' (canal padrão) como fallback.
IF NOT EXISTS (SELECT 1 FROM dbo.etl_app_config WHERE config_key = 'teams_webhook_url')
BEGIN
    INSERT INTO dbo.etl_app_config (config_key, config_value, descricao)
    VALUES ('teams_webhook_url', '',
            'Webhook padrão do Teams (fallback geral da API). Cole a mesma URL da Variable TEAMS_WEBHOOK_URL_CVP do Airflow.');
END
GO

IF NOT EXISTS (SELECT 1 FROM dbo.etl_app_config WHERE config_key = 'teams_webhook_url_ack')
BEGIN
    INSERT INTO dbo.etl_app_config (config_key, config_value, descricao)
    VALUES ('teams_webhook_url_ack', '',
            'Webhook do Teams para notificações de falha assumida (Assumir). Se vazio, usa teams_webhook_url.');
END
GO
