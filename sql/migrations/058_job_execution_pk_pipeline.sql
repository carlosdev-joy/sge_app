-- 058_job_execution_pk_pipeline.sql
-- Fase 2 da migration 027 — elimina a colisão de execution_id entre pipelines.
--
-- execution_id = ts_nodash (timestamp lógico do run) COLIDE quando duas
-- pipelines agendadas no mesmo tick têm job homônimo: as SPs da 027 filtram
-- por pipeline no WHERE, "não acham" a linha da outra pipeline e INSEREM —
-- violação do PK antigo (execution_id, job_name, task_id), que derruba o run
-- da 2ª pipeline no log_start com card Teams "Job com falha: Não identificado".
--
-- O que faz (nesta ordem):
--   1. backfill de pipeline NULL (EXEC dinâmico — o shape do deploy_full não
--      tem a coluna e um UPDATE estático falharia em compile-time, Msg 207);
--   2. DROP dinâmico de TODOS os índices não-PK que referenciam a coluna
--      pipeline (chave OU INCLUDE — Msg 5074 bloqueia o ALTER com eles vivos)
--      + ALTER COLUMN pipeline NOT NULL;
--   3. DROP do índice único duplicado ux_etl_execution;
--   4. PK recriado ATÔMICO como (execution_id, pipeline, job_name, task_id) —
--      com pré-condição (pipeline NOT NULL) e auto-recuperação (tabela sem PK
--      entra no bloco e ganha o PK);
--   5. sp_etl_ds_job_log_upsert recriada com QUOTED_IDENTIFIER ON se preciso
--      (SP criada com QI OFF falharia em TODO upsert após o índice filtrado);
--   6. etl_ds_job_log: dedupe + índice ÚNICO filtrado;
--   7. índices de consulta recriados com as definições REAIS de produção
--      (INCLUDEs do script 20260531_indices_etl_job_execution_v1);
--   8. sp_etl_job_execution_log v2: reprocesso (log_start em linha existente)
--      REINICIA o relógio (start_time novo, end_time/duration NULL) — antes o
--      rerun herdava start antigo e a duração saía negativa/errada.
--
-- OPERAÇÃO (janela): a tabela é quente (log_start de toda task + monitor).
-- Aplicar SEM execuções em andamento — pausar scheduler/monitor; o rebuild do
-- PK clusterizado pode demorar em tabela grande. Se aplicar via sqlcmd, use
-- SEMPRE 'sqlcmd -b -I' (aborta no 1º erro; QUOTED_IDENTIFIER ON).
--
-- Defensiva ao shape alternativo do deploy_full.sql (id IDENTITY/pipeline_name):
-- todos os blocos skipam com [SKIP]. Idempotente — seguro rodar mais de uma vez.

-- Sessão: QI ON (exigido por índice filtrado) e XACT_ABORT ON (erro em bloco
-- com transação aberta faz rollback completo — nada fica pela metade).
SET QUOTED_IDENTIFIER ON;
SET XACT_ABORT ON;
GO

-- 1) Backfill: linha histórica sem pipeline não pode entrar no PK.
--    EXEC dinâmico: no shape do deploy_full a coluna não existe e o UPDATE
--    estático falharia na compilação do batch ANTES do IF (Msg 207).
IF COL_LENGTH('dbo.etl_job_execution', 'pipeline') IS NOT NULL
   AND COL_LENGTH('dbo.etl_job_execution', 'task_id') IS NOT NULL
BEGIN
    EXEC('UPDATE dbo.etl_job_execution SET pipeline = ''(desconhecido)'' WHERE pipeline IS NULL;');
    PRINT '[OK] backfill de pipeline NULL concluido';
END
ELSE
    PRINT '[SKIP] etl_job_execution sem o shape esperado (pipeline/task_id) — nada a fazer';
GO

