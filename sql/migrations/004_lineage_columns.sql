-- 004_lineage_columns.sql
-- Adiciona armazenamento de colunas/campos extraídos do DSX por stage.
-- columns_json: JSON array de strings com os nomes das colunas/campos usados no stage.
--   Ex: '["ID_CLIENTE","NM_CLIENTE","VL_TOTAL"]'

-- Staging (importação pendente de aprovação)
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.etl_seq_import_lineage') AND name = 'columns_json'
)
    ALTER TABLE dbo.etl_seq_import_lineage ADD columns_json NVARCHAR(MAX) NULL;

-- Produção (lineage aprovado)
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.etl_job_lineage') AND name = 'columns_json'
)
    ALTER TABLE dbo.etl_job_lineage ADD columns_json NVARCHAR(MAX) NULL;
