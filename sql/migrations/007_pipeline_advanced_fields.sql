-- ============================================================
-- Migração 007: Campos Avançados de Pipeline + Tabela etl_project
-- Adiciona campos de configuração operacional ao editor de pipeline
-- e cria tabela de projetos com seed inicial.
-- ============================================================

-- 1. descricao: descrição livre do pipeline
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.etl_pipeline') AND name = 'descricao'
)
    ALTER TABLE dbo.etl_pipeline ADD descricao NVARCHAR(500) NULL;

-- 2. criticidade: prioridade do pipeline (Alta, Media, Baixa)
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.etl_pipeline') AND name = 'criticidade'
)
    ALTER TABLE dbo.etl_pipeline ADD criticidade NVARCHAR(10) NULL DEFAULT 'Media';

-- 3. sla_minutos: tempo máximo esperado de execução em minutos (NULL = sem SLA)
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.etl_pipeline') AND name = 'sla_minutos'
)
    ALTER TABLE dbo.etl_pipeline ADD sla_minutos INT NULL;

-- 4. ambiente: ambiente de execução (DEV, HOM, PROD)
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.etl_pipeline') AND name = 'ambiente'
)
    ALTER TABLE dbo.etl_pipeline ADD ambiente NVARCHAR(10) NULL DEFAULT 'PROD';

-- 5. max_active_runs: máximo de execuções simultâneas permitidas
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.etl_pipeline') AND name = 'max_active_runs'
)
    ALTER TABLE dbo.etl_pipeline ADD max_active_runs INT NULL DEFAULT 1;

-- 6. retries_count: número de tentativas em caso de falha
--    (nomeado retries_count para evitar conflito com palavra reservada RETRIES)
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.etl_pipeline') AND name = 'retries_count'
)
    ALTER TABLE dbo.etl_pipeline ADD retries_count INT NULL DEFAULT 1;

-- 7. retry_delay_seconds: intervalo em segundos entre tentativas
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.etl_pipeline') AND name = 'retry_delay_seconds'
)
    ALTER TABLE dbo.etl_pipeline ADD retry_delay_seconds INT NULL DEFAULT 300;

-- 8. pool_name: pool de execução do Airflow (NULL = default_pool)
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.etl_pipeline') AND name = 'pool_name'
)
    ALTER TABLE dbo.etl_pipeline ADD pool_name NVARCHAR(100) NULL;

-- ============================================================
-- Expandir depends_on de NVARCHAR(200) para NVARCHAR(2000)
-- para suportar múltiplas dependências separadas por vírgula
-- ============================================================
IF COL_LENGTH('dbo.etl_pipeline', 'depends_on') < 2000
    ALTER TABLE dbo.etl_pipeline ALTER COLUMN depends_on NVARCHAR(2000) NULL;

-- ============================================================
-- Tabela etl_project: projetos/domínios de negócio
-- ============================================================
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'etl_project')
CREATE TABLE dbo.etl_project (
    project_name  NVARCHAR(100) NOT NULL,
    descricao     NVARCHAR(300) NULL,
    ativo         BIT           NOT NULL DEFAULT 1,
    criado_em     DATETIME      NOT NULL DEFAULT GETDATE(),
    CONSTRAINT PK_etl_project PRIMARY KEY (project_name)
);

-- Seed: projetos iniciais
IF NOT EXISTS (SELECT 1 FROM dbo.etl_project WHERE project_name = 'BI_CVP')
    INSERT INTO dbo.etl_project (project_name) VALUES ('BI_CVP');

IF NOT EXISTS (SELECT 1 FROM dbo.etl_project WHERE project_name = 'BI_VIDA')
    INSERT INTO dbo.etl_project (project_name) VALUES ('BI_VIDA');

IF NOT EXISTS (SELECT 1 FROM dbo.etl_project WHERE project_name = 'BI_PRESTAMISTA')
    INSERT INTO dbo.etl_project (project_name) VALUES ('BI_PRESTAMISTA');

IF NOT EXISTS (SELECT 1 FROM dbo.etl_project WHERE project_name = 'BI_PREVIDENCIA')
    INSERT INTO dbo.etl_project (project_name) VALUES ('BI_PREVIDENCIA');

-- ============================================================
-- Nota de Auditoria:
-- Os campos abaixo adicionados a dbo.etl_pipeline devem ser
-- rastreados pela tabela dbo.etl_pipeline_audit. O registro
-- das alterações nesses campos é gerenciado pelo código DAG
-- (não por trigger SQL), pois o contexto de usuário/sessão
-- está disponível apenas na camada de aplicação:
--   - criticidade
--   - sla_minutos
--   - ambiente
--   - max_active_runs
--   - retries_count
--   - retry_delay_seconds
--   - pool_name
--   - descricao
-- ============================================================

PRINT '==> Migração 007: campos avançados de pipeline e tabela etl_project criados.';
GO
