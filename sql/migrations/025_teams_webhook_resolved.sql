-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 025 — Webhook do Teams para falha resolvida
--   Semeia o parâmetro 'teams_webhook_url_resolved' em dbo.etl_app_config,
--   editável em Admin > Configurações, na mesma linha de
--   'teams_webhook_url_ack' (migration 014). Se vazio, a API usa
--   'teams_webhook_url' (canal padrão) como fallback.
-- Idempotente — seguro para rodar mais de uma vez.
-- ═══════════════════════════════════════════════════════════════════════════

IF NOT EXISTS (SELECT 1 FROM dbo.etl_app_config WHERE config_key = 'teams_webhook_url_resolved')
BEGIN
    INSERT INTO dbo.etl_app_config (config_key, config_value, descricao)
    VALUES ('teams_webhook_url_resolved', '',
            'Webhook do Teams para notificações de falha resolvida (Marcar como Resolvida). Se vazio, usa teams_webhook_url.');
END
GO
