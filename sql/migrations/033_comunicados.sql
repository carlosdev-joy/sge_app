-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 033 — Comunicados do admin (broadcast por perfil/usuário)
--   etl_comunicado            → mensagem autorada pelo admin (simples ou banner)
--   etl_comunicado_destinatario → recibo por usuário (entregue/visto/confirmado)
--   para auditoria de comunicação interna.
-- Idempotente — seguro para rodar mais de uma vez.
-- ═══════════════════════════════════════════════════════════════════════════

IF OBJECT_ID('dbo.etl_comunicado', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_comunicado (
        id            BIGINT IDENTITY(1,1) PRIMARY KEY,
        titulo        NVARCHAR(160) NOT NULL,
        mensagem      NVARCHAR(MAX) NOT NULL,
        tipo          NVARCHAR(32)  NOT NULL DEFAULT 'info',     -- info | success | warning | error (cor)
        formato       NVARCHAR(16)  NOT NULL DEFAULT 'simples',  -- simples (sininho/toast) | banner (pop-up)
        link          NVARCHAR(300) NULL,
        imagem_url    NVARCHAR(500) NULL,                        -- reservado para uso futuro (banner com imagem)
        publico_tipo  NVARCHAR(16)  NOT NULL,                    -- todos | perfil | usuarios
        publico_desc  NVARCHAR(300) NULL,                        -- descrição legível do público-alvo
        criado_por    NVARCHAR(64)  NOT NULL,
        criado_em     DATETIME      NOT NULL DEFAULT GETDATE(),
        expira_em     DATETIME      NULL,
        ativo         BIT           NOT NULL DEFAULT 1
    );
    PRINT '[OK] Tabela dbo.etl_comunicado criada';
END
GO

IF OBJECT_ID('dbo.etl_comunicado_destinatario', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_comunicado_destinatario (
        id            BIGINT IDENTITY(1,1) PRIMARY KEY,
        comunicado_id BIGINT       NOT NULL,
        matricula     NVARCHAR(64) NOT NULL,
        entregue_em   DATETIME     NOT NULL DEFAULT GETDATE(),
        visto_em      DATETIME     NULL,   -- apareceu no sininho/toast/banner
        confirmado_em DATETIME     NULL,   -- usuário abriu/confirmou ('Entendi')
        CONSTRAINT FK_cdest_com FOREIGN KEY (comunicado_id)
            REFERENCES dbo.etl_comunicado(id),
        CONSTRAINT UQ_cdest UNIQUE (comunicado_id, matricula)
    );
    CREATE NONCLUSTERED INDEX IX_cdest_user
        ON dbo.etl_comunicado_destinatario (matricula, confirmado_em);
    CREATE NONCLUSTERED INDEX IX_cdest_com
        ON dbo.etl_comunicado_destinatario (comunicado_id);
    PRINT '[OK] Tabela dbo.etl_comunicado_destinatario criada';
END
GO
