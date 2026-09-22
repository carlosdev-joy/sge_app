-- sql/migrations/116_ia_provedor_config.sql
-- F0 da spec docs/spec-agentes-datastage.md: desacopla a config do provedor de
-- IA do módulo Caixa Seguro (o módulo vai sair do Orquestra em breve; a IA
-- fica e passa a servir Maestro, triagem, agentes e o que vier depois).
--
-- COPIA (não move, não apaga) 5 das 6 chaves compartilhadas de config_key
-- 'caixa_ia_*' para 'ia_*' — provider, model, base_url, api_key_enc,
-- usa_proxy. `ultima_verificacao` fica de fora de propósito (ver o
-- comentário antes do INSERT dela, mais abaixo): copiá-la faria a tela nova
-- mostrar "conectado" sobre uma verificação que nunca rodou com a config
-- `ia_*`. `caixa_ia_enabled` também NÃO entra: é o interruptor PRÓPRIO dos
-- assistentes do Caixa Seguro (routers/caixa_chat.py), não do provedor
-- compartilhado, e fica com o módulo Caixa quando ele sair.
--
-- Idempotente (roda 2×): só INSERE onde a chave nova ainda não existe, e só
-- quando a antiga tem valor. `api/services/ia_provedor.load_config()` lê a
-- nova com fallback para a antiga, então a ordem desta migration em relação
-- ao deploy de dags/+worker não quebra nada (ver risco 18 da spec).
-- Aplicada pela etapa 6c do deploy.sh.

IF EXISTS (SELECT 1 FROM dbo.etl_app_config WHERE config_key = 'caixa_ia_provider')
   AND NOT EXISTS (SELECT 1 FROM dbo.etl_app_config WHERE config_key = 'ia_provider')
BEGIN
    INSERT INTO dbo.etl_app_config (config_key, config_value, descricao, updated_by, updated_at)
    SELECT 'ia_provider', config_value, 'Provedor de IA compartilhado (F0) — copiado de caixa_ia_provider', 'migration_116', GETDATE()
    FROM dbo.etl_app_config WHERE config_key = 'caixa_ia_provider';
    PRINT '[OK] ia_provider copiado de caixa_ia_provider';
END
ELSE
    PRINT '[SKIP] ia_provider ja existe ou caixa_ia_provider nao existe';
GO

IF EXISTS (SELECT 1 FROM dbo.etl_app_config WHERE config_key = 'caixa_ia_model')
   AND NOT EXISTS (SELECT 1 FROM dbo.etl_app_config WHERE config_key = 'ia_model')
BEGIN
    INSERT INTO dbo.etl_app_config (config_key, config_value, descricao, updated_by, updated_at)
    SELECT 'ia_model', config_value, 'Provedor de IA compartilhado (F0) — copiado de caixa_ia_model', 'migration_116', GETDATE()
    FROM dbo.etl_app_config WHERE config_key = 'caixa_ia_model';
    PRINT '[OK] ia_model copiado de caixa_ia_model';
END
ELSE
    PRINT '[SKIP] ia_model ja existe ou caixa_ia_model nao existe';
GO

IF EXISTS (SELECT 1 FROM dbo.etl_app_config WHERE config_key = 'caixa_ia_base_url')
   AND NOT EXISTS (SELECT 1 FROM dbo.etl_app_config WHERE config_key = 'ia_base_url')
BEGIN
    INSERT INTO dbo.etl_app_config (config_key, config_value, descricao, updated_by, updated_at)
    SELECT 'ia_base_url', config_value, 'Provedor de IA compartilhado (F0) — copiado de caixa_ia_base_url', 'migration_116', GETDATE()
    FROM dbo.etl_app_config WHERE config_key = 'caixa_ia_base_url';
    PRINT '[OK] ia_base_url copiado de caixa_ia_base_url';
END
ELSE
    PRINT '[SKIP] ia_base_url ja existe ou caixa_ia_base_url nao existe';
GO

IF EXISTS (SELECT 1 FROM dbo.etl_app_config WHERE config_key = 'caixa_ia_api_key_enc')
   AND NOT EXISTS (SELECT 1 FROM dbo.etl_app_config WHERE config_key = 'ia_api_key_enc')
BEGIN
    -- A chave já vem CIFRADA (Fernet, ORQUESTRA_CONN_KEY) em caixa_ia_api_key_enc;
    -- copiar o texto cifrado não expõe nada em claro nem exige decifrar/recifrar.
    INSERT INTO dbo.etl_app_config (config_key, config_value, descricao, updated_by, updated_at)
    SELECT 'ia_api_key_enc', config_value, 'Provedor de IA compartilhado (F0) — copiado de caixa_ia_api_key_enc', 'migration_116', GETDATE()
    FROM dbo.etl_app_config WHERE config_key = 'caixa_ia_api_key_enc';
    PRINT '[OK] ia_api_key_enc copiado de caixa_ia_api_key_enc';
END
ELSE
    PRINT '[SKIP] ia_api_key_enc ja existe ou caixa_ia_api_key_enc nao existe';
GO

IF EXISTS (SELECT 1 FROM dbo.etl_app_config WHERE config_key = 'caixa_ia_usa_proxy')
   AND NOT EXISTS (SELECT 1 FROM dbo.etl_app_config WHERE config_key = 'ia_usa_proxy')
BEGIN
    INSERT INTO dbo.etl_app_config (config_key, config_value, descricao, updated_by, updated_at)
    SELECT 'ia_usa_proxy', config_value, 'Provedor de IA compartilhado (F0) — copiado de caixa_ia_usa_proxy', 'migration_116', GETDATE()
    FROM dbo.etl_app_config WHERE config_key = 'caixa_ia_usa_proxy';
    PRINT '[OK] ia_usa_proxy copiado de caixa_ia_usa_proxy';
END
ELSE
    PRINT '[SKIP] ia_usa_proxy ja existe ou caixa_ia_usa_proxy nao existe';
GO

-- ultima_verificacao NÃO é copiada de propósito: é o laudo de uma verificação
-- feita sob o nome antigo — copiá-lo faria a tela nova mostrar "conectado"
-- sobre uma checagem que nunca rodou com a config `ia_*`. Fica em branco até
-- alguém clicar em "Verificar" em Admin › IA (mesmo comportamento de uma
-- instalação nova, já tratado por load_config/ia_get).

PRINT '[OK] migration 116 concluida — caixa_ia_enabled NAO migra (fica com o modulo Caixa)';
GO
