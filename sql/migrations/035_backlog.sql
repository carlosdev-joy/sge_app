-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 035 — Backlog do produto (gestão no Admin)
--   etl_backlog guarda itens de backlog (feature/bug/debt/spike) com prioridade,
--   área, status e responsável — geridos pela aba Backlog do Admin e pela skill
--   /backlog. Backend e UI degradam graciosamente se a tabela não existir.
-- Idempotente — seguro para rodar mais de uma vez.
-- ═══════════════════════════════════════════════════════════════════════════

IF OBJECT_ID('dbo.etl_backlog', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_backlog (
        id            BIGINT IDENTITY(1,1) PRIMARY KEY,
        titulo        NVARCHAR(200) NOT NULL,
        descricao     NVARCHAR(MAX) NULL,
        tipo          NVARCHAR(16)  NOT NULL DEFAULT 'feature',  -- feature|bug|debt|spike
        area          NVARCHAR(24)  NULL,                        -- backend|frontend|datastage|deploy|infra|outro
        prioridade    NVARCHAR(4)   NOT NULL DEFAULT 'P2',       -- P0..P3
        status        NVARCHAR(16)  NOT NULL DEFAULT 'ideia',    -- ideia|refinado|em_andamento|concluido|descartado
        estimativa    NVARCHAR(16)  NULL,
        responsavel   NVARCHAR(64)  NULL,
        ref_pr        NVARCHAR(60)  NULL,
        tags          NVARCHAR(200) NULL,
        criado_por    NVARCHAR(64)  NULL,
        criado_em     DATETIME      NOT NULL DEFAULT GETDATE(),
        atualizado_em DATETIME      NULL,
        concluido_em  DATETIME      NULL
    );
    CREATE NONCLUSTERED INDEX IX_etl_backlog_status
        ON dbo.etl_backlog (status, prioridade, criado_em DESC);
    PRINT '[OK] Tabela dbo.etl_backlog criada';
END
GO
