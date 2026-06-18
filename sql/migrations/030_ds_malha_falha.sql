-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 030 — Registro de falhas detectadas na varredura da malha
--   Jobs ABORTED pegos pelo dsjob -jobinfo (etl_ds_malha_status) — falhas que a
--   SEQ não tratou. Append-only, dedup por (project, job_name, wave_number).
--   Base de DOIS controles:
--     1. alerta (Teams) idempotente — alerta cada run abortado uma única vez;
--     2. integração com a Gestão de Falhas (UNION em /execucoes/falhas) com
--        ack/resolução/SNOW reaproveitados via etl_failure_ack (execution_id).
--   APARTADO: não toca etl_job_execution (não polui KPI de pipeline nem o gantt).
-- ═══════════════════════════════════════════════════════════════════════════

IF OBJECT_ID('dbo.etl_ds_malha_falha', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_ds_malha_falha (
        id              INT IDENTITY(1,1) PRIMARY KEY,
        execution_id    VARCHAR(100)  NOT NULL,   -- sintético: 'malha:' + hash(project|job|wave)
        project         VARCHAR(200)  NOT NULL,
        pipeline        VARCHAR(200)  NOT NULL,    -- = project (chave do ack/resolve em etl_failure_ack)
        job_name        VARCHAR(300)  NOT NULL,
        wave_number     INT           NULL,        -- identidade do run (dedup do alerta)
        status_code     INT           NULL,        -- 3 = ABORTED
        status_label    VARCHAR(30)   NULL,
        info            NVARCHAR(500) NULL,         -- linha "Job Status" bruta
        started_at      DATETIME2(7)  NULL,         -- "Job Start Time" do dsjob (quando parseável)
        elapsed_seconds INT           NULL,         -- tempo gasto, se o dsjob informar
        detected_at     DATETIME2(7)  NOT NULL DEFAULT SYSDATETIME(),
        alerted_at      DATETIME2(7)  NULL          -- quando o Teams foi notificado
    );
    -- Dedup: um registro por run (project, job, wave). NULL de wave conta como -1.
    CREATE UNIQUE INDEX UX_etl_ds_malha_falha
        ON dbo.etl_ds_malha_falha (project, job_name, wave_number);
    CREATE INDEX IX_etl_ds_malha_falha_detected
        ON dbo.etl_ds_malha_falha (detected_at);
    CREATE INDEX IX_etl_ds_malha_falha_exec
        ON dbo.etl_ds_malha_falha (execution_id, pipeline);
END
GO
