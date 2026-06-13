-- =============================================================
-- schema_prod_dev.sql
-- Drop + CREATE das tabelas etl_* no schema de PRODUÇÃO
-- (igual ao que a API api/main.py espera).
--
-- Executar ANTES de carregar o dump_prod.sql.
-- NÃO toca em etl_usuario / etl_sessao / etl_perfil* (auth).
--
-- Fluxo completo:
--   1) sqlcmd ... < sql/schema_prod_dev.sql   (este arquivo)
--   2) bash scripts/carregar-dados-dev.sh dump_prod.sql
-- =============================================================
SET NOCOUNT ON;
GO

-- ──────────────────────────────────────────────────────────────
-- 1. Remove FKs que referenciam as tabelas que serão recriadas
-- ──────────────────────────────────────────────────────────────
DECLARE @sql NVARCHAR(MAX) = N'';
DECLARE @alvos TABLE (nome SYSNAME);
INSERT INTO @alvos VALUES
 ('etl_project'),('etl_app_config'),('etl_job_type'),('etl_stage_type_map'),
 ('etl_versao_ferramenta'),('etl_pipeline'),('etl_pipeline_job'),
 ('etl_job_lineage'),('etl_job_execution'),('etl_pipeline_audit'),
 ('etl_pipeline_owner'),('etl_pipeline_performance_snapshot'),
 ('etl_object_tag'),('etl_calendario'),('etl_blackout'),
 ('etl_seq_import'),('etl_seq_import_job'),('etl_seq_import_lineage'),
 ('etl_datastage_job_log'),('etl_factory_log');

SELECT @sql += 'ALTER TABLE ' + QUOTENAME(OBJECT_SCHEMA_NAME(fk.parent_object_id))
            + '.' + QUOTENAME(OBJECT_NAME(fk.parent_object_id))
            + ' DROP CONSTRAINT ' + QUOTENAME(fk.name) + ';' + CHAR(10)
FROM sys.foreign_keys fk
WHERE OBJECT_NAME(fk.parent_object_id)     IN (SELECT nome FROM @alvos)
   OR OBJECT_NAME(fk.referenced_object_id) IN (SELECT nome FROM @alvos);
IF @sql <> N'' EXEC sys.sp_executesql @sql;
PRINT 'FKs removidas.';
GO

-- ──────────────────────────────────────────────────────────────
-- 2. Drop (ordem filho → pai)
-- ──────────────────────────────────────────────────────────────
DROP TABLE IF EXISTS dbo.etl_factory_log;
DROP TABLE IF EXISTS dbo.etl_datastage_job_log;
DROP TABLE IF EXISTS dbo.etl_seq_import_lineage;
DROP TABLE IF EXISTS dbo.etl_seq_import_job;
DROP TABLE IF EXISTS dbo.etl_seq_import;
DROP TABLE IF EXISTS dbo.etl_blackout;
DROP TABLE IF EXISTS dbo.etl_calendario;
DROP TABLE IF EXISTS dbo.etl_pipeline_performance_snapshot;
DROP TABLE IF EXISTS dbo.etl_pipeline_owner;
DROP TABLE IF EXISTS dbo.etl_pipeline_audit;
DROP TABLE IF EXISTS dbo.etl_object_tag;
DROP TABLE IF EXISTS dbo.etl_job_execution;
DROP TABLE IF EXISTS dbo.etl_job_lineage;
DROP TABLE IF EXISTS dbo.etl_pipeline_job;
DROP TABLE IF EXISTS dbo.etl_pipeline;
DROP TABLE IF EXISTS dbo.etl_versao_ferramenta;
DROP TABLE IF EXISTS dbo.etl_stage_type_map;
DROP TABLE IF EXISTS dbo.etl_job_type;
DROP TABLE IF EXISTS dbo.etl_app_config;
DROP TABLE IF EXISTS dbo.etl_project;
-- tabelas EXTRA que o dev tinha com schema divergente
DROP TABLE IF EXISTS dbo.etl_ds_job_log;
DROP TABLE IF EXISTS dbo.etl_configuracao;
PRINT 'Tabelas dropadas.';
GO

-- ──────────────────────────────────────────────────────────────
-- 3. CREATE TABLE no schema de produção
-- ──────────────────────────────────────────────────────────────

CREATE TABLE dbo.etl_project (
    project_name  NVARCHAR(200) NOT NULL CONSTRAINT PK_etl_project PRIMARY KEY,
    descricao     NVARCHAR(500) NULL,
    ativo         BIT           NOT NULL DEFAULT 1,
    criado_em     DATETIME      NOT NULL DEFAULT GETDATE()
);
GO

