-- Reenvio explícito e auditado; não importa nem reenvia registros Legacy.
IF COL_LENGTH('dbo.etl_sla_alert','attempt_count') IS NULL
BEGIN
    ALTER TABLE dbo.etl_sla_alert ADD attempt_count INT NOT NULL
        CONSTRAINT DF_sla_attempt_count DEFAULT 0 WITH VALUES;
END
GO
IF OBJECT_ID('dbo.etl_alert_recovery','U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_alert_recovery (
        request_id UNIQUEIDENTIFIER NOT NULL PRIMARY KEY,
        intent_id UNIQUEIDENTIFIER NOT NULL REFERENCES dbo.etl_alert_intent(id),
        previous_state VARCHAR(16) NOT NULL,
        expected_sequence INT NOT NULL,
        actor NVARCHAR(100) NOT NULL,
        reason VARCHAR(32) NOT NULL,
        duplicate_risk_ack BIT NOT NULL,
        created_at DATETIME2(6) NOT NULL DEFAULT SYSUTCDATETIME()
    );
END
GO
IF OBJECT_ID('dbo.etl_sla_attempt','U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_sla_attempt (
        alert_id INT NOT NULL REFERENCES dbo.etl_sla_alert(id),
        sequence INT NOT NULL CHECK(sequence>0),
        claim_token UNIQUEIDENTIFIER NOT NULL UNIQUE,
        started_at DATETIME2(6) NOT NULL DEFAULT SYSUTCDATETIME(),
        finished_at DATETIME2(6) NULL,
        outcome VARCHAR(16) NULL CHECK(outcome IN ('Accepted','Failed','Unknown')),
        CONSTRAINT PK_sla_attempt PRIMARY KEY(alert_id,sequence)
    );
END
GO
IF OBJECT_ID('dbo.etl_sla_recovery','U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_sla_recovery (
        request_id UNIQUEIDENTIFIER NOT NULL PRIMARY KEY,
        alert_id INT NOT NULL,
        previous_state VARCHAR(16) NOT NULL,
        actor NVARCHAR(100) NOT NULL,
        reason VARCHAR(32) NOT NULL,
        duplicate_risk_ack BIT NOT NULL,
        created_at DATETIME2(6) NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_sla_recovery_alert FOREIGN KEY(alert_id) REFERENCES dbo.etl_sla_alert(id)
    );
END
GO
