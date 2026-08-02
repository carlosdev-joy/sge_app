-- =============================================================
-- schema_prod_dev.sql — Drop + CREATE das tabelas etl_* (dados)
-- no schema EXATO de produção (gerado a partir de prod_info.txt).
--
-- NÃO toca: etl_usuario, etl_sessao, etl_perfil*, etl_airflow_role_perfil,
--           etl_schema_version, etl_sla_alert, etl_failure_ack,
--           etl_configuracao, etl_teste_execucao (auth / infra do dev).
--
-- Fluxo:
--   1) sqlcmd ... -i /dev/stdin < sql/schema_prod_dev.sql
--   2) bash scripts/carregar-dados-dev.sh dump_prod.sql
-- =============================================================
SET NOCOUNT ON;
GO

-- ──────────────────────────────────────────────────────────────
-- 1. Remove FKs que envolvem as tabelas alvo
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
 ('etl_ds_job_log'),('etl_datastage_job_log'),('etl_factory_log');

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
-- 2. Drop (filho → pai)
-- ──────────────────────────────────────────────────────────────
-- Views primeiro (runs anteriores podem ter criado etl_ds_job_log/
-- etl_datastage_job_log como VIEW — DROP TABLE numa view dá erro).
DROP VIEW IF EXISTS dbo.etl_ds_job_log;
DROP VIEW IF EXISTS dbo.etl_datastage_job_log;
GO
DROP TABLE IF EXISTS dbo.etl_factory_log;
DROP TABLE IF EXISTS dbo.etl_datastage_job_log;
DROP TABLE IF EXISTS dbo.etl_ds_job_log;
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
-- resíduos do dev antigo
DROP TABLE IF EXISTS dbo.etl_configuracao;
PRINT 'Tabelas dropadas.';
GO

-- ──────────────────────────────────────────────────────────────
-- 3. CREATE TABLE — schema idêntico ao de produção
-- ──────────────────────────────────────────────────────────────

-- etl_project
CREATE TABLE dbo.etl_project (
    project_name  NVARCHAR(100) NOT NULL CONSTRAINT PK_etl_project PRIMARY KEY,
    descricao     NVARCHAR(300) NULL,
    ativo         BIT           NOT NULL,
    criado_em     DATETIME      NOT NULL DEFAULT GETDATE()
);
GO

-- etl_app_config
CREATE TABLE dbo.etl_app_config (
    config_key    VARCHAR(100)   NOT NULL CONSTRAINT PK_etl_app_config PRIMARY KEY,
    config_value  VARCHAR(1000)  NOT NULL,
    descricao     VARCHAR(500)   NULL,
    updated_by    VARCHAR(100)   NULL,
    updated_at    DATETIME       NOT NULL DEFAULT GETDATE()
);
GO

-- etl_job_type
CREATE TABLE dbo.etl_job_type (
    id               INT           IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_job_type PRIMARY KEY,
    nome             NVARCHAR(100) NOT NULL,
    descricao        NVARCHAR(500) NULL,
    lineage_enabled  BIT           NOT NULL DEFAULT 0,
    status           BIT           NOT NULL DEFAULT 1,
    criado_em        DATETIME2     NOT NULL DEFAULT GETDATE(),
    criado_por       NVARCHAR(100) NOT NULL DEFAULT 'system'
);
CREATE UNIQUE INDEX UQ_etl_job_type_nome ON dbo.etl_job_type (nome);
GO

-- etl_stage_type_map
CREATE TABLE dbo.etl_stage_type_map (
    stage_type    NVARCHAR(100) NOT NULL CONSTRAINT PK_etl_stage_type_map PRIMARY KEY,
    type_label    NVARCHAR(100) NOT NULL,
    type_category NVARCHAR(50)  NULL,
    role_hint     NVARCHAR(50)  NULL
);
GO