-- 2) NOT NULL. Antes, dropa DINAMICAMENTE todo índice não-PK que referencia a
--    coluna pipeline (chave OU INCLUDE) — Msg 5074 impede o ALTER com eles
--    vivos, e produção tem um 3º índice (project_status_start, pipeline no
--    INCLUDE) que só existe no script avulso 20260531. Recriados no passo 7.
IF COL_LENGTH('dbo.etl_job_execution', 'pipeline') IS NOT NULL
   AND COL_LENGTH('dbo.etl_job_execution', 'task_id') IS NOT NULL
   AND EXISTS (SELECT 1 FROM sys.columns
               WHERE object_id = OBJECT_ID('dbo.etl_job_execution')
                 AND name = 'pipeline' AND is_nullable = 1)
BEGIN
    DECLARE @drops NVARCHAR(MAX) = N'';
    SELECT @drops = @drops + N'DROP INDEX ' + QUOTENAME(i.name)
                  + N' ON dbo.etl_job_execution; '
    FROM sys.indexes i
    WHERE i.object_id = OBJECT_ID('dbo.etl_job_execution')
      AND i.is_primary_key = 0 AND i.type > 0
      AND EXISTS (SELECT 1
                  FROM sys.index_columns ic
                  JOIN sys.columns c ON c.object_id = ic.object_id
                                    AND c.column_id = ic.column_id
                  WHERE ic.object_id = i.object_id AND ic.index_id = i.index_id
                    AND c.name = 'pipeline');
    IF @drops <> N''
    BEGIN
        PRINT '[OK] dropando indices dependentes de pipeline: ' + @drops;
        EXEC sp_executesql @drops;
    END
    ALTER TABLE dbo.etl_job_execution ALTER COLUMN pipeline VARCHAR(200) NOT NULL;
    PRINT '[OK] etl_job_execution.pipeline agora NOT NULL';
END
ELSE
    PRINT '[SKIP] pipeline ja e NOT NULL (ou shape divergente)';
GO

-- 3) Índice único duplicado do PK antigo — manteria a colisão mesmo com PK novo.
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

-- 4) PK com pipeline — ATÔMICO (DROP+ADD na mesma transação; XACT_ABORT ON na
--    sessão) e com auto-recuperação: tabela SEM PK nenhum também entra no
--    bloco e ganha o PK. Pré-condição: pipeline precisa estar NOT NULL (senão
--    o ADD falharia DEPOIS do DROP — era o caminho que deixava a tabela heap).
IF COL_LENGTH('dbo.etl_job_execution', 'pipeline') IS NOT NULL
   AND COL_LENGTH('dbo.etl_job_execution', 'task_id') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1
       FROM sys.index_columns ic
       JOIN sys.indexes i ON i.object_id = ic.object_id AND i.index_id = ic.index_id
       JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
       WHERE i.object_id = OBJECT_ID('dbo.etl_job_execution')
         AND i.is_primary_key = 1 AND c.name = 'pipeline')
BEGIN
    IF EXISTS (SELECT 1 FROM sys.columns
               WHERE object_id = OBJECT_ID('dbo.etl_job_execution')
                 AND name = 'pipeline' AND is_nullable = 1)
        RAISERROR('058: pipeline ainda anulavel (bloco 2 nao aplicou) — PK mantido; corrija antes de reaplicar.', 16, 1);
    ELSE
    BEGIN
        BEGIN TRAN;
        IF EXISTS (SELECT 1 FROM sys.key_constraints
                   WHERE parent_object_id = OBJECT_ID('dbo.etl_job_execution')
                     AND type = 'PK')
            ALTER TABLE dbo.etl_job_execution DROP CONSTRAINT PK_etl_job_execution;
        ALTER TABLE dbo.etl_job_execution ADD CONSTRAINT PK_etl_job_execution
            PRIMARY KEY CLUSTERED (execution_id, pipeline, job_name, task_id);
        COMMIT;
        PRINT '[OK] PK recriado como (execution_id, pipeline, job_name, task_id)';
    END
END
ELSE
    PRINT '[SKIP] PK ja contem pipeline (ou shape divergente)';
