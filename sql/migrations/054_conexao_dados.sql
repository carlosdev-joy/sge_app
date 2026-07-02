-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 054 — Conexões de Dados nativas do Orquestra
--   etl_conexao — cadastro das conexões MSSQL usadas pela Cópia de Dados e
--                 pelos nós SQL, com a senha CIFRADA (Fernet — chave em
--                 ORQUESTRA_CONN_KEY, a mesma no orquestra-api e nos
--                 containers do Airflow). Substitui as Airflow Connections
--                 como fonte da verdade; as DAGs resolvem aqui PRIMEIRO e
--                 caem para BaseHook (Airflow) só na transição.
--   origem      — 'orquestra' (criada na UI) | 'migrada_airflow' (importada
--                 pela action conn_migrate da DAG etl_admin_manage).
-- Idempotente — seguro para rodar mais de uma vez.
-- ═══════════════════════════════════════════════════════════════════════════

IF OBJECT_ID('dbo.etl_conexao', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_conexao (
        id             INT IDENTITY(1,1) PRIMARY KEY,
        conn_id        VARCHAR(100)  NOT NULL,
        conn_type      VARCHAR(20)   NOT NULL DEFAULT 'mssql',
        host           NVARCHAR(255) NOT NULL,
        port           INT           NULL,          -- NULL = 1433 (padrão MSSQL)
        login          NVARCHAR(128) NOT NULL,
        senha_enc      VARCHAR(2000) NOT NULL,      -- token Fernet (base64) — NUNCA texto puro
        descricao      NVARCHAR(400) NULL,
        extra_json     NVARCHAR(MAX) NULL,          -- {"charset": "CP1252", ...}
        origem         VARCHAR(20)   NOT NULL DEFAULT 'orquestra',
        criado_por     NVARCHAR(64)  NULL,
        criado_em      DATETIME      NOT NULL DEFAULT GETDATE(),
        atualizado_por NVARCHAR(64)  NULL,
        atualizado_em  DATETIME      NULL
    );
    CREATE UNIQUE NONCLUSTERED INDEX UX_etl_conexao_conn_id
        ON dbo.etl_conexao (conn_id);
    PRINT '[OK] Tabela dbo.etl_conexao criada';
END
ELSE
    PRINT '[SKIP] Tabela dbo.etl_conexao ja existe';
GO
