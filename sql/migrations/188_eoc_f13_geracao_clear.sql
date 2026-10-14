-- F13: geração durável. Não ativa produtor ou envio; não importa runs antigos.
IF OBJECT_ID('dbo.etl_alert_cycle', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_alert_cycle (
        run_key CHAR(64) COLLATE Latin1_General_100_BIN2 NOT NULL PRIMARY KEY,
        pipeline_name NVARCHAR(200) COLLATE Latin1_General_100_BIN2 NOT NULL,
        run_id NVARCHAR(250) COLLATE Latin1_General_100_BIN2 NOT NULL,
        generation INT NOT NULL DEFAULT 1 CHECK (generation > 0),
        pending_clear UNIQUEIDENTIFIER NULL,
        created_at DATETIME2(6) NOT NULL DEFAULT SYSUTCDATETIME(),
        updated_at DATETIME2(6) NOT NULL DEFAULT SYSUTCDATETIME()
    );
END
GO
IF OBJECT_ID('dbo.etl_alert_run_snapshot', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_alert_run_snapshot (
        run_key CHAR(64) COLLATE Latin1_General_100_BIN2 NOT NULL PRIMARY KEY
            REFERENCES dbo.etl_alert_cycle(run_key),
        snapshot_json NVARCHAR(MAX) NOT NULL CHECK (ISJSON(snapshot_json)=1),
        snapshot_hash CHAR(64) COLLATE Latin1_General_100_BIN2 NOT NULL,
        created_at DATETIME2(6) NOT NULL DEFAULT SYSUTCDATETIME()
    );
END
GO
IF OBJECT_ID('dbo.etl_alert_clear', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_alert_clear (
        id UNIQUEIDENTIFIER NOT NULL PRIMARY KEY,
        run_key CHAR(64) COLLATE Latin1_General_100_BIN2 NOT NULL
            REFERENCES dbo.etl_alert_cycle(run_key),
        base_generation INT NOT NULL CHECK (base_generation > 0),
        state VARCHAR(16) NOT NULL DEFAULT 'Pending'
            CHECK (state IN ('Pending','Confirmed','Rejected','Unknown')),
        created_at DATETIME2(6) NOT NULL DEFAULT SYSUTCDATETIME(),
        updated_at DATETIME2(6) NOT NULL DEFAULT SYSUTCDATETIME()
    );
END
GO
