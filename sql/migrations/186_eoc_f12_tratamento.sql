-- F12: adapter do acknowledge existente e trilha independente do processamento.
IF OBJECT_ID('dbo.etl_failure_ack','U') IS NOT NULL
BEGIN
    IF COL_LENGTH('dbo.etl_failure_ack','priority') IS NULL
        ALTER TABLE dbo.etl_failure_ack ADD priority VARCHAR(10) NOT NULL
            CONSTRAINT DF_failure_ack_priority DEFAULT 'normal';
    IF COL_LENGTH('dbo.etl_failure_ack','treatment_version') IS NULL
        ALTER TABLE dbo.etl_failure_ack ADD treatment_version ROWVERSION;
    IF COL_LENGTH('dbo.etl_failure_ack','resolved_by') IS NULL
        ALTER TABLE dbo.etl_failure_ack ADD resolved_by NVARCHAR(64) NULL;
    IF COL_LENGTH('dbo.etl_failure_ack','resolved_display_name') IS NULL
        ALTER TABLE dbo.etl_failure_ack ADD resolved_display_name NVARCHAR(200) NULL;
    IF COL_LENGTH('dbo.etl_failure_ack','resolved_at') IS NULL
        ALTER TABLE dbo.etl_failure_ack ADD resolved_at DATETIME NULL;
    IF COL_LENGTH('dbo.etl_failure_ack','resolution_note') IS NULL
        ALTER TABLE dbo.etl_failure_ack ADD resolution_note NVARCHAR(500) NULL;
    IF COL_LENGTH('dbo.etl_failure_ack','snow_ticket') IS NULL
        ALTER TABLE dbo.etl_failure_ack ADD snow_ticket NVARCHAR(64) NULL;
END
GO

IF COL_LENGTH('dbo.etl_failure_ack','resolved_display_name') < 400
    ALTER TABLE dbo.etl_failure_ack ALTER COLUMN resolved_display_name NVARCHAR(200) NULL;
GO

-- Auditoria do adapter, sem segunda fonte de incidentes. Sem FK: desfazer ack
-- preserva a trilha, sempre na chave original, sem inventar geração histórica.
IF OBJECT_ID('dbo.etl_failure_ack_history','U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_failure_ack_history (
        id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        execution_id VARCHAR(100) NOT NULL,
        pipeline VARCHAR(200) NOT NULL,
        action VARCHAR(20) NOT NULL,
        actor NVARCHAR(100) NOT NULL,
        display_name NVARCHAR(200) NULL,
        created_at DATETIME2 NOT NULL CONSTRAINT DF_failure_history_at DEFAULT SYSUTCDATETIME(),
        note NVARCHAR(500) NULL,
        snow_ticket NVARCHAR(64) NULL,
        priority VARCHAR(10) NULL
        , previous_version BINARY(8) NULL
    );
    CREATE INDEX IX_failure_history_identity ON dbo.etl_failure_ack_history(execution_id,pipeline,id);
    -- Fotografia do registro legado, não eventos inventados nem retarget.
    IF OBJECT_ID('dbo.etl_failure_ack','U') IS NOT NULL
        INSERT dbo.etl_failure_ack_history(execution_id,pipeline,action,actor,display_name,note,priority)
        SELECT execution_id,pipeline,'legacy_snapshot',ack_by,display_name,note,priority
        FROM dbo.etl_failure_ack;
END
GO
