USE [DMDB41];
GO

/* ============================================================
   ORQUESTRA — Índices dbo.etl_job_execution | v1.0

   Contexto:
   - Tabela de telemetria central do ORQUESTRA (logs de execução).
   - Índices NONCLUSTERED para suportar:
       * Tela de Logs (filtros por pipeline/status/data)
       * Dashboard (agregações por projeto/pipeline)
       * Função teams_end (lookup por execution_id + pipeline)

   Observações importantes:
   - A PK CLUSTERED (execution_id, job_name, task_id) JÁ EXISTE e NÃO deve ser alterada.
   - Script idempotente: seguro rodar múltiplas vezes (IF NOT EXISTS).
   - Os índices não alteram a forma como a tabela recebe INSERT/UPDATE.
   ============================================================ */

-- ============================================================
-- ÍNDICE 1: pipeline + status + start_time
-- Justificativa: filtro mais comum (pipeline + status + janela de tempo)
-- ============================================================
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = 'IX_etl_job_execution_pipeline_status_start'
      AND object_id = OBJECT_ID('dbo.etl_job_execution')
)
BEGIN
    CREATE NONCLUSTERED INDEX [IX_etl_job_execution_pipeline_status_start]
    ON [dbo].[etl_job_execution] ([pipeline], [status], [start_time])
    INCLUDE ([execution_id], [job_name], [end_time], [duration_seconds], [project], [task_id]);
    PRINT 'OK: IX_etl_job_execution_pipeline_status_start';
END
ELSE
    PRINT 'JA EXISTE: IX_etl_job_execution_pipeline_status_start';
GO

-- ============================================================
-- ÍNDICE 2: project + status + start_time
-- Justificativa: consultas agregadas por projeto (dashboard/gestão)
-- ============================================================
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = 'IX_etl_job_execution_project_status_start'
      AND object_id = OBJECT_ID('dbo.etl_job_execution')
)
BEGIN
    CREATE NONCLUSTERED INDEX [IX_etl_job_execution_project_status_start]
    ON [dbo].[etl_job_execution] ([project], [status], [start_time])
    INCLUDE ([execution_id], [pipeline], [job_name], [end_time], [duration_seconds], [task_id]);
    PRINT 'OK: IX_etl_job_execution_project_status_start';
END
ELSE
    PRINT 'JA EXISTE: IX_etl_job_execution_project_status_start';
GO

-- ============================================================
-- ÍNDICE 3: execution_id + pipeline
-- Justificativa: lookup de consolidação (teams_end) e drill-down
-- ============================================================
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = 'IX_etl_job_execution_execution_id_pipeline'
      AND object_id = OBJECT_ID('dbo.etl_job_execution')
)
BEGIN
    CREATE NONCLUSTERED INDEX [IX_etl_job_execution_execution_id_pipeline]
    ON [dbo].[etl_job_execution] ([execution_id], [pipeline])
    INCLUDE ([status], [start_time], [end_time], [duration_seconds]);
    PRINT 'OK: IX_etl_job_execution_execution_id_pipeline';
END
ELSE
    PRINT 'JA EXISTE: IX_etl_job_execution_execution_id_pipeline';
GO

-- ============================================================
-- VERIFICAÇÃO: listar todos os índices da tabela
-- Esperado: 1 PK CLUSTERED + 3 NONCLUSTERED (nomes acima)
-- ============================================================
SELECT
    i.name AS indice,
    i.type_desc AS tipo,
    i.is_primary_key AS pk,
    i.is_unique AS unico
FROM sys.indexes i
WHERE i.object_id = OBJECT_ID('dbo.etl_job_execution')
ORDER BY i.index_id;
GO