CREATE TABLE dbo.etl_app_config (
    config_key    NVARCHAR(200)  NOT NULL CONSTRAINT PK_etl_app_config PRIMARY KEY,
    config_value  NVARCHAR(MAX)  NULL,
    descricao     NVARCHAR(500)  NULL,
    updated_by    NVARCHAR(100)  NULL,
    updated_at    DATETIME       NOT NULL DEFAULT GETDATE()
);
GO

CREATE TABLE dbo.etl_job_type (
    id          INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_job_type PRIMARY KEY,
    type_name   NVARCHAR(100)     NOT NULL,
    descricao   NVARCHAR(500)     NULL,
    ativo       BIT               NOT NULL DEFAULT 1
);
GO

CREATE TABLE dbo.etl_stage_type_map (
    stage_type    NVARCHAR(100) NOT NULL CONSTRAINT PK_etl_stage_type_map PRIMARY KEY,
    type_label    NVARCHAR(100) NOT NULL,
    type_category NVARCHAR(50)  NULL,
    role_hint     NVARCHAR(50)  NULL
);
GO

CREATE TABLE dbo.etl_versao_ferramenta (
    id            INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_versao_ferramenta PRIMARY KEY,
    versao        NVARCHAR(50)      NOT NULL,
    titulo        NVARCHAR(200)     NULL,
    descricao_md  NVARCHAR(MAX)     NULL,
    criado_em     DATETIME          NOT NULL DEFAULT GETDATE(),
    criado_por    NVARCHAR(100)     NULL
);
GO

CREATE TABLE dbo.etl_pipeline (
    pipeline_name           NVARCHAR(200)  NOT NULL CONSTRAINT PK_etl_pipeline PRIMARY KEY,
    project_name            NVARCHAR(200)  NULL,
    domain                  NVARCHAR(200)  NULL,
    tags                    NVARCHAR(600)  NULL,
    scheduled_time          TIME           NULL,
    schedule_type           NVARCHAR(40)   NULL,
    schedule_hour           INT            NULL,
    schedule_minute         INT            NULL,
    schedule_dow            NVARCHAR(40)   NULL,
    schedule_dom            INT            NULL,
    active                  BIT            NOT NULL DEFAULT 1,
    dag_criada              BIT            NOT NULL DEFAULT 0,
    envia_msg_inicio        BIT            NOT NULL DEFAULT 0,
    envia_msg_fim           BIT            NOT NULL DEFAULT 0,
    envia_msg_erro          BIT            NOT NULL DEFAULT 1,
    depends_on              NVARCHAR(4000) NULL,
    dag_start_date          DATE           NULL,
    descricao               NVARCHAR(1000) NULL,
    criticidade             NVARCHAR(20)   NULL,
    sla_minutos             INT            NULL,
    ambiente                NVARCHAR(20)   NULL DEFAULT 'PROD',
    max_active_runs         INT            NULL DEFAULT 1,
    retries_count           INT            NULL DEFAULT 1,
    retry_delay_seconds     INT            NULL DEFAULT 300,
    pool_name               NVARCHAR(200)  NULL,
    last_execution          DATETIME       NULL,
    created_at              DATETIME       NOT NULL DEFAULT GETDATE(),
    updated_at              DATETIME       NOT NULL DEFAULT GETDATE(),
    runbook_md              NVARCHAR(MAX)  NULL,
    calendario_nome         NVARCHAR(100)  NULL,
    somente_dias_uteis      BIT            NULL DEFAULT 0,
    trigger_por_dependencia BIT            NULL DEFAULT 0,
    horarios_especificos    NVARCHAR(MAX)  NULL,
    dias_semana             NVARCHAR(100)  NULL
);
GO

CREATE TABLE dbo.etl_pipeline_job (
    id              INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_pipeline_job PRIMARY KEY,
    pipeline_name   NVARCHAR(200)     NOT NULL,
    job_name        NVARCHAR(200)     NOT NULL,
    execution_order INT               NOT NULL DEFAULT 0,
    job_type        NVARCHAR(50)      NULL,
    job_command     NVARCHAR(MAX)     NULL,
    active          BIT               NOT NULL DEFAULT 1,
    created_at      DATETIME          NOT NULL DEFAULT GETDATE(),
    updated_at      DATETIME          NOT NULL DEFAULT GETDATE()
);
GO

CREATE TABLE dbo.etl_job_lineage (
    id                INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_job_lineage PRIMARY KEY,
    pipeline_name     NVARCHAR(200)     NOT NULL,
    job_name          NVARCHAR(200)     NOT NULL,
    execution_order   INT               NULL,
    direction         NVARCHAR(50)      NULL,
    object_type       NVARCHAR(100)     NULL,
    object_name       NVARCHAR(500)     NULL,
    database_name     NVARCHAR(200)     NULL,
    columns_json      NVARCHAR(MAX)     NULL,
    stage_name        NVARCHAR(200)     NULL,
    stage_type_raw    NVARCHAR(200)     NULL,
    sql_expression    NVARCHAR(MAX)     NULL,
    file_path         NVARCHAR(500)     NULL,
    dsx_source_file   NVARCHAR(500)     NULL,
    extracted_at      DATETIME          NULL,
    extraction_method NVARCHAR(100)     NULL,
    created_at        DATETIME          NOT NULL DEFAULT GETDATE(),
    updated_at        DATETIME          NOT NULL DEFAULT GETDATE()
);
GO

