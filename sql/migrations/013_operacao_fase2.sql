-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 013 — Operação Fase 2
--   1. Runbook por pipeline (instruções de falha em markdown)
--   2. Alertas de SLA (dedup de notificações do sla_monitor)
--   3. Acknowledge de falha (operador assume o incidente)
-- ═══════════════════════════════════════════════════════════════════════════

-- 1. Runbook
IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
               WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_pipeline' AND COLUMN_NAME='runbook_md')
BEGIN
    ALTER TABLE dbo.etl_pipeline ADD runbook_md NVARCHAR(MAX) NULL;
END
GO

-- 2. Alertas de SLA
IF OBJECT_ID('dbo.etl_sla_alert', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_sla_alert (
        id           INT IDENTITY(1,1) PRIMARY KEY,
        execution_id VARCHAR(100) NOT NULL,
        pipeline     VARCHAR(200) NOT NULL,
        alert_type   VARCHAR(10)  NOT NULL,   -- RISK | BREACH
        sla_minutos  INT          NULL,
        elapsed_min  INT          NULL,
        alerted_at   DATETIME     NOT NULL DEFAULT GETDATE()
    );
    CREATE UNIQUE INDEX UX_etl_sla_alert ON dbo.etl_sla_alert (execution_id, pipeline, alert_type);
END
GO

-- 3. Acknowledge de falha
IF OBJECT_ID('dbo.etl_failure_ack', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_failure_ack (
        id           INT IDENTITY(1,1) PRIMARY KEY,
        execution_id VARCHAR(100)  NOT NULL,
        pipeline     VARCHAR(200)  NOT NULL,
        ack_by       VARCHAR(100)  NOT NULL,
        display_name NVARCHAR(200) NULL,
        ack_at       DATETIME      NOT NULL DEFAULT GETDATE(),
        note         NVARCHAR(500) NULL
    );
    CREATE UNIQUE INDEX UX_etl_failure_ack ON dbo.etl_failure_ack (execution_id, pipeline);
END
ELSE
BEGIN
    -- Adiciona display_name se já existia a tabela sem ela
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
                   WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_failure_ack' AND COLUMN_NAME='display_name')
        ALTER TABLE dbo.etl_failure_ack ADD display_name NVARCHAR(200) NULL;
END
GO
