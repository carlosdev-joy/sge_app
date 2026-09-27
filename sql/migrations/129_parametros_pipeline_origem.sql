-- F1: mesmo catálogo, destino explícito e procedência separada da fonte do valor.
-- Legado permanece manual/datastage. Valores cifrados e nomes não são alterados.
-- Aplicar após 108, na etapa 6c; atualizar API e reiniciar worker antes de criar ORQ.
IF OBJECT_ID('dbo.etl_pipeline_param', 'U') IS NULL
    THROW 50129, 'Aplique a migration 108 antes da 129.', 1;
GO
IF COL_LENGTH('dbo.etl_pipeline_param', 'param_destino') IS NULL
    ALTER TABLE dbo.etl_pipeline_param ADD param_destino VARCHAR(16) NOT NULL
        CONSTRAINT DF_etl_pipeline_param_destino DEFAULT 'datastage' WITH VALUES;
GO
IF COL_LENGTH('dbo.etl_pipeline_param', 'param_procedencia') IS NULL
    ALTER TABLE dbo.etl_pipeline_param ADD param_procedencia VARCHAR(16) NOT NULL
        CONSTRAINT DF_etl_pipeline_param_procedencia DEFAULT 'manual' WITH VALUES;
GO
IF COL_LENGTH('dbo.etl_pipeline_param', 'param_import_project') IS NULL
    ALTER TABLE dbo.etl_pipeline_param ADD param_import_project NVARCHAR(128) NULL;
GO
IF COL_LENGTH('dbo.etl_pipeline_param', 'param_import_job') IS NULL
    ALTER TABLE dbo.etl_pipeline_param ADD param_import_job NVARCHAR(128) NULL;
GO
IF COL_LENGTH('dbo.etl_pipeline_param', 'param_descricao') IS NULL
    ALTER TABLE dbo.etl_pipeline_param ADD param_descricao NVARCHAR(500) NULL;
GO
IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name='CK_etl_pipeline_param_catalogo')
    ALTER TABLE dbo.etl_pipeline_param WITH CHECK ADD CONSTRAINT CK_etl_pipeline_param_catalogo
    CHECK (param_destino COLLATE Latin1_General_BIN2 IN ('datastage', 'orquestra')
       AND param_procedencia COLLATE Latin1_General_BIN2 IN ('manual', 'datastage')
       AND ((param_procedencia='manual' AND param_import_project IS NULL AND param_import_job IS NULL)
         OR (param_procedencia='datastage' AND param_import_project IS NOT NULL
             AND LEN(param_import_project)>0 AND param_import_job IS NOT NULL AND LEN(param_import_job)>0)));
GO