CREATE TABLE dbo.etl_job_execution (
    id               INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_job_execution PRIMARY KEY,
    execution_id     NVARCHAR(100)     NOT NULL,
    project          NVARCHAR(100)     NULL,
    pipeline         NVARCHAR(200)     NULL,
    job_name         NVARCHAR(200)     NULL,
    host             NVARCHAR(200)     NULL,
    status           NVARCHAR(50)      NULL,
    status_code      INT               NULL,
    start_time       DATETIME          NULL,
    end_time         DATETIME          NULL,
    duration_seconds INT               NULL,
    log_file         NVARCHAR(500)     NULL,
    task_id          NVARCHAR(200)     NULL,
    attempt          INT               NULL DEFAULT 1,
    created_at       DATETIME          NOT NULL DEFAULT GETDATE(),
    updated_at       DATETIME          NOT NULL DEFAULT GETDATE()
);
CREATE INDEX IX_etl_job_execution_exec  ON dbo.etl_job_execution (execution_id);
CREATE INDEX IX_etl_job_execution_start ON dbo.etl_job_execution (start_time DESC);
GO

CREATE TABLE dbo.etl_pipeline_audit (
    id            INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_pipeline_audit PRIMARY KEY,
    pipeline_name NVARCHAR(200)     NOT NULL,
    acao          NVARCHAR(100)     NOT NULL,
    usuario       NVARCHAR(100)     NULL,
    detalhe       NVARCHAR(MAX)     NULL,
    criado_em     DATETIME          NOT NULL DEFAULT GETDATE()
);
GO

CREATE TABLE dbo.etl_pipeline_owner (
    id            INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_pipeline_owner PRIMARY KEY,
    pipeline_name NVARCHAR(200)     NOT NULL,
    owner_name    NVARCHAR(200)     NULL,
    owner_email   NVARCHAR(200)     NULL,
    steward_name  NVARCHAR(200)     NULL,
    steward_email NVARCHAR(200)     NULL,
    criado_em     DATETIME          NOT NULL DEFAULT GETDATE()
);
GO

CREATE TABLE dbo.etl_pipeline_performance_snapshot (
    id              INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_perf_snap PRIMARY KEY,
    pipeline        NVARCHAR(200)     NOT NULL,
    project         NVARCHAR(100)     NULL,
    execution_id    NVARCHAR(100)     NULL,
    alerta_horas    INT               NULL,
    elapsed_seconds INT               NULL,
    snapshot_at     DATETIME          NOT NULL DEFAULT GETDATE()
);
GO

CREATE TABLE dbo.etl_object_tag (
    id          INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_object_tag PRIMARY KEY,
    object_key  NVARCHAR(500)     NOT NULL,
    tag         NVARCHAR(50)      NOT NULL,  -- PII / Confidencial / Regulado / Publico
    criado_em   DATETIME          NOT NULL DEFAULT GETDATE()
);
GO

CREATE TABLE dbo.etl_calendario (
    id              INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_calendario PRIMARY KEY,
    calendario_nome NVARCHAR(100)     NOT NULL,
    data            DATE              NOT NULL,
    descricao       NVARCHAR(500)     NULL,
    created_by      NVARCHAR(100)     NULL,
    created_at      DATETIME          NOT NULL DEFAULT GETDATE()
);
GO

CREATE TABLE dbo.etl_blackout (
    id              INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_blackout PRIMARY KEY,
    pipeline_name   NVARCHAR(200)     NULL,
    data_inicio     DATE              NOT NULL,
    data_fim        DATE              NOT NULL,
    motivo          NVARCHAR(500)     NULL,
    criado_por      NVARCHAR(100)     NULL,
    criado_em       DATETIME          NOT NULL DEFAULT GETDATE()
);
GO