GO

-- 5) Índice FILTRADO exige QUOTED_IDENTIFIER ON também em quem ESCREVE na
--    tabela. Se a sp_etl_ds_job_log_upsert foi criada numa sessão com QI OFF
--    (sqlcmd sem -I), TODO upsert falharia após o passo 6 — apagão da
--    telemetria DS. Recria a SP com a MESMA definição, nesta sessão (QI ON).
IF EXISTS (SELECT 1 FROM sys.sql_modules m
           WHERE m.object_id = OBJECT_ID('dbo.sp_etl_ds_job_log_upsert')
             AND m.uses_quoted_identifier = 0)
BEGIN
    DECLARE @def NVARCHAR(MAX) =
        (SELECT m.definition FROM sys.sql_modules m
         WHERE m.object_id = OBJECT_ID('dbo.sp_etl_ds_job_log_upsert'));
    BEGIN TRAN;
    DROP PROCEDURE dbo.sp_etl_ds_job_log_upsert;
    EXEC sp_executesql @def;
    COMMIT;
    PRINT '[OK] sp_etl_ds_job_log_upsert recriada com QUOTED_IDENTIFIER ON';
END
ELSE
    PRINT '[SKIP] sp_etl_ds_job_log_upsert ok (ou ausente)';
GO

-- 6) etl_ds_job_log: dedupe + unicidade natural (filtrada p/ legado com NULL).
--    Transação única: o DELETE de dedupe não commita sem o índice nascer.
IF OBJECT_ID('dbo.etl_ds_job_log', 'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.indexes
                   WHERE object_id = OBJECT_ID('dbo.etl_ds_job_log')
                     AND name = 'UX_etl_ds_job_log_run')
BEGIN
    BEGIN TRAN;
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
    COMMIT;
    PRINT '[OK] etl_ds_job_log: dedupe + UX_etl_ds_job_log_run criado';
END
ELSE
    PRINT '[SKIP] UX_etl_ds_job_log_run ja existe (ou tabela ausente)';
GO

-- 7) Recria os índices de consulta com as definições REAIS de produção
--    (script 20260531 — com INCLUDEs; a forma achatada do schema_prod_dev é
--    um snapshot desatualizado). Idempotente por nome.
IF COL_LENGTH('dbo.etl_job_execution', 'pipeline') IS NOT NULL
   AND COL_LENGTH('dbo.etl_job_execution', 'task_id') IS NOT NULL
BEGIN
    IF NOT EXISTS (SELECT 1 FROM sys.indexes
                   WHERE object_id = OBJECT_ID('dbo.etl_job_execution')
                     AND name = 'IX_etl_job_execution_pipeline_status_start')
    BEGIN
        CREATE NONCLUSTERED INDEX [IX_etl_job_execution_pipeline_status_start]
        ON [dbo].[etl_job_execution] ([pipeline], [status], [start_time])
        INCLUDE ([execution_id], [job_name], [end_time], [duration_seconds], [project], [task_id]);
        PRINT '[OK] IX_etl_job_execution_pipeline_status_start recriado';
    END
    IF NOT EXISTS (SELECT 1 FROM sys.indexes
                   WHERE object_id = OBJECT_ID('dbo.etl_job_execution')
                     AND name = 'IX_etl_job_execution_project_status_start')
    BEGIN
        CREATE NONCLUSTERED INDEX [IX_etl_job_execution_project_status_start]
        ON [dbo].[etl_job_execution] ([project], [status], [start_time])
        INCLUDE ([execution_id], [pipeline], [job_name], [end_time], [duration_seconds], [task_id]);
        PRINT '[OK] IX_etl_job_execution_project_status_start recriado';
    END
    IF NOT EXISTS (SELECT 1 FROM sys.indexes
                   WHERE object_id = OBJECT_ID('dbo.etl_job_execution')
                     AND name = 'IX_etl_job_execution_execution_id_pipeline')
    BEGIN
        CREATE NONCLUSTERED INDEX [IX_etl_job_execution_execution_id_pipeline]
        ON [dbo].[etl_job_execution] ([execution_id], [pipeline])
        INCLUDE ([status], [start_time], [end_time], [duration_seconds]);
        PRINT '[OK] IX_etl_job_execution_execution_id_pipeline recriado';
    END