-- etl_versao_ferramenta
CREATE TABLE dbo.etl_versao_ferramenta (
    id           INT           IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_versao_ferramenta PRIMARY KEY,
    versao       NVARCHAR(20)  NOT NULL,
    titulo       NVARCHAR(200) NOT NULL,
    descricao_md NVARCHAR(MAX) NULL,
    criado_em    DATETIME2     NOT NULL DEFAULT GETDATE(),
    criado_por   NVARCHAR(100) NOT NULL DEFAULT 'system'
);
CREATE INDEX IX_etl_versao_ferramenta_criado ON dbo.etl_versao_ferramenta (criado_em);
GO

-- etl_pipeline
CREATE TABLE dbo.etl_pipeline (
    pipeline_name            NVARCHAR(200) NOT NULL CONSTRAINT PK_etl_pipeline PRIMARY KEY,
    scheduled_time           TIME          NOT NULL DEFAULT '00:00:00',
    active                   BIT           NULL      DEFAULT 1,
    last_execution           DATETIME2     NULL,
    created_at               DATETIME2     NULL      DEFAULT GETDATE(),
    updated_at               DATETIME2     NULL      DEFAULT GETDATE(),
    ENVIA_MSG_INICIO         BIT           NOT NULL  DEFAULT 0,
    ENVIA_MSG_FIM            BIT           NOT NULL  DEFAULT 0,
    ENVIA_MSG_ERRO           BIT           NOT NULL  DEFAULT 1,
    DAG_CRIADA               BIT           NOT NULL  DEFAULT 0,
    project_name             NVARCHAR(50)  NOT NULL  DEFAULT '',
    domain                   NVARCHAR(100) NOT NULL  DEFAULT '',
    tags                     NVARCHAR(500) NOT NULL  DEFAULT '',
    schedule_type            VARCHAR(20)   NULL,
    schedule_hour            TINYINT       NULL,
    schedule_minute          TINYINT       NULL,
    schedule_dow             TINYINT       NULL,
    schedule_dom             TINYINT       NULL,
    depends_on               NVARCHAR(2000) NULL,
    dag_start_date           DATE          NULL,
    descricao                NVARCHAR(500) NULL,
    criticidade              NVARCHAR(10)  NULL,
    sla_minutos              INT           NULL,
    ambiente                 NVARCHAR(10)  NULL,
    max_active_runs          INT           NULL,
    retries_count            INT           NULL,
    retry_delay_seconds      INT           NULL,
    pool_name                NVARCHAR(100) NULL,
    runbook_md               NVARCHAR(MAX) NULL,
    calendario_nome          VARCHAR(100)  NULL,
    somente_dias_uteis       BIT           NOT NULL  DEFAULT 0,
    trigger_por_dependencia  BIT           NOT NULL  DEFAULT 0,
    horarios_especificos     VARCHAR(500)  NULL,
    dias_semana              VARCHAR(30)   NULL,
    -- Drift achado na validação da F5 (2026-08-02): produção TEM esta coluna
    -- (o GET /factory/preview a seleciona direto de etl_pipeline e o factory lê
    -- pipeline.get("ssh_conn_id") como conexão default dos jobs), mas ela não
    -- estava neste dump — no dev o preview quebrava com "Invalid column name".
    ssh_conn_id              VARCHAR(100)  NULL
);
GO

-- etl_pipeline_job  (PK composta — sem identity)
CREATE TABLE dbo.etl_pipeline_job (
    pipeline_name   NVARCHAR(200) NOT NULL,
    job_name        NVARCHAR(200) NOT NULL,
    execution_order INT           NOT NULL DEFAULT 0,
    created_at      DATETIME      NOT NULL DEFAULT GETDATE(),
    updated_at      DATETIME      NULL,
    job_type        NVARCHAR(20)  NOT NULL DEFAULT 'datastage',
    job_command     NVARCHAR(500) NULL,
    CONSTRAINT PK_etl_pipeline_job PRIMARY KEY (pipeline_name, job_name)
);
GO

