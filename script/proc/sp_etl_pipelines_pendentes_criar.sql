USE [DMDB41]
GO

/****** Object:  StoredProcedure [dbo].[sp_etl_pipelines_pendentes_criar]    Script Date: 30/05/2026 00:58:06 ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
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


