-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 061 — Caixa Seguro (Fase 4): assistentes IA
--
--   etl_caixa_chat_log → registro das conversas com os assistentes
--                        (Diego/Lari/Léo). Substitui a tabela
--                        leo_conversations do Supabase da POC Lovable.
--
-- A configuração dos assistentes (ligado/desligado, provedor, modelo, chave)
-- vive em dbo.etl_app_config sob as chaves caixa_ia_* — gerida pela action
-- caixa_ia_set do admin; a chave de API é cifrada com Fernet
-- (ORQUESTRA_CONN_KEY, mesmo mecanismo de dbo.etl_conexao).
--
-- Idempotente — seguro para rodar mais de uma vez.
-- ═══════════════════════════════════════════════════════════════════════════

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
               WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_caixa_chat_log')
BEGIN
    CREATE TABLE dbo.etl_caixa_chat_log (
        id          INT IDENTITY(1,1) NOT NULL,
        assistente  VARCHAR(10)    NOT NULL,   -- diego | lari | leo
        matricula   VARCHAR(20)    NOT NULL,
        mensagem    NVARCHAR(MAX)  NOT NULL,
        resposta    NVARCHAR(MAX)  NULL,
        contexto    NVARCHAR(MAX)  NULL,       -- JSON do contexto da página
        modelo      VARCHAR(100)   NULL,
        duracao_ms  INT            NULL,
        status      VARCHAR(20)    NOT NULL DEFAULT 'ok',  -- ok | erro
        erro        NVARCHAR(1000) NULL,
        criado_em   DATETIME       NOT NULL DEFAULT GETDATE(),
        CONSTRAINT PK_etl_caixa_chat_log PRIMARY KEY (id)
    );
    CREATE NONCLUSTERED INDEX IX_caixa_chat_matricula
        ON dbo.etl_caixa_chat_log (matricula, criado_em DESC);
    CREATE NONCLUSTERED INDEX IX_caixa_chat_assistente
        ON dbo.etl_caixa_chat_log (assistente, criado_em DESC);
    PRINT '[OK] Tabela etl_caixa_chat_log criada';
END
GO
