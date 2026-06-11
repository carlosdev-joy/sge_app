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

-- 4. Webhook do Teams configurável pelo Admin (Admin > Configurações)
--    URLs do Power Automate podem passar de 500 chars — alarga a coluna.
IF EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
           WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_app_config'
             AND COLUMN_NAME='config_value' AND CHARACTER_MAXIMUM_LENGTH < 1000)
BEGIN
    ALTER TABLE dbo.etl_app_config ALTER COLUMN config_value VARCHAR(1000) NOT NULL;
END
GO

IF NOT EXISTS (SELECT 1 FROM dbo.etl_app_config WHERE config_key = 'teams_webhook_url')
BEGIN
    INSERT INTO dbo.etl_app_config (config_key, config_value, descricao)
    VALUES ('teams_webhook_url', '',
            'URL do webhook do Teams usada pela API (assumir falha). Cole aqui a mesma URL da Variable TEAMS_WEBHOOK_URL_CVP do Airflow.');
END
GO
