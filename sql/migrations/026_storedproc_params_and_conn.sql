-- Migration 026 — Stored procedure com parâmetros fixos + conexão MSSQL por job
--   mssql_conn_id  : conexão Airflow por job (NULL = usa MSSQL_CONN_ID global, igual hoje)
--   etl_pipeline_job_param : parâmetros fixos de entrada para jobs job_type='storedproc'
--
--   Corrige também sp_etl_pipelines_pendentes_criar, que não devolvia
--   ssh_conn_id/verbose_log (bug pré-existente) nem mssql_conn_id/params — a fábrica
--   de DAG lia esses campos via job.get(...), que sempre retornava None.

IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_pipeline_job'
      AND COLUMN_NAME='mssql_conn_id'
)
BEGIN
    ALTER TABLE dbo.etl_pipeline_job ADD mssql_conn_id VARCHAR(100) NULL;
    PRINT '[OK] Coluna mssql_conn_id adicionada em dbo.etl_pipeline_job';
END
GO

IF OBJECT_ID('dbo.etl_pipeline_job_param', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_pipeline_job_param (
        id            INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_pipeline_job_param PRIMARY KEY,
        pipeline_name NVARCHAR(200) NOT NULL,
        job_name      NVARCHAR(200) NOT NULL,
        param_name    VARCHAR(128)  NOT NULL,
        param_type    VARCHAR(30)   NOT NULL,
        param_value   NVARCHAR(MAX) NULL,
        param_order   INT           NOT NULL DEFAULT 0,
        created_at    DATETIME2(7)  NOT NULL DEFAULT SYSDATETIME(),
        CONSTRAINT FK_etl_pipeline_job_param_job
            FOREIGN KEY (pipeline_name, job_name)
            REFERENCES dbo.etl_pipeline_job (pipeline_name, job_name) ON DELETE CASCADE
    );
    CREATE INDEX IX_etl_pipeline_job_param_job
        ON dbo.etl_pipeline_job_param (pipeline_name, job_name, param_order);
    PRINT '[OK] Tabela etl_pipeline_job_param criada';
END
GO

CREATE OR ALTER PROCEDURE dbo.sp_etl_pipeline_job_upsert
    @pipeline_name   VARCHAR(200),
    @job_name        VARCHAR(200),
    @execution_order INT,
    @job_type        VARCHAR(50),
    @job_command     NVARCHAR(MAX) = NULL,
    @ssh_conn_id     VARCHAR(100)  = NULL,
    @verbose_log     BIT           = 0,
    @mssql_conn_id   VARCHAR(100)  = NULL
AS
BEGIN
    SET NOCOUNT ON;
    IF EXISTS (SELECT 1 FROM dbo.etl_pipeline_job WHERE pipeline_name=@pipeline_name AND job_name=@job_name)
        UPDATE dbo.etl_pipeline_job
        SET execution_order=@execution_order, job_type=@job_type,
            job_command=@job_command, ssh_conn_id=@ssh_conn_id,
            verbose_log=@verbose_log, mssql_conn_id=@mssql_conn_id, updated_at=GETDATE()
        WHERE pipeline_name=@pipeline_name AND job_name=@job_name;
    ELSE
        INSERT INTO dbo.etl_pipeline_job
            (pipeline_name, job_name, execution_order, job_type, job_command, ssh_conn_id, verbose_log, mssql_conn_id)
        VALUES
            (@pipeline_name, @job_name, @execution_order, @job_type, @job_command, @ssh_conn_id, @verbose_log, @mssql_conn_id);
END
GO

-- Substitui por completo os parâmetros fixos de um job (replace-all a cada save do wizard)
CREATE OR ALTER PROCEDURE dbo.sp_etl_pipeline_job_param_clear
    @pipeline_name VARCHAR(200),
    @job_name      VARCHAR(200)
AS
BEGIN
    SET NOCOUNT ON;
    DELETE FROM dbo.etl_pipeline_job_param WHERE pipeline_name=@pipeline_name AND job_name=@job_name;
END
GO

CREATE OR ALTER PROCEDURE dbo.sp_etl_pipeline_job_param_insert
    @pipeline_name VARCHAR(200),
    @job_name      VARCHAR(200),
    @param_name    VARCHAR(128),
    @param_type    VARCHAR(30),
    @param_value   NVARCHAR(MAX) = NULL,
    @param_order   INT = 0
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO dbo.etl_pipeline_job_param
        (pipeline_name, job_name, param_name, param_type, param_value, param_order)
    VALUES
        (@pipeline_name, @job_name, @param_name, @param_type, @param_value, @param_order);
END
GO

CREATE OR ALTER PROCEDURE [dbo].[sp_etl_pipelines_pendentes_criar]
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        p.pipeline_name,
        p.project_name,
        p.domain,
        p.tags,
        CONVERT(VARCHAR(8), p.scheduled_time, 108) AS scheduled_time,
        p.schedule_type,
        p.schedule_hour,
        p.schedule_minute,
        p.schedule_dow,
        p.schedule_dom,
        p.ENVIA_MSG_INICIO,
        p.ENVIA_MSG_FIM,
        p.ENVIA_MSG_ERRO
    FROM dbo.etl_pipeline p
    WHERE p.DAG_CRIADA = 0
      AND p.active     = 1
    ORDER BY p.project_name, p.domain, p.pipeline_name;

    SELECT
        j.pipeline_name,
        j.job_name,
        j.execution_order,
        j.job_type,
        ISNULL(j.job_command, '')   AS job_command,
        j.ssh_conn_id,
        ISNULL(j.verbose_log, 0)    AS verbose_log,
        j.mssql_conn_id
    FROM dbo.etl_pipeline_job j
    INNER JOIN dbo.etl_pipeline p
        ON p.pipeline_name = j.pipeline_name
    WHERE p.DAG_CRIADA = 0
      AND p.active     = 1
    ORDER BY j.pipeline_name, j.execution_order;

    SELECT
        jp.pipeline_name,
        jp.job_name,
        jp.param_name,
        jp.param_type,
        jp.param_value,
        jp.param_order
    FROM dbo.etl_pipeline_job_param jp
    INNER JOIN dbo.etl_pipeline p
        ON p.pipeline_name = jp.pipeline_name
    WHERE p.DAG_CRIADA = 0
      AND p.active     = 1
    ORDER BY jp.pipeline_name, jp.job_name, jp.param_order;

END
GO
