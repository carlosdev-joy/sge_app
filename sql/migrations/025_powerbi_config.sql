-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 025 — Parâmetros de conexão do Power BI (Admin > Configurações)
--   A API (api/services/powerbi_client.py) lê tenant_id, client_id,
--   client_secret, scope e token_url de dbo.etl_app_config — sem credenciais
--   em código nem em variável de ambiente. powerbi_client_secret é tratado
--   como sensível (não aparece em GET /config, só editável via Admin).
-- ═══════════════════════════════════════════════════════════════════════════

IF NOT EXISTS (SELECT 1 FROM dbo.etl_app_config WHERE config_key = 'powerbi_tenant_id')
BEGIN
    INSERT INTO dbo.etl_app_config (config_key, config_value, descricao)
    VALUES ('powerbi_tenant_id', '',
            'Directory (tenant) ID do Azure AD usado pelo service principal do Power BI.');
END
GO

IF NOT EXISTS (SELECT 1 FROM dbo.etl_app_config WHERE config_key = 'powerbi_client_id')
BEGIN
    INSERT INTO dbo.etl_app_config (config_key, config_value, descricao)
    VALUES ('powerbi_client_id', '',
            'Application (client) ID do app registration / service principal do Power BI.');
END
GO

IF NOT EXISTS (SELECT 1 FROM dbo.etl_app_config WHERE config_key = 'powerbi_client_secret')
BEGIN
    INSERT INTO dbo.etl_app_config (config_key, config_value, descricao)
    VALUES ('powerbi_client_secret', '',
            'Client secret do app registration do Power BI. Sensível — não exposto em GET /config.');
END
GO

IF NOT EXISTS (SELECT 1 FROM dbo.etl_app_config WHERE config_key = 'powerbi_scope')
BEGIN
    INSERT INTO dbo.etl_app_config (config_key, config_value, descricao)
    VALUES ('powerbi_scope', '',
            'Scope OAuth do Power BI. Opcional — se vazio, usa o default '
            '"https://analysis.windows.net/powerbi/api/.default".');
END
GO

IF NOT EXISTS (SELECT 1 FROM dbo.etl_app_config WHERE config_key = 'powerbi_token_url')
BEGIN
    INSERT INTO dbo.etl_app_config (config_key, config_value, descricao)
    VALUES ('powerbi_token_url', '',
            'URL do endpoint de token OAuth. Opcional — se vazio, é derivada de '
            'powerbi_tenant_id (https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token).');
END
GO
