-- Legado não é reenviado. Payload contém referência de destino, nunca webhook.
IF COL_LENGTH('dbo.etl_sla_alert', 'intent_json') IS NULL
BEGIN
    ALTER TABLE dbo.etl_sla_alert ADD intent_json NVARCHAR(MAX) NULL;
END
GO
IF COL_LENGTH('dbo.etl_sla_alert', 'delivery_state') IS NULL
BEGIN
    ALTER TABLE dbo.etl_sla_alert ADD delivery_state VARCHAR(16) NOT NULL
        CONSTRAINT DF_sla_delivery_state DEFAULT 'Legacy' WITH VALUES,
        claim_token UNIQUEIDENTIFIER NULL,
        lease_until DATETIME2(6) NULL;
END
GO
