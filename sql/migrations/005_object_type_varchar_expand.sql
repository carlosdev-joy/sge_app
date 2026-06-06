-- Amplia object_type em etl_job_lineage e etl_seq_import_lineage
-- para suportar valores como "Arquivo DataSet (.ds/.dx)"

IF COL_LENGTH('dbo.etl_job_lineage', 'object_type') < 100
    ALTER TABLE dbo.etl_job_lineage ALTER COLUMN object_type NVARCHAR(100) NULL;

IF COL_LENGTH('dbo.etl_seq_import_lineage', 'object_type') < 100
    ALTER TABLE dbo.etl_seq_import_lineage ALTER COLUMN object_type NVARCHAR(100) NULL;
