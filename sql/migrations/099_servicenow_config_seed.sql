-- sql/migrations/099_servicenow_config_seed.sql
-- Seed das configurações de integração ServiceNow na tabela etl_app_config.
-- Execute APÓS as migrations 089–098 (tabela já existente).
-- A senha NÃO está aqui — configure via tela Admin > ServiceNow após o deploy.
--
-- Chaves gerenciadas:
--   servicenow_url       → URL base da instância (ex: https://cvpsnprod.service-now.com)
--   servicenow_usuario   → Conta de serviço com role itil / power_bi
--   servicenow_senha_enc → Senha cifrada via Fernet (configurar pelo Admin)
--   servicenow_habilitado→ "1" = sync ativo | "0" = sync pausado
--   servicenow_proxy     → Proxy corporativo para acesso externo (vazio = direto)
--   servicenow_grupos    → Nome do grupo de atribuição no ServiceNow a monitorar
-- ─────────────────────────────────────────────────────────────────────────────

MERGE dbo.etl_app_config AS t
USING (VALUES
    ('servicenow_url',       'https://cvpsnprod.service-now.com'),
    ('servicenow_usuario',   'user.power_bi'),
    ('servicenow_senha_enc', ''),
    ('servicenow_habilitado','0'),
    ('servicenow_proxy',     'http://webproxycvp.adcorp.intranet/'),
    ('servicenow_grupos',    'TI_CVP_GERESD_ED')
) AS s (config_key, config_value)
ON t.config_key = s.config_key
WHEN NOT MATCHED THEN
    INSERT (config_key, config_value) VALUES (s.config_key, s.config_value);
-- WHEN MATCHED: não sobrescreve — preserva configuração já existente em produção.
GO
