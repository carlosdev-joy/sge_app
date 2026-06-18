-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 028 — Malha DataStage persistida (a partir do export XML <DSExport>)
--   Parseia o XML UMA vez e grava a estrutura, evitando reanálise a cada consulta.
--   APARTADO da geração de DAG e das tabelas de pipeline do Orquestra.
--
--   etl_ds_malha       — cabeçalho por projeto (servidor, versão, contagens)
--   etl_ds_malha_node  — jobs/sequences (nós)
--   etl_ds_malha_edge  — chamadas (parent → real_target), em ordem
-- ═══════════════════════════════════════════════════════════════════════════

-- 1. Cabeçalho por projeto
IF OBJECT_ID('dbo.etl_ds_malha', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_ds_malha (
        project       NVARCHAR(200) NOT NULL PRIMARY KEY,
        server_name   NVARCHAR(200) NULL,
        ds_version    VARCHAR(30)   NULL,
        source_file   NVARCHAR(400) NULL,
        nodes_count   INT           NOT NULL DEFAULT 0,
        edges_count   INT           NOT NULL DEFAULT 0,
        imported_by   NVARCHAR(100) NULL,
        imported_at   DATETIME2(7)  NOT NULL DEFAULT SYSDATETIME()
    );
END
GO

-- 2. Nós (jobs / sequences)
IF OBJECT_ID('dbo.etl_ds_malha_node', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_ds_malha_node (
        id           INT IDENTITY(1,1) PRIMARY KEY,
        project      NVARCHAR(200) NOT NULL,
        name         NVARCHAR(300) NOT NULL,
        kind         VARCHAR(20)   NOT NULL,   -- sequence | job | executor
        is_sequence  BIT           NOT NULL DEFAULT 0,
        is_executor  BIT           NOT NULL DEFAULT 0,
        stage_types  NVARCHAR(MAX) NULL        -- JSON array
    );
    CREATE UNIQUE INDEX UX_etl_ds_malha_node ON dbo.etl_ds_malha_node (project, name);
END
GO

-- 3. Arestas (chamadas: parent → real_target)
IF OBJECT_ID('dbo.etl_ds_malha_edge', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_ds_malha_edge (
        id           INT IDENTITY(1,1) PRIMARY KEY,
        project      NVARCHAR(200) NOT NULL,
        parent       NVARCHAR(300) NOT NULL,
        seq_order    INT           NOT NULL DEFAULT 0,
        activity     NVARCHAR(300) NULL,
        jobname      NVARCHAR(300) NULL,       -- nome chamado no DSX (pode ser o wrapper)
        real_target  NVARCHAR(300) NULL,       -- job real (ParmNomeJob resolvido)
        kind         VARCHAR(20)   NOT NULL    -- JOB | ROTINA | CMD
    );
    CREATE INDEX IX_etl_ds_malha_edge_parent ON dbo.etl_ds_malha_edge (project, parent, seq_order);
    CREATE INDEX IX_etl_ds_malha_edge_target ON dbo.etl_ds_malha_edge (project, real_target);
END
GO