-- etl_job_lineage
CREATE TABLE dbo.etl_job_lineage (
    id                INT           IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_job_lineage PRIMARY KEY,
    pipeline_name     NVARCHAR(200) NOT NULL,
    job_name          NVARCHAR(200) NOT NULL,
    direction         NVARCHAR(30)  NOT NULL,
    object_type       VARCHAR(100)  NULL,
    object_name       NVARCHAR(500) NOT NULL,
    created_at        DATETIME2     NOT NULL DEFAULT GETDATE(),
    updated_at        DATETIME2     NOT NULL DEFAULT GETDATE(),
    stage_name        VARCHAR(200)  NULL,
    stage_type_raw    VARCHAR(100)  NULL,
    database_name     VARCHAR(200)  NULL,
    sql_expression    NVARCHAR(MAX) NULL,
    dsx_source_file   VARCHAR(500)  NULL,
    extracted_at      DATETIME2     NULL,
    extraction_method VARCHAR(50)   NULL,
    file_path         VARCHAR(500)  NULL,
    columns_json      NVARCHAR(MAX) NULL
);
GO

-- etl_job_execution  (PK composta — sem identity)
CREATE TABLE dbo.etl_job_execution (
    execution_id     VARCHAR(50)   NOT NULL,
    project          VARCHAR(100)  NOT NULL,
    job_name         VARCHAR(200)  NOT NULL,
    pipeline         VARCHAR(200)  NULL,
    host             VARCHAR(200)  NULL,
    start_time       DATETIME2     NOT NULL,
    end_time         DATETIME2     NULL,
    duration_seconds INT           NULL,
    status_code      INT           NULL,
    attempt          INT           NULL,
    log_file         VARCHAR(500)  NULL,
    created_at       DATETIME2     NULL DEFAULT GETDATE(),
    status           VARCHAR(20)   NULL,
    updated_at       DATETIME2     NULL DEFAULT GETDATE(),
    task_id          VARCHAR(200)  NOT NULL,
    CONSTRAINT PK_etl_job_execution PRIMARY KEY (execution_id, job_name, task_id)
);
CREATE UNIQUE INDEX ux_etl_execution  ON dbo.etl_job_execution (execution_id, job_name, task_id);
CREATE INDEX IX_etl_job_execution_execution_id_pipeline
    ON dbo.etl_job_execution (execution_id, pipeline, status, start_time, end_time, duration_seconds);
CREATE INDEX IX_etl_job_execution_job_time
    ON dbo.etl_job_execution (job_name, start_time);
CREATE INDEX IX_etl_job_execution_pipeline_status_start
    ON dbo.etl_job_execution (pipeline, status, start_time);
CREATE INDEX IX_etl_job_execution_status
    ON dbo.etl_job_execution (status_code, start_time);
GO

-- etl_pipeline_audit
CREATE TABLE dbo.etl_pipeline_audit (
    id            BIGINT        IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_pipeline_audit PRIMARY KEY,
    pipeline_name NVARCHAR(200) NOT NULL,
    changed_by    NVARCHAR(100) NOT NULL,
    field_name    NVARCHAR(100) NOT NULL,
    old_value     NVARCHAR(MAX) NULL,
    new_value     NVARCHAR(MAX) NULL,
    changed_at    DATETIME2     NOT NULL DEFAULT GETDATE()
);
CREATE INDEX IX_etl_pipeline_audit_pipeline_name ON dbo.etl_pipeline_audit (pipeline_name, changed_at);
CREATE INDEX IX_etl_pipeline_audit_changed_by    ON dbo.etl_pipeline_audit (changed_by, changed_at);
GO

-- etl_pipeline_owner  (PK = pipeline_name, sem id)
CREATE TABLE dbo.etl_pipeline_owner (
    pipeline_name NVARCHAR(300) NOT NULL CONSTRAINT PK_etl_pipeline_owner PRIMARY KEY,
    owner_name    NVARCHAR(100) NULL,
    owner_email   NVARCHAR(150) NULL,
    steward_name  NVARCHAR(100) NULL,
    steward_email NVARCHAR(150) NULL,
    updated_at    DATETIME      NOT NULL DEFAULT GETDATE(),
    updated_by    NVARCHAR(100) NULL
);
GO

