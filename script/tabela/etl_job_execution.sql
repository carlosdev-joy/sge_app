USE [DMDB41]
GO

/****** Object:  Table [dbo].[etl_job_execution]    Script Date: 30/05/2026 00:56:44 ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[etl_job_execution](
	[execution_id] [varchar](50) NOT NULL,
	[project] [varchar](100) NOT NULL,
	[job_name] [varchar](200) NOT NULL,
	[pipeline] [varchar](200) NULL,
	[host] [varchar](200) NULL,
	[start_time] [datetime2](7) NOT NULL,
	[end_time] [datetime2](7) NULL,
	[duration_seconds] [int] NULL,
	[status_code] [int] NULL,
	[attempt] [int] NULL,
	[log_file] [varchar](500) NULL,
	[created_at] [datetime2](7) NULL,
	[status] [varchar](20) NULL,
	[updated_at] [datetime2](7) NULL,
	[task_id] [varchar](200) NOT NULL,
 CONSTRAINT [PK_etl_job_execution] PRIMARY KEY CLUSTERED 
(
	[execution_id] ASC,
	[job_name] ASC,
	[task_id] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]
GO

ALTER TABLE [dbo].[etl_job_execution] ADD  DEFAULT ((1)) FOR [attempt]
GO

ALTER TABLE [dbo].[etl_job_execution] ADD  DEFAULT (getdate()) FOR [created_at]
GO

/* ============================================================
   ORQUESTRA — Índices dbo.etl_job_execution (v1.0)
   - Não altera a PK (clustered) existente
   - Índices NONCLUSTERED para suportar consultas (Logs/Dashboard/teams_end)
   - Script idempotente (seguro rodar múltiplas vezes)
   ============================================================ */

-- Índice 1: pipeline + status + start_time
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = 'IX_etl_job_execution_pipeline_status_start'
      AND object_id = OBJECT_ID('dbo.etl_job_execution')
)
BEGIN
    CREATE NONCLUSTERED INDEX [IX_etl_job_execution_pipeline_status_start]
    ON [dbo].[etl_job_execution] ([pipeline] ASC, [status] ASC, [start_time] ASC)
    INCLUDE ([execution_id], [job_name], [end_time], [duration_seconds], [project], [task_id]);
    PRINT 'OK: IX_etl_job_execution_pipeline_status_start';
END
ELSE
    PRINT 'JA EXISTE: IX_etl_job_execution_pipeline_status_start';
GO

-- Índice 2: project + status + start_time
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = 'IX_etl_job_execution_project_status_start'
      AND object_id = OBJECT_ID('dbo.etl_job_execution')
)
BEGIN
    CREATE NONCLUSTERED INDEX [IX_etl_job_execution_project_status_start]
    ON [dbo].[etl_job_execution] ([project] ASC, [status] ASC, [start_time] ASC)
    INCLUDE ([execution_id], [pipeline], [job_name], [end_time], [duration_seconds], [task_id]);
    PRINT 'OK: IX_etl_job_execution_project_status_start';
END
ELSE
    PRINT 'JA EXISTE: IX_etl_job_execution_project_status_start';
GO

-- Índice 3: execution_id + pipeline
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = 'IX_etl_job_execution_execution_id_pipeline'
      AND object_id = OBJECT_ID('dbo.etl_job_execution')
)
BEGIN
    CREATE NONCLUSTERED INDEX [IX_etl_job_execution_execution_id_pipeline]
    ON [dbo].[etl_job_execution] ([execution_id] ASC, [pipeline] ASC)
    INCLUDE ([status], [start_time], [end_time], [duration_seconds]);
    PRINT 'OK: IX_etl_job_execution_execution_id_pipeline';
END
ELSE
    PRINT 'JA EXISTE: IX_etl_job_execution_execution_id_pipeline';
GO


