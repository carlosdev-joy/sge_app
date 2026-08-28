-- Migration 010: tabela de log detalhado DataStage
-- Persiste wave_number, jobs filhos e logsum do DataStageOperator
--
-- ⚠️ GUARDAS ACRESCENTADAS EM 2026-08-28. Esta era a ÚNICA das 100 migrations
-- do repo cuja segunda execução falhava ("There is already an object named
-- 'etl_ds_job_log'"). Na prática ela nunca reexecutava — o runner consulta
-- `dbo.etl_schema_version` e pula o que já foi aplicado —, mas essa proteção é
-- de FORA: ela não cobre um banco restaurado de backup parcial, uma migration
-- aplicada à mão sem registrar, nem a retomada de um deploy interrompido no
-- meio. Migration que só pode rodar uma vez transforma qualquer um desses
-- casos numa parada com erro.
--
-- O comportamento em banco NOVO é idêntico ao de antes: a tabela não existe, a
-- guarda passa, tudo é criado igual.

IF OBJECT_ID('dbo.etl_ds_job_log', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_ds_job_log (
        id               INT IDENTITY(1,1) PRIMARY KEY,
        execution_id     VARCHAR(50)       NOT NULL,
        pipeline_name    VARCHAR(200)      NOT NULL,
        job_name         VARCHAR(200)      NOT NULL,
        project          VARCHAR(100)      NOT NULL,
        wave_number      INT               NULL,
        pid              VARCHAR(20)       NULL,
        status           VARCHAR(50)       NOT NULL,
        status_code      INT               NULL,
        child_jobs       NVARCHAR(MAX)     NULL,  -- JSON: [{name, status, status_code}]
        log_summary      NVARCHAR(MAX)     NULL,
        poll_snapshots   NVARCHAR(MAX)     NULL,  -- JSON: [{ts, status, status_code}]
        last_polled_at   DATETIME          NULL,
        created_at       DATETIME          NOT NULL DEFAULT GETDATE(),
        updated_at       DATETIME          NOT NULL DEFAULT GETDATE()
    );
    PRINT '[OK] Tabela etl_ds_job_log criada';
END
ELSE
    PRINT '[SKIP] etl_ds_job_log ja existe';

-- Os índices em guarda PRÓPRIA, e não dentro da guarda da tabela: um banco que
-- tenha a tabela sem os índices (criada à mão, ou por um deploy que morreu
-- entre o CREATE TABLE e o CREATE INDEX) fica com eles faltando para sempre se
-- a única guarda for a da tabela.
IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE name = 'ix_ds_job_log_exec'
                 AND object_id = OBJECT_ID('dbo.etl_ds_job_log'))
    CREATE INDEX ix_ds_job_log_exec  ON dbo.etl_ds_job_log (execution_id);

IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE name = 'ix_ds_job_log_job'
                 AND object_id = OBJECT_ID('dbo.etl_ds_job_log'))
    CREATE INDEX ix_ds_job_log_job   ON dbo.etl_ds_job_log (job_name, created_at DESC);

GO

-- Upsert usado pelo DataStageOperator e monitor DAG
CREATE OR ALTER PROCEDURE dbo.sp_etl_ds_job_log_upsert
    @execution_id   VARCHAR(50),
    @pipeline_name  VARCHAR(200),
    @job_name       VARCHAR(200),
    @project        VARCHAR(100),
    @wave_number    INT,
    @pid            VARCHAR(20),
    @status         VARCHAR(50),
    @status_code    INT,
    @child_jobs     NVARCHAR(MAX),
    @log_summary    NVARCHAR(MAX),
    @poll_snapshot  NVARCHAR(MAX)   -- JSON de um snapshot a anexar
AS
BEGIN
    SET NOCOUNT ON;

    IF EXISTS (
        SELECT 1 FROM dbo.etl_ds_job_log
        WHERE execution_id = @execution_id AND job_name = @job_name
    )
    BEGIN
        UPDATE dbo.etl_ds_job_log
        SET
            status          = @status,
            status_code     = @status_code,
            wave_number     = COALESCE(@wave_number, wave_number),
            pid             = COALESCE(@pid, pid),
            child_jobs      = CASE WHEN @child_jobs IS NOT NULL AND @child_jobs <> '' THEN @child_jobs ELSE child_jobs END,
            log_summary     = CASE WHEN @log_summary IS NOT NULL AND @log_summary <> '' THEN @log_summary ELSE log_summary END,
            poll_snapshots  = CASE
                                WHEN @poll_snapshot IS NOT NULL AND @poll_snapshot <> ''
                                THEN COALESCE(
                                    LEFT(poll_snapshots, LEN(poll_snapshots) - 1) + ',' + @poll_snapshot + ']',
                                    '[' + @poll_snapshot + ']'
                                )
                                ELSE poll_snapshots
                              END,
            last_polled_at  = GETDATE(),
            updated_at      = GETDATE()
        WHERE execution_id = @execution_id AND job_name = @job_name;
    END
    ELSE
    BEGIN
        INSERT INTO dbo.etl_ds_job_log
            (execution_id, pipeline_name, job_name, project, wave_number, pid,
             status, status_code, child_jobs, log_summary, poll_snapshots, last_polled_at)
        VALUES
            (@execution_id, @pipeline_name, @job_name, @project, @wave_number, @pid,
             @status, @status_code, @child_jobs, @log_summary,
             CASE WHEN @poll_snapshot IS NOT NULL THEN '[' + @poll_snapshot + ']' ELSE NULL END,
             GETDATE());
    END
END
GO
