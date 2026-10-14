-- Referência pessoal aprovada; conteúdo cifrado, sem endpoint de envio.
-- Idempotente — seguro para rodar mais de uma vez.
IF OBJECT_ID('dbo.etl_teams_personal_binding', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_teams_personal_binding (
        target_fingerprint CHAR(64) COLLATE Latin1_General_100_BIN2 NOT NULL PRIMARY KEY,
        reference_enc VARCHAR(MAX) NOT NULL,
        updated_by NVARCHAR(100) NOT NULL,
        updated_at DATETIME2(6) NOT NULL DEFAULT SYSUTCDATETIME()
    );
END
GO
