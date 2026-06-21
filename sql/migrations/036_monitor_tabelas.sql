-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 036 — Monitoramento de tabelas (observabilidade de dados)
--   etl_monitor_tabela     → registro das tabelas importantes a monitorar
--                            (database.schema.tabela + coluna de competência).
--   etl_monitor_snapshot   → capturas periódicas (total, última data, qtde/dia)
--                            para frescor, tendência e alerta de anomalia.
-- Idempotente — seguro para rodar mais de uma vez.
-- ═══════════════════════════════════════════════════════════════════════════

IF OBJECT_ID('dbo.etl_monitor_tabela', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_monitor_tabela (
        id                 BIGINT IDENTITY(1,1) PRIMARY KEY,
        database_name      NVARCHAR(128) NOT NULL,
        schema_name        NVARCHAR(128) NOT NULL DEFAULT 'dbo',
        table_name         NVARCHAR(128) NOT NULL,
        coluna_data        NVARCHAR(128) NOT NULL,        -- competência/carga (conta por dia)
        coluna_atualizacao NVARCHAR(128) NULL,            -- updated_at, se existir
        criticidade        NVARCHAR(8)   NULL,            -- Alta|Media|Baixa
        sla_horas          INT           NULL,            -- frescor esperado (h); NULL = sem SLA
        ativo              BIT           NOT NULL DEFAULT 1,
        descricao          NVARCHAR(300) NULL,
        criado_por         NVARCHAR(64)  NULL,
        criado_em          DATETIME      NOT NULL DEFAULT GETDATE(),
        atualizado_em      DATETIME      NULL,
        CONSTRAINT UQ_monitor_tabela UNIQUE (database_name, schema_name, table_name)
    );
    PRINT '[OK] Tabela dbo.etl_monitor_tabela criada';
END
GO

IF OBJECT_ID('dbo.etl_monitor_snapshot', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_monitor_snapshot (
        id              BIGINT IDENTITY(1,1) PRIMARY KEY,
        tabela_id       BIGINT   NOT NULL,
        captured_at     DATETIME NOT NULL DEFAULT GETDATE(),
        total_linhas    BIGINT   NULL,        -- aproximado (sys.dm_db_partition_stats)
        ultima_data     DATETIME NULL,        -- MAX(coluna_data)
        last_write      DATETIME NULL,        -- DMV last_user_update
        qtde_ultimo_dia BIGINT   NULL,        -- contagem do dia mais recente da coluna_data
        por_dia         NVARCHAR(MAX) NULL,   -- JSON [{dia, qtde}] últimos N dias
        erro            NVARCHAR(400) NULL,   -- mensagem se a captura falhou
        CONSTRAINT FK_monitor_snap FOREIGN KEY (tabela_id)
            REFERENCES dbo.etl_monitor_tabela(id)
    );
    CREATE NONCLUSTERED INDEX IX_monitor_snap
        ON dbo.etl_monitor_snapshot (tabela_id, captured_at DESC);
    PRINT '[OK] Tabela dbo.etl_monitor_snapshot criada';
END
GO
