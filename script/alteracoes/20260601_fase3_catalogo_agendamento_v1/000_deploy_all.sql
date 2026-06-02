USE [DMDB41];
GO

/* ============================================================
   ORQUESTRA — Fase 3: Catálogo Detalhado + Agendamento Avançado (v1.0)
   Deploy único (produção): idempotente.

   Inclui:
   1) ALTER TABLE dbo.etl_pipeline (schedule_type + campos auxiliares)
   2) ALTER PROC dbo.sp_etl_pipeline_upsert (novos parâmetros)
   3) ALTER PROC dbo.sp_etl_pipelines_pendentes_criar (retorna schedule_* para factory)
   ============================================================ */

/* 1) dbo.etl_pipeline — colunas de agendamento */
IF COL_LENGTH('dbo.etl_pipeline', 'schedule_type') IS NULL
BEGIN
    ALTER TABLE dbo.etl_pipeline ADD schedule_type VARCHAR(20) NULL;
    PRINT 'OK: dbo.etl_pipeline.schedule_type';
END
GO

IF COL_LENGTH('dbo.etl_pipeline', 'schedule_hour') IS NULL
BEGIN
    ALTER TABLE dbo.etl_pipeline ADD schedule_hour TINYINT NULL;
    PRINT 'OK: dbo.etl_pipeline.schedule_hour';
END
GO

IF COL_LENGTH('dbo.etl_pipeline', 'schedule_minute') IS NULL
BEGIN
    ALTER TABLE dbo.etl_pipeline ADD schedule_minute TINYINT NULL;
    PRINT 'OK: dbo.etl_pipeline.schedule_minute';
END
GO

IF COL_LENGTH('dbo.etl_pipeline', 'schedule_dow') IS NULL
BEGIN
    ALTER TABLE dbo.etl_pipeline ADD schedule_dow TINYINT NULL;
    PRINT 'OK: dbo.etl_pipeline.schedule_dow';
END
GO

IF COL_LENGTH('dbo.etl_pipeline', 'schedule_dom') IS NULL
BEGIN
    ALTER TABLE dbo.etl_pipeline ADD schedule_dom TINYINT NULL;
    PRINT 'OK: dbo.etl_pipeline.schedule_dom';
END
GO

/* 2) sp_etl_pipeline_upsert */
CREATE OR ALTER PROCEDURE [dbo].[sp_etl_pipeline_upsert]
(
    @pipeline_name    NVARCHAR(200),
    @scheduled_time   TIME(0),
    @schedule_type    VARCHAR(20)    = NULL,
    @schedule_hour    TINYINT        = NULL,
    @schedule_minute  TINYINT        = NULL,
    @schedule_dow     TINYINT        = NULL,
    @schedule_dom     TINYINT        = NULL,
    @active           BIT           = 1,
    @envia_msg_inicio BIT           = 1,
    @envia_msg_fim    BIT           = 1,
    @envia_msg_erro   BIT           = 1,
    @dag_criada       BIT           = 0,
    @project_name     NVARCHAR(50),
    @domain           NVARCHAR(100),
    @tags             NVARCHAR(500) = ''
)
AS
BEGIN
    SET NOCOUNT ON;

    IF EXISTS (SELECT 1 FROM dbo.etl_pipeline WHERE pipeline_name = @pipeline_name)
    BEGIN
        UPDATE dbo.etl_pipeline
        SET
            scheduled_time   = @scheduled_time,
            schedule_type    = COALESCE(@schedule_type, schedule_type),
            schedule_hour    = COALESCE(@schedule_hour, schedule_hour),
            schedule_minute  = COALESCE(@schedule_minute, schedule_minute),
            schedule_dow     = COALESCE(@schedule_dow, schedule_dow),
            schedule_dom     = COALESCE(@schedule_dom, schedule_dom),
            active           = @active,
            ENVIA_MSG_INICIO = @envia_msg_inicio,
            ENVIA_MSG_FIM    = @envia_msg_fim,
            ENVIA_MSG_ERRO   = @envia_msg_erro,
            DAG_CRIADA       = @dag_criada,
            project_name     = @project_name,
            domain           = @domain,
            tags             = @tags,
            updated_at       = SYSDATETIME()
        WHERE pipeline_name = @pipeline_name;
    END
    ELSE
    BEGIN
        INSERT INTO dbo.etl_pipeline (
            pipeline_name, scheduled_time,
            schedule_type, schedule_hour, schedule_minute, schedule_dow, schedule_dom,
            active, last_execution, created_at, updated_at,
            ENVIA_MSG_INICIO, ENVIA_MSG_FIM, ENVIA_MSG_ERRO, DAG_CRIADA,
            project_name, domain, tags
        )
        VALUES (
            @pipeline_name, @scheduled_time,
            @schedule_type, @schedule_hour, @schedule_minute, @schedule_dow, @schedule_dom,
            @active, NULL, SYSDATETIME(), SYSDATETIME(),
            @envia_msg_inicio, @envia_msg_fim, @envia_msg_erro, @dag_criada,
            @project_name, @domain, @tags
        );
    END
END
GO

PRINT 'OK: sp_etl_pipeline_upsert (Fase 3 schedule)';
GO

/* 3) sp_etl_pipelines_pendentes_criar — inclui schedule_* */
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
        ISNULL(j.job_command, '') AS job_command
    FROM dbo.etl_pipeline_job j
    INNER JOIN dbo.etl_pipeline p
        ON p.pipeline_name = j.pipeline_name
    WHERE p.DAG_CRIADA = 0
      AND p.active     = 1
    ORDER BY j.pipeline_name, j.execution_order;
END
GO

PRINT 'OK: sp_etl_pipelines_pendentes_criar (Fase 3 schedule)';
GO

