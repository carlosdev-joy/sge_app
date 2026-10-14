-- F9A: fundação persistente. Sem produtor de clientes ou envio externo.
IF OBJECT_ID('dbo.etl_alert_event', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_alert_event (
        id UNIQUEIDENTIFIER NOT NULL PRIMARY KEY,
        event_key CHAR(64) COLLATE Latin1_General_100_BIN2 NOT NULL UNIQUE,
        policy_revision VARCHAR(101) COLLATE Latin1_General_100_BIN2 NOT NULL,
        pipeline_name NVARCHAR(200) NOT NULL,
        run_id NVARCHAR(250) NOT NULL,
        cycle_generation INT NOT NULL CHECK (cycle_generation > 0),
        event_type VARCHAR(16) NOT NULL CHECK (event_type IN ('success','warning','failure')),
        source NVARCHAR(100) NOT NULL,
        source_status VARCHAR(16) NOT NULL,
        source_at DATETIME2(6) NOT NULL,
        received_at DATETIME2(6) NOT NULL,
        dry_run BIT NOT NULL CHECK (dry_run = 1),
        created_at DATETIME2(6) NOT NULL DEFAULT SYSUTCDATETIME()
    );
END
GO
IF OBJECT_ID('dbo.etl_alert_intent', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_alert_intent (
        id UNIQUEIDENTIFIER NOT NULL PRIMARY KEY,
        event_id UNIQUEIDENTIFIER NOT NULL REFERENCES dbo.etl_alert_event(id),
        policy_revision VARCHAR(101) COLLATE Latin1_General_100_BIN2 NOT NULL,
        channel VARCHAR(16) COLLATE Latin1_General_100_BIN2 NOT NULL
            CHECK (channel IN ('email','teamsPersonal','teamsChannel')),
        destination_ref VARCHAR(180) COLLATE Latin1_General_100_BIN2 NOT NULL,
        delivery_key CHAR(64) COLLATE Latin1_General_100_BIN2 NOT NULL UNIQUE,
        state VARCHAR(16) NOT NULL DEFAULT 'Pending'
            CHECK (state IN ('Pending','Leased','Accepted','Failed','Unknown','DryRun')),
        attempt_count INT NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
        next_attempt_at DATETIME2(6) NOT NULL DEFAULT SYSUTCDATETIME(),
        lease_token UNIQUEIDENTIFIER NULL,
        lease_until DATETIME2(6) NULL,
        updated_at DATETIME2(6) NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT UQ_alert_intent_destination UNIQUE (event_id,policy_revision,channel,destination_ref)
    );
END
GO
IF OBJECT_ID('dbo.etl_alert_attempt', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_alert_attempt (
        id UNIQUEIDENTIFIER NOT NULL PRIMARY KEY,
        intent_id UNIQUEIDENTIFIER NOT NULL REFERENCES dbo.etl_alert_intent(id),
        sequence INT NOT NULL CHECK (sequence > 0),
        lease_token UNIQUEIDENTIFIER NOT NULL,
        started_at DATETIME2(6) NOT NULL DEFAULT SYSUTCDATETIME(),
        finished_at DATETIME2(6) NULL,
        outcome VARCHAR(16) NULL CHECK (outcome IN ('Accepted','Failed','Unknown','DryRun')),
        error_code VARCHAR(32) NULL,
        retry_after_seconds INT NULL CHECK (retry_after_seconds BETWEEN 0 AND 86400),
        CONSTRAINT UQ_alert_attempt_sequence UNIQUE (intent_id,sequence)
    );
END
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.etl_alert_intent') AND name='IX_alert_intent_queue')
    CREATE INDEX IX_alert_intent_queue ON dbo.etl_alert_intent(state,next_attempt_at,lease_until) INCLUDE (event_id,attempt_count);
GO
