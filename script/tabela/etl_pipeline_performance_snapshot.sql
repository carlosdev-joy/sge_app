USE [DMDB41];
GO

/* ============================================================
   ORQUESTRA — Tabela de Snapshot de Performance (v1.0)

   Objetivo:
   - Registrar histórico de alertas (3h/6h/12h) para pipelines em RUNNING.
   - Base para análise de tendência de performance ao longo do tempo.
   ============================================================ */

CREATE TABLE [dbo].[etl_pipeline_performance_snapshot] (
    [id]              INT IDENTITY(1,1) NOT NULL,
    [pipeline]         VARCHAR(200) NOT NULL,
    [project]          VARCHAR(100) NOT NULL,
    [execution_id]     VARCHAR(50)  NOT NULL,
    [alerta_horas]     INT          NOT NULL,   -- 3, 6 ou 12
    [elapsed_seconds]  INT          NOT NULL,   -- tempo decorrido no snapshot
    [snapshot_at]      DATETIME2    NOT NULL CONSTRAINT [DF_perf_snapshot_at] DEFAULT (GETDATE()),
    CONSTRAINT [PK_perf_snapshot] PRIMARY KEY CLUSTERED ([id] ASC)
);
GO

-- Índice para análise temporal por pipeline/alerta
CREATE NONCLUSTERED INDEX [IX_perf_snap_pipeline_alert]
ON [dbo].[etl_pipeline_performance_snapshot] ([pipeline], [alerta_horas], [snapshot_at]);
GO

