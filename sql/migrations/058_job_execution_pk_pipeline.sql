-- 058_job_execution_pk_pipeline.sql
-- Fase 2 da migration 027 — elimina a colisão de execution_id entre pipelines.
--
-- execution_id = ts_nodash (timestamp lógico do run) COLIDE quando duas
-- pipelines agendadas no mesmo tick têm job homônimo: as SPs da 027 filtram
-- por pipeline no WHERE, "não acham" a linha da outra pipeline e INSEREM —
-- violação do PK antigo (execution_id, job_name, task_id), que derruba o run
-- da 2ª pipeline no log_start com card Teams "Job com falha: Não identificado".
--
-- O que faz:
--   1. backfill de pipeline NULL (linhas históricas) + ALTER NOT NULL;
--   2. DROP do índice único duplicado ux_etl_execution (mesmas colunas do PK
--      antigo — sem isso a troca do PK não resolveria nada);
--   3. PK recriado como (execution_id, pipeline, job_name, task_id);
--   4. etl_ds_job_log: dedupe (mantém a linha mais recente por chave) + índice
--      ÚNICO filtrado (execution_id, pipeline_name, job_name) — trava a corrida
--      monitor×operador que podia duplicar linhas.
--
-- OPERAÇÃO (janela): a tabela é quente (log_start de toda task + monitor a
-- cada ciclo). Aplicar SEM execuções em andamento — pausar scheduler/monitor
-- durante a janela; o rebuild do PK clusterizado pode demorar em tabela grande.
--
-- Defensiva: só roda no shape de produção (coluna 'pipeline' + 'task_id');
-- o shape alternativo do deploy_full.sql (id IDENTITY/pipeline_name) é
-- ignorado com [SKIP]. Idempotente — seguro para rodar mais de uma vez.

-- 1) Backfill: linha histórica sem pipeline não pode entrar no PK.
IF COL_LENGTH('dbo.etl_job_execution', 'pipeline') IS NOT NULL
   AND COL_LENGTH('dbo.etl_job_execution', 'task_id') IS NOT NULL
BEGIN
    UPDATE dbo.etl_job_execution SET pipeline = '(desconhecido)'
     WHERE pipeline IS NULL;
    PRINT '[OK] backfill de pipeline NULL concluido';
END
ELSE
    PRINT '[SKIP] etl_job_execution sem o shape esperado (pipeline/task_id) — nada a fazer';
GO

-- 1b) NOT NULL (só se ainda for anulável).
IF COL_LENGTH('dbo.etl_job_execution', 'pipeline') IS NOT NULL
   AND COL_LENGTH('dbo.etl_job_execution', 'task_id') IS NOT NULL
   AND EXISTS (SELECT 1 FROM sys.columns
               WHERE object_id = OBJECT_ID('dbo.etl_job_execution')
                 AND name = 'pipeline' AND is_nullable = 1)
BEGIN
    ALTER TABLE dbo.etl_job_execution ALTER COLUMN pipeline VARCHAR(200) NOT NULL;
    PRINT '[OK] etl_job_execution.pipeline agora NOT NULL';
END
ELSE
    PRINT '[SKIP] pipeline ja e NOT NULL (ou shape divergente)';
GO

-- 2) Índice único duplicado do PK antigo — manteria a colisão mesmo com PK novo.
IF EXISTS (SELECT 1 FROM sys.indexes
           WHERE object_id = OBJECT_ID('dbo.etl_job_execution')
             AND name = 'ux_etl_execution')
BEGIN
    DROP INDEX ux_etl_execution ON dbo.etl_job_execution;
    PRINT '[OK] indice unico ux_etl_execution removido';
END
ELSE
    PRINT '[SKIP] ux_etl_execution ja nao existe';
GO

-- 3) PK com pipeline (só se o PK atual ainda não contém a coluna).
IF COL_LENGTH('dbo.etl_job_execution', 'pipeline') IS NOT NULL
   AND COL_LENGTH('dbo.etl_job_execution', 'task_id') IS NOT NULL
   AND EXISTS (SELECT 1 FROM sys.key_constraints
               WHERE parent_object_id = OBJECT_ID('dbo.etl_job_execution')
                 AND type = 'PK')
   AND NOT EXISTS (
       SELECT 1
       FROM sys.index_columns ic
       JOIN sys.indexes i ON i.object_id = ic.object_id AND i.index_id = ic.index_id
       JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
       WHERE i.object_id = OBJECT_ID('dbo.etl_job_execution')
         AND i.is_primary_key = 1 AND c.name = 'pipeline')
BEGIN
    ALTER TABLE dbo.etl_job_execution DROP CONSTRAINT PK_etl_job_execution;
    ALTER TABLE dbo.etl_job_execution ADD CONSTRAINT PK_etl_job_execution
        PRIMARY KEY CLUSTERED (execution_id, pipeline, job_name, task_id);
    PRINT '[OK] PK recriado como (execution_id, pipeline, job_name, task_id)';
END
ELSE
    PRINT '[SKIP] PK ja contem pipeline (ou shape divergente)';
GO

-- 4) etl_ds_job_log: dedupe + unicidade natural (filtrada p/ legado com NULL).
IF OBJECT_ID('dbo.etl_ds_job_log', 'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.indexes
                   WHERE object_id = OBJECT_ID('dbo.etl_ds_job_log')
                     AND name = 'UX_etl_ds_job_log_run')
BEGIN
    -- Mantém, por chave, a linha mais recente (updated_at > last_polled_at >
    -- created_at > id) — as demais são duplicatas da corrida monitor×operador.
    ;WITH d AS (
        SELECT id, ROW_NUMBER() OVER (
            PARTITION BY execution_id, pipeline_name, job_name
            ORDER BY COALESCE(updated_at, last_polled_at, created_at) DESC, id DESC) AS rn
        FROM dbo.etl_ds_job_log
        WHERE pipeline_name IS NOT NULL
    )
    DELETE FROM d WHERE rn > 1;

    CREATE UNIQUE INDEX UX_etl_ds_job_log_run
        ON dbo.etl_ds_job_log (execution_id, pipeline_name, job_name)
        WHERE pipeline_name IS NOT NULL;
    PRINT '[OK] etl_ds_job_log: dedupe + UX_etl_ds_job_log_run criado';
END
ELSE
    PRINT '[SKIP] UX_etl_ds_job_log_run ja existe (ou tabela ausente)';
GO
