-- Migration 049: contagem de linhas do job + nó de notificação (Teams)
-- (A) rows_out em etl_ds_job_log: linhas de SAÍDA gravadas pelo job DataStage,
--     base da condição de decisão 'linhas_job' (lê desta tabela por execução).
-- (B) notify_json em etl_pipeline_job: config do nó de notificação no fluxo.
-- (C) etl_msg_grupo (canal/webhook do Teams) + etl_msg_template (mensagem editável
--     com placeholders {pipeline} {job} {linhas} {status} {data}).
-- Idempotente; blocos terminam com GO. Tudo degrada se a tabela não existir.

-- ── (A) rows_out em etl_ds_job_log ────────────────────────────────────────────
IF COL_LENGTH('dbo.etl_ds_job_log', 'rows_out') IS NULL
    ALTER TABLE dbo.etl_ds_job_log ADD rows_out INT NULL;
GO

-- Upsert = versão 027 (escopo por pipeline_name + ds_start/end_time) + @rows_out.
-- IMPORTANTE: superset da 027 — NÃO dropar parâmetros/colunas que ela já tratava.
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
    @poll_snapshot  NVARCHAR(MAX),  -- JSON de um snapshot a anexar
    @ds_start_time  VARCHAR(50)  = NULL,
    @ds_end_time    DATETIME     = NULL,
    @rows_out       INT          = NULL  -- linhas de saída (opcional; default preserva)
AS
BEGIN
    SET NOCOUNT ON;

    IF EXISTS (
        SELECT 1 FROM dbo.etl_ds_job_log
        WHERE execution_id = @execution_id AND pipeline_name = @pipeline_name AND job_name = @job_name
    )
    BEGIN
        UPDATE dbo.etl_ds_job_log
        SET
            status          = @status,
            status_code     = @status_code,
            wave_number     = COALESCE(@wave_number, wave_number),
            pid             = COALESCE(@pid, pid),
            child_jobs      = CASE WHEN @child_jobs     IS NOT NULL AND @child_jobs     <> '' THEN @child_jobs     ELSE child_jobs     END,
            log_summary     = CASE WHEN @log_summary    IS NOT NULL AND @log_summary    <> '' THEN @log_summary    ELSE log_summary    END,
            ds_start_time   = CASE WHEN @ds_start_time  IS NOT NULL                           THEN @ds_start_time  ELSE ds_start_time  END,
            ds_end_time     = CASE WHEN @ds_end_time     IS NOT NULL                           THEN @ds_end_time    ELSE ds_end_time    END,
            rows_out        = COALESCE(@rows_out, rows_out),
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
        WHERE execution_id = @execution_id AND pipeline_name = @pipeline_name AND job_name = @job_name;
    END
    ELSE
    BEGIN
        INSERT INTO dbo.etl_ds_job_log
            (execution_id, pipeline_name, job_name, project, wave_number, pid,
             status, status_code, child_jobs, log_summary,
             ds_start_time, ds_end_time, rows_out,
             poll_snapshots, last_polled_at)
        VALUES
            (@execution_id, @pipeline_name, @job_name, @project, @wave_number, @pid,
             @status, @status_code, @child_jobs, @log_summary,
             @ds_start_time, @ds_end_time, @rows_out,
             CASE WHEN @poll_snapshot IS NOT NULL THEN '[' + @poll_snapshot + ']' ELSE NULL END,
             GETDATE());
    END
END
GO

-- ── (B) config do nó de notificação por job ───────────────────────────────────
-- JSON: {"grupo_id": N, "template_id": N, "mensagem": "..."} — análogo ao
-- condition_json da decisão, mas para o tipo 'notificacao'.
IF COL_LENGTH('dbo.etl_pipeline_job', 'notify_json') IS NULL
    ALTER TABLE dbo.etl_pipeline_job ADD notify_json NVARCHAR(MAX) NULL;
GO

-- ── (C) Grupos = canais/webhooks do Teams ─────────────────────────────────────
IF OBJECT_ID('dbo.etl_msg_grupo', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_msg_grupo (
        id          INT IDENTITY(1,1) PRIMARY KEY,
        nome        VARCHAR(120)   NOT NULL,
        descricao   VARCHAR(400)   NULL,
        webhook_url NVARCHAR(1000) NULL,   -- webhook do canal Teams (Power Automate/incoming)
        ativo       BIT            NOT NULL DEFAULT 1,
        created_at  DATETIME       NOT NULL DEFAULT GETDATE(),
        updated_at  DATETIME       NOT NULL DEFAULT GETDATE()
    );
    CREATE UNIQUE INDEX ux_msg_grupo_nome ON dbo.etl_msg_grupo (nome);
END
GO

-- ── (C) Templates = mensagens editáveis com placeholders ──────────────────────
IF OBJECT_ID('dbo.etl_msg_template', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_msg_template (
        id          INT IDENTITY(1,1) PRIMARY KEY,
        grupo_id    INT            NULL,     -- canal sugerido (ref. lógica a etl_msg_grupo.id)
        nome        VARCHAR(120)   NOT NULL,
        titulo      VARCHAR(200)   NULL,
        corpo       NVARCHAR(MAX)  NOT NULL, -- {pipeline} {job} {linhas} {status} {data}
        ativo       BIT            NOT NULL DEFAULT 1,
        created_at  DATETIME       NOT NULL DEFAULT GETDATE(),
        updated_at  DATETIME       NOT NULL DEFAULT GETDATE()
    );
    CREATE INDEX ix_msg_template_grupo ON dbo.etl_msg_template (grupo_id);
END
GO