CREATE TABLE dbo.etl_seq_import (
    id                    INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_seq_import PRIMARY KEY,
    dsx_filename          NVARCHAR(500)     NULL,
    seq_name_raw          NVARCHAR(500)     NULL,
    seq_name              NVARCHAR(500)     NULL,
    project_name          NVARCHAR(200)     NULL,
    domain                NVARCHAR(200)     NULL,
    pipeline_name_override NVARCHAR(200)    NULL,
    schedule_type         NVARCHAR(50)      NULL,
    schedule_cron         NVARCHAR(100)     NULL,
    schedule_hour         INT               NULL,
    schedule_minute       INT               NULL,
    schedule_dow          NVARCHAR(40)      NULL,
    schedule_dom          INT               NULL,
    status                NVARCHAR(50)      NULL DEFAULT 'pendente',
    obs                   NVARCHAR(MAX)     NULL,
    imported_by           NVARCHAR(100)     NULL,
    imported_at           DATETIME          NOT NULL DEFAULT GETDATE(),
    reviewed_by           NVARCHAR(100)     NULL,
    reviewed_at           DATETIME          NULL,
    pipeline_id           INT               NULL
);
GO

CREATE TABLE dbo.etl_seq_import_job (
    id                INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_seq_import_job PRIMARY KEY,
    import_id         INT               NOT NULL,
    execution_order   INT               NULL,
    job_name_ds       NVARCHAR(200)     NULL,
    job_name_orq      NVARCHAR(200)     NULL,
    job_type          NVARCHAR(50)      NULL,
    job_command       NVARCHAR(MAX)     NULL,
    status            NVARCHAR(50)      NULL DEFAULT 'pendente',
    lineage_extracted BIT               NOT NULL DEFAULT 0,
    lineage_count     INT               NULL DEFAULT 0,
    pipeline_job_id   INT               NULL
);
GO

CREATE TABLE dbo.etl_seq_import_lineage (
    id                INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_seq_import_lineage PRIMARY KEY,
    import_job_id     INT               NOT NULL,
    direction         NVARCHAR(50)      NULL,
    object_type       NVARCHAR(100)     NULL,
    object_name       NVARCHAR(500)     NULL,
    database_name     NVARCHAR(200)     NULL,
    columns_json      NVARCHAR(MAX)     NULL,
    stage_type_raw    NVARCHAR(200)     NULL,
    sql_expression    NVARCHAR(MAX)     NULL,
    file_path         NVARCHAR(500)     NULL,
    dsx_source_file   NVARCHAR(500)     NULL,
    extraction_method NVARCHAR(100)     NULL,
    lineage_id        INT               NULL,
    criado_em         DATETIME          NOT NULL DEFAULT GETDATE()
);
GO

-- etl_datastage_job_log é o nome em PRODUÇÃO
-- (dev usava etl_ds_job_log via migration 010 — agora alinhado com prod)
CREATE TABLE dbo.etl_datastage_job_log (
    id              INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_datastage_job_log PRIMARY KEY,
    execution_id    NVARCHAR(100)     NOT NULL,
    pipeline_name   NVARCHAR(200)     NOT NULL,
    job_name        NVARCHAR(200)     NOT NULL,
    project         NVARCHAR(100)     NOT NULL,
    wave_number     INT               NULL,
    pid             NVARCHAR(20)      NULL,
    status          NVARCHAR(50)      NOT NULL DEFAULT 'RUNNING',
    status_code     INT               NULL,
    child_jobs      NVARCHAR(MAX)     NULL,
    log_summary     NVARCHAR(MAX)     NULL,
    poll_snapshots  NVARCHAR(MAX)     NULL,
    last_polled_at  DATETIME          NULL,
    created_at      DATETIME          NOT NULL DEFAULT GETDATE(),
    updated_at      DATETIME          NOT NULL DEFAULT GETDATE()
);
CREATE INDEX IX_ds_job_log_exec ON dbo.etl_datastage_job_log (execution_id);
CREATE INDEX IX_ds_job_log_job  ON dbo.etl_datastage_job_log (job_name, created_at DESC);
GO

CREATE TABLE dbo.etl_factory_log (
    id              INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_factory_log PRIMARY KEY,
    dag_run_id      NVARCHAR(200)     NULL,
    iniciado_em     DATETIME          NULL,
    finalizado_em   DATETIME          NULL,
    estado          NVARCHAR(50)      NULL,
    escopo          NVARCHAR(200)     NULL,
    pipeline_name   NVARCHAR(200)     NULL,
    geradas         INT               NULL DEFAULT 0,
    erros           INT               NULL DEFAULT 0,
    detalhes_json   NVARCHAR(MAX)     NULL
);
GO

-- ──────────────────────────────────────────────────────────────
-- 4. Alias: a API usa etl_ds_job_log em alguns lugares;
--    cria uma VIEW para compatibilidade retroativa
-- ──────────────────────────────────────────────────────────────
CREATE OR ALTER VIEW dbo.etl_ds_job_log AS
    SELECT * FROM dbo.etl_datastage_job_log;
GO

PRINT '============================================================';
PRINT ' Schema de producao aplicado no DEV com sucesso.';
PRINT ' Execute agora: bash scripts/carregar-dados-dev.sh dump_prod.sql';
PRINT '============================================================';
GO