END
GO

-- 8) sp_etl_job_execution_log v2 — reprocesso reinicia o relógio da linha.
--    Antes, o ramo UPDATE nunca tocava start_time nem limpava end_time: um
--    rerun (e o rerun após SKIPPED do flow_close) herdava o start antigo e a
--    duração saía errada. @status='RUNNING' em linha existente = log_start de
--    reprocesso → zera fim/duração e assume o novo início/host.
IF COL_LENGTH('dbo.etl_job_execution', 'pipeline') IS NOT NULL
   AND COL_LENGTH('dbo.etl_job_execution', 'task_id') IS NOT NULL
BEGIN
    EXEC('
CREATE OR ALTER PROCEDURE [dbo].[sp_etl_job_execution_log]
(
 @execution_id       VARCHAR(50),
 @project            VARCHAR(100),
 @job_name           VARCHAR(200),
 @pipeline           VARCHAR(200),
 @host               VARCHAR(200),
 @start_time         VARCHAR(30),
 @end_time           VARCHAR(30),
 @duration_seconds   INT,
 @status             VARCHAR(20),
 @log_file           VARCHAR(500),
 @task_id            VARCHAR(200)
)
AS
BEGIN
SET NOCOUNT ON;

DECLARE @start_dt DATETIME2
DECLARE @end_dt   DATETIME2

SET @start_dt = CASE WHEN @start_time IS NULL OR @start_time = '''' THEN NULL
                     ELSE CAST(@start_time AS DATETIME2) END
SET @end_dt   = CASE WHEN @end_time IS NULL OR @end_time = ''''
                       OR @end_time = ''1900-01-01 00:00:00'' THEN NULL
                     ELSE CAST(@end_time AS DATETIME2) END

IF NOT EXISTS (
    SELECT 1 FROM dbo.etl_job_execution
    WHERE execution_id = @execution_id AND pipeline = @pipeline
      AND job_name = @job_name AND task_id = @task_id
)
BEGIN
    INSERT INTO dbo.etl_job_execution
        (execution_id, project, job_name, pipeline, host, start_time, end_time,
         duration_seconds, status, log_file, task_id, created_at, updated_at)
    VALUES
        (@execution_id, @project, @job_name, @pipeline, @host, @start_dt, @end_dt,
         @duration_seconds, @status, @log_file, @task_id, GETDATE(), GETDATE())
END
ELSE
BEGIN
    UPDATE dbo.etl_job_execution
    SET
        -- Reprocesso (log_start em linha existente): reinicia o relógio.
        start_time = CASE WHEN @status = ''RUNNING'' AND @start_dt IS NOT NULL
                          THEN @start_dt ELSE start_time END,
        host       = CASE WHEN @status = ''RUNNING'' AND @host IS NOT NULL
                          THEN @host ELSE host END,
        end_time = CASE WHEN @status = ''RUNNING'' THEN NULL
                        ELSE COALESCE(@end_dt, end_time) END,
        duration_seconds = CASE
            WHEN @status = ''RUNNING'' THEN NULL
            WHEN @end_dt IS NOT NULL THEN DATEDIFF(SECOND, start_time, @end_dt)
            ELSE duration_seconds END,
        status = @status,
        log_file = @log_file,
        updated_at = GETDATE()
    WHERE execution_id = @execution_id AND pipeline = @pipeline
      AND job_name = @job_name AND task_id = @task_id
END
END
');
    PRINT '[OK] sp_etl_job_execution_log v2 (reprocesso reinicia o relogio)';
END
ELSE
    PRINT '[SKIP] shape divergente — SP mantida';
GO
