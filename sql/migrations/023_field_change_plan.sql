-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 023 — Planos de ajuste de campos (worklist operacional)
--   A partir da busca de impacto por campo (DSX), o usuário monta um "plano"
--   com os campos a alterar (ex.: CNPJ em BIGINT → VARCHAR) e acompanha o
--   andamento item a item, com data/hora e responsável.
--
--   etl_field_change_plan  — o lote/plano
--   etl_field_change_item  — cada ocorrência a alterar (job + stage + coluna)
-- ═══════════════════════════════════════════════════════════════════════════

-- 1. Plano
IF OBJECT_ID('dbo.etl_field_change_plan', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_field_change_plan (
        id            INT IDENTITY(1,1) PRIMARY KEY,
        nome          NVARCHAR(200) NOT NULL,
        descricao     NVARCHAR(MAX) NULL,
        status        VARCHAR(20)   NOT NULL DEFAULT 'aberto',  -- aberto | finalizado
        created_by    NVARCHAR(100) NULL,
        created_at    DATETIME2(7)  NOT NULL DEFAULT SYSDATETIME(),
        updated_at    DATETIME2(7)  NOT NULL DEFAULT SYSDATETIME(),
        finalized_at  DATETIME2(7)  NULL,
        finalized_by  NVARCHAR(100) NULL
    );
END
GO

-- 2. Item (granularidade: ocorrência = job + stage + coluna)
IF OBJECT_ID('dbo.etl_field_change_item', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_field_change_item (
        id              INT IDENTITY(1,1) PRIMARY KEY,
        plan_id         INT           NOT NULL,
        dsx_file        VARCHAR(200)  NULL,
        project_name    VARCHAR(200)  NULL,
        job_name        NVARCHAR(200) NOT NULL,
        stage_name      VARCHAR(200)  NULL,
        stage_type      VARCHAR(100)  NULL,
        direction       VARCHAR(30)   NULL,
        object_name     NVARCHAR(500) NULL,
        column_name     NVARCHAR(200) NOT NULL,
        datatype_atual  VARCHAR(60)   NULL,
        precision_val   INT           NULL,
        scale_val       INT           NULL,
        datatype_alvo   VARCHAR(60)   NULL,
        status          VARCHAR(20)   NOT NULL DEFAULT 'pendente', -- pendente | em_andamento | concluido
        observacao      NVARCHAR(MAX) NULL,
        assigned_to     NVARCHAR(100) NULL,
        started_at      DATETIME2(7)  NULL,
        done_at         DATETIME2(7)  NULL,
        done_by         NVARCHAR(100) NULL,
        created_at      DATETIME2(7)  NOT NULL DEFAULT SYSDATETIME(),
        updated_at      DATETIME2(7)  NOT NULL DEFAULT SYSDATETIME(),
        CONSTRAINT FK_etl_field_change_item_plan
            FOREIGN KEY (plan_id) REFERENCES dbo.etl_field_change_plan(id) ON DELETE CASCADE
    );
    -- Evita duplicar a mesma ocorrência dentro de um plano
    CREATE UNIQUE INDEX UX_etl_field_change_item
        ON dbo.etl_field_change_item (plan_id, job_name, stage_name, column_name);
    CREATE INDEX IX_etl_field_change_item_plan
        ON dbo.etl_field_change_item (plan_id, status);
END
GO
