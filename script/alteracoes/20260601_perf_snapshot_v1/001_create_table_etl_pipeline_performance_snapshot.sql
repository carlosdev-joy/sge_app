USE [DMDB41];
GO

/* ============================================================
   ORQUESTRA — Alteração (v1.0)
   Criação da tabela dbo.etl_pipeline_performance_snapshot + índice

   Observações:
   - Para novos ambientes, o DDL oficial está em: script/tabela/etl_pipeline_performance_snapshot.sql
   - Este script é para rodar em ambiente já existente.
   - Idempotente: cria somente se ainda não existir.
   ============================================================ */

IF OBJECT_ID('dbo.etl_pipeline_performance_snapshot', 'U') IS NULL
BEGIN
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
    PRINT 'OK: dbo.etl_pipeline_performance_snapshot criada';
END
ELSE
    PRINT 'JA EXISTE: dbo.etl_pipeline_performance_snapshot';
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = 'IX_perf_snap_pipeline_alert'
      AND object_id = OBJECT_ID('dbo.etl_pipeline_performance_snapshot')
)
BEGIN
    CREATE NONCLUSTERED INDEX [IX_perf_snap_pipeline_alert]
    ON [dbo].[etl_pipeline_performance_snapshot] ([pipeline], [alerta_horas], [snapshot_at]);
    PRINT 'OK: IX_perf_snap_pipeline_alert';
END
ELSE
    PRINT 'JA EXISTE: IX_perf_snap_pipeline_alert';
GO