-- etl_pipeline_performance_snapshot
CREATE TABLE dbo.etl_pipeline_performance_snapshot (
    id              INT           IDENTITY(1,1) NOT NULL CONSTRAINT PK_perf_snapshot PRIMARY KEY,
    pipeline        VARCHAR(200)  NOT NULL,
    project         VARCHAR(100)  NOT NULL,
    execution_id    VARCHAR(50)   NOT NULL,
    alerta_horas    INT           NOT NULL,
    elapsed_seconds INT           NOT NULL,
    snapshot_at     DATETIME2     NOT NULL DEFAULT GETDATE()
);
CREATE INDEX IX_perf_snap_pipeline_alert ON dbo.etl_pipeline_performance_snapshot (pipeline, alerta_horas, snapshot_at);
GO

-- etl_object_tag
CREATE TABLE dbo.etl_object_tag (
    id          INT           IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_object_tag PRIMARY KEY,
    object_key  VARCHAR(400)  NOT NULL,
    tag         VARCHAR(50)   NOT NULL,
    added_by    VARCHAR(100)  NULL,
    added_at    DATETIME      NOT NULL DEFAULT GETDATE()
);
CREATE UNIQUE INDEX UQ_object_tag ON dbo.etl_object_tag (object_key, tag);
GO

-- etl_calendario
CREATE TABLE dbo.etl_calendario (
    id              INT           IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_calendario PRIMARY KEY,
    calendario_nome VARCHAR(100)  NOT NULL,
    data            DATE          NOT NULL,
    descricao       NVARCHAR(200) NULL,
    created_by      VARCHAR(100)  NULL,
    created_at      DATETIME      NOT NULL DEFAULT GETDATE()
);
CREATE UNIQUE INDEX UQ_etl_calendario ON dbo.etl_calendario (calendario_nome, data);
GO

-- etl_blackout
CREATE TABLE dbo.etl_blackout (
    id            INT           IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_blackout PRIMARY KEY,
    inicio        DATETIME      NOT NULL,
    fim           DATETIME      NOT NULL,
    escopo        NVARCHAR(200) NULL,
    motivo        NVARCHAR(300) NOT NULL,
    ativo         BIT           NOT NULL DEFAULT 1,
    criado_por    VARCHAR(100)  NULL,
    created_at    DATETIME      NOT NULL DEFAULT GETDATE(),
    encerrado_por VARCHAR(100)  NULL,
    encerrado_em  DATETIME      NULL
);
CREATE INDEX IX_etl_blackout_ativo ON dbo.etl_blackout (ativo, inicio, fim);
GO

-- etl_seq_import
CREATE TABLE dbo.etl_seq_import (
    id                     INT           IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_seq_import PRIMARY KEY,
    dsx_filename           VARCHAR(500)  NOT NULL,
    seq_name_raw           VARCHAR(500)  NOT NULL,
    seq_name               VARCHAR(500)  NOT NULL,
    project_name           VARCHAR(100)  NOT NULL,
    domain                 VARCHAR(100)  NULL,
    pipeline_name_override VARCHAR(300)  NULL,
    schedule_type          VARCHAR(20)   NULL,
    schedule_cron          VARCHAR(100)  NULL,
    schedule_hour          TINYINT       NULL,
    schedule_minute        TINYINT       NULL,
    schedule_dow           TINYINT       NULL,
    schedule_dom           TINYINT       NULL,
    status                 VARCHAR(30)   NOT NULL DEFAULT 'pendente',
    obs                    VARCHAR(1000) NULL,
    imported_by            VARCHAR(100)  NOT NULL,
    imported_at            DATETIME      NOT NULL DEFAULT GETDATE(),
    reviewed_by            VARCHAR(100)  NULL,
    reviewed_at            DATETIME      NULL,
    pipeline_id            INT           NULL
);
CREATE INDEX IX_seq_import_status ON dbo.etl_seq_import (status, imported_at);
GO

-- etl_seq_import_job
CREATE TABLE dbo.etl_seq_import_job (
    id                INT           IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_seq_import_job PRIMARY KEY,
    import_id         INT           NOT NULL,
    execution_order   INT           NOT NULL,
    job_name_ds       VARCHAR(300)  NOT NULL,
    job_name_orq      VARCHAR(300)  NOT NULL,
    job_type          VARCHAR(30)   NOT NULL,
    job_command       VARCHAR(1000) NULL,
    status            VARCHAR(30)   NOT NULL DEFAULT 'pendente',
    lineage_extracted BIT           NOT NULL DEFAULT 0,
    lineage_count     INT           NOT NULL DEFAULT 0,
    pipeline_job_id   INT           NULL
);
GO

