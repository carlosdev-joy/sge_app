-- F2b: vínculos e configuração original por corrida, antes de ativar consumidores.
IF COL_LENGTH('dbo.etl_pipeline_param', 'param_destino') IS NULL
    THROW 50130, 'Aplique a migration 129 antes da 130.', 1;
GO
IF COL_LENGTH('dbo.etl_pipeline_job', 'param_vinculos_json') IS NULL
    ALTER TABLE dbo.etl_pipeline_job ADD param_vinculos_json NVARCHAR(MAX) NULL;
GO
IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name='CK_etl_pipeline_job_param_vinculos')
    ALTER TABLE dbo.etl_pipeline_job ADD CONSTRAINT CK_etl_pipeline_job_param_vinculos
    CHECK (param_vinculos_json IS NULL OR ISJSON(param_vinculos_json)=1);
GO
IF OBJECT_ID('dbo.etl_parametro_snapshot', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_parametro_snapshot (
        pipeline_name NVARCHAR(200) COLLATE Latin1_General_BIN2 NOT NULL,
        run_id NVARCHAR(250) COLLATE Latin1_General_BIN2 NOT NULL,
        versao INT NOT NULL CONSTRAINT DF_etl_parametro_snapshot_versao DEFAULT 1,
        payload_cifrado NVARCHAR(MAX) NOT NULL,
        criado_em DATETIME2 NOT NULL CONSTRAINT DF_etl_parametro_snapshot_data DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_etl_parametro_snapshot PRIMARY KEY (pipeline_name, run_id),
        CONSTRAINT CK_etl_parametro_snapshot_versao CHECK (versao=1)
    );
END;
GO

IF COL_LENGTH('dbo.etl_pipeline', 'param_snapshot_ativo') IS NULL
    ALTER TABLE dbo.etl_pipeline ADD param_snapshot_ativo BIT NOT NULL
        CONSTRAINT DF_etl_pipeline_param_snapshot_ativo DEFAULT 0 WITH VALUES;
GO
