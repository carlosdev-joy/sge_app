USE [DMDB41];
GO

/* ORQUESTRA — Lineage Catálogo (Fase 2) v1.0 — ALTER TABLE etl_job_lineage */

IF COL_LENGTH('dbo.etl_job_lineage', 'file_path') IS NULL
BEGIN
    ALTER TABLE dbo.etl_job_lineage ADD file_path VARCHAR(500) NULL;
    PRINT 'OK: coluna dbo.etl_job_lineage.file_path';
END
ELSE
    PRINT 'JA EXISTE: dbo.etl_job_lineage.file_path';
GO

IF EXISTS (
    SELECT 1
    FROM sys.columns c
    JOIN sys.types t ON t.user_type_id = c.user_type_id
    WHERE c.object_id = OBJECT_ID('dbo.etl_job_lineage')
      AND c.name = 'direction'
      AND t.name IN ('nvarchar', 'varchar')
      AND c.max_length < 60  -- nvarchar(30) = 60 bytes
)
BEGIN
    ALTER TABLE dbo.etl_job_lineage ALTER COLUMN direction NVARCHAR(30) NOT NULL;
    PRINT 'OK: dbo.etl_job_lineage.direction NVARCHAR(30)';
END
ELSE
    PRINT 'OK/JA: dbo.etl_job_lineage.direction';
GO

-- Extended property (tentativa — ignora se já existir)
IF NOT EXISTS (
    SELECT 1
    FROM sys.extended_properties ep
    WHERE ep.major_id = OBJECT_ID('dbo.etl_job_lineage')
      AND ep.minor_id = COLUMNPROPERTY(OBJECT_ID('dbo.etl_job_lineage'),'file_path','ColumnId')
      AND ep.name = 'MS_Description'
)
BEGIN
    EXEC sys.sp_addextendedproperty
        @name = N'MS_Description',
        @value = N'Path completo do arquivo para stages DataSet e SequentialFile. Ex: /opt/airflow/dsx/files/Data_Set_4.ds',
        @level0type = N'SCHEMA', @level0name = N'dbo',
        @level1type = N'TABLE',  @level1name = N'etl_job_lineage',
        @level2type = N'COLUMN', @level2name = N'file_path';
    PRINT 'OK: MS_Description dbo.etl_job_lineage.file_path';
END
GO