-- etl_seq_import_lineage
CREATE TABLE dbo.etl_seq_import_lineage (
    id                INT           IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_seq_import_lineage PRIMARY KEY,
    import_job_id     INT           NOT NULL,
    direction         VARCHAR(20)   NOT NULL,
    object_name       VARCHAR(300)  NOT NULL,
    object_type       VARCHAR(100)  NULL,
    stage_type_raw    VARCHAR(100)  NULL,
    sql_expression    VARCHAR(MAX)  NULL,
    file_path         VARCHAR(500)  NULL,
    database_name     VARCHAR(255)  NULL,
    dsx_source_file   VARCHAR(500)  NULL,
    extraction_method VARCHAR(50)   NULL,
    status            VARCHAR(30)   NOT NULL DEFAULT 'pendente',
    lineage_id        INT           NULL,
    columns_json      NVARCHAR(MAX) NULL
);
GO

-- etl_ds_job_log  (nome real em produção)
CREATE TABLE dbo.etl_ds_job_log (
    id              INT           IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_ds_job_log PRIMARY KEY,
    execution_id    VARCHAR(50)   NOT NULL,
    pipeline_name   VARCHAR(200)  NOT NULL,
    job_name        VARCHAR(200)  NOT NULL,
    project         VARCHAR(100)  NOT NULL,
    wave_number     INT           NULL,
    pid             VARCHAR(20)   NULL,
    status          VARCHAR(50)   NOT NULL DEFAULT 'RUNNING',
    status_code     INT           NULL,
    child_jobs      NVARCHAR(MAX) NULL,
    log_summary     NVARCHAR(MAX) NULL,
    poll_snapshots  NVARCHAR(MAX) NULL,
    last_polled_at  DATETIME      NULL,
    created_at      DATETIME      NOT NULL DEFAULT GETDATE(),
    updated_at      DATETIME      NOT NULL DEFAULT GETDATE(),
    ds_start_time   VARCHAR(50)   NULL,
    ds_end_time     DATETIME      NULL,
    queued_seconds  INT           NULL
);
CREATE INDEX ix_ds_job_log_exec ON dbo.etl_ds_job_log (execution_id);
CREATE INDEX ix_ds_job_log_job  ON dbo.etl_ds_job_log (job_name, created_at DESC);
GO

-- etl_datastage_job_log — alias como view para o dump_prod.sql
-- (dump_dados.py tinha esse nome errado na lista DEFAULT_TABLES)
CREATE VIEW dbo.etl_datastage_job_log AS
    SELECT id, execution_id, pipeline_name, job_name, project,
           wave_number, pid, status, status_code, child_jobs,
           log_summary, poll_snapshots, last_polled_at, created_at, updated_at
    FROM dbo.etl_ds_job_log;
GO

-- etl_factory_log
CREATE TABLE dbo.etl_factory_log (
    id              INT           IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_factory_log PRIMARY KEY,
    dag_run_id      VARCHAR(200)  NOT NULL,
    iniciado_em     DATETIME      NOT NULL DEFAULT GETDATE(),
    finalizado_em   DATETIME      NULL,
    estado          VARCHAR(20)   NOT NULL,
    escopo          NVARCHAR(500) NULL,
    pipeline_name   VARCHAR(200)  NULL,
    geradas         INT           NOT NULL DEFAULT 0,
    erros           INT           NOT NULL DEFAULT 0,
    detalhes_json   NVARCHAR(MAX) NULL
);
CREATE UNIQUE INDEX UQ_etl_factory_log_run ON dbo.etl_factory_log (dag_run_id);
GO

PRINT '============================================================';
PRINT ' Schema de producao aplicado no DEV com sucesso.';
PRINT ' Execute: bash scripts/carregar-dados-dev.sh dump_prod.sql';
PRINT '============================================================';
GO
