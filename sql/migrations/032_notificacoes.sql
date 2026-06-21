-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 032 — Notificações por usuário (central no header)
--   etl_notificacao guarda ações relevantes por usuário (DAG gerada/ativa,
--   pipeline inativado/ativado, falha assumida/resolvida…), exibidas no sininho
--   do header com toast para as novas. lida=0 → não-lida.
-- Idempotente — seguro para rodar mais de uma vez.
-- ═══════════════════════════════════════════════════════════════════════════

IF OBJECT_ID('dbo.etl_notificacao', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_notificacao (
        id          BIGINT IDENTITY(1,1) PRIMARY KEY,
        matricula   NVARCHAR(64)  NOT NULL,
        tipo        NVARCHAR(32)  NOT NULL DEFAULT 'info',   -- info | success | warning | error
        titulo      NVARCHAR(160) NOT NULL,
        mensagem    NVARCHAR(800) NULL,
        link        NVARCHAR(300) NULL,
        lida        BIT           NOT NULL DEFAULT 0,
        created_at  DATETIME      NOT NULL DEFAULT GETDATE()
    );
    CREATE NONCLUSTERED INDEX IX_etl_notificacao_user
        ON dbo.etl_notificacao (matricula, created_at DESC);
    CREATE NONCLUSTERED INDEX IX_etl_notificacao_unread
        ON dbo.etl_notificacao (matricula, lida);
    PRINT '[OK] Tabela dbo.etl_notificacao criada';
END
GO
