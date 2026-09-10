-- sql/migrations/109_job_param_override.sql
-- Sobreposição de parâmetros DataStage na REEXECUÇÃO (spec docs/spec-parametros-job-datastage.md, F5).
--
-- O operador reexecuta uma etapa (modal de rerun) e troca o valor de um
-- parâmetro SÓ naquela corrida — ex.: refazer o mês com outra data. O
-- `clearTaskInstances` reusa o mesmo dag_run e o Airflow não deixa editar o
-- `conf`, então a sobreposição vive numa tabela, chaveada pelo run_id:
--
--   dbo.etl_job_param_override — uma linha por (pipeline, job, dag_run_id, param).
--     • gravada pela API ANTES do clear (e apagada se o clear falhar);
--     • lida pelo operador no disparo (passo 3 do §4: sobrepõe etapa e pipeline
--       como valor FIXO, fonte 'rerun');
--     • `consumido_em` carimbado pelo operador quando o valor foi enviado —
--       o rastro de "esse valor foi usado";
--     • Encrypted NÃO pode ser sobreposto (API 422, operador ParamError).
--   FK para dbo.etl_pipeline_job com ON DELETE CASCADE (como a 026/106).
--   param_name em colação binária, como a 108 (o DataStage distingue caixa).
--   dag_run_id NVARCHAR(250): run_id do Airflow (manual__…, scheduled__…, dep__…).
--
-- Idempotente (roda 2×). Aplicada pela etapa 6c do deploy.sh.

IF OBJECT_ID('dbo.etl_job_param_override', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_job_param_override (
        id            INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_job_param_override PRIMARY KEY,
        pipeline_name NVARCHAR(200) NOT NULL,
        job_name      NVARCHAR(200) NOT NULL,
        dag_run_id    NVARCHAR(250) NOT NULL,
        param_name    VARCHAR(128)  COLLATE Latin1_General_BIN2 NOT NULL,
        param_value   NVARCHAR(MAX) NULL,
        criado_em     DATETIME2(0)  NOT NULL CONSTRAINT DF_etl_job_param_override_em DEFAULT GETDATE(),
        criado_por    NVARCHAR(100) NULL,       -- matrícula (vocabulário de etl_pipeline_audit.changed_by)
        consumido_em  DATETIME2(0)  NULL,       -- carimbado pelo operador quando o valor foi enviado
        CONSTRAINT UQ_etl_job_param_override UNIQUE (pipeline_name, job_name, dag_run_id, param_name),
        CONSTRAINT FK_etl_job_param_override_job FOREIGN KEY (pipeline_name, job_name)
            REFERENCES dbo.etl_pipeline_job (pipeline_name, job_name) ON DELETE CASCADE
    );
    PRINT '[OK] Tabela dbo.etl_job_param_override criada';
END
ELSE
    PRINT '[SKIP] dbo.etl_job_param_override ja existe';
GO

-- A consulta do operador: (pipeline, run, job). Guarda própria, como as
-- demais migrations (o índice pode faltar num banco restaurado).
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_etl_job_param_override_run'
               AND object_id = OBJECT_ID('dbo.etl_job_param_override'))
BEGIN
    CREATE INDEX IX_etl_job_param_override_run
        ON dbo.etl_job_param_override (pipeline_name, dag_run_id, job_name);
    PRINT '[OK] IX_etl_job_param_override_run criado';
END
ELSE
    PRINT '[SKIP] IX_etl_job_param_override_run ja existe';
GO
