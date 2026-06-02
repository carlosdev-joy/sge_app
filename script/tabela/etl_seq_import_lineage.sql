USE [DMDB41];
GO

/* ORQUESTRA — Importação de Sequence (v1.0) — Lineage (staging) */

CREATE TABLE [dbo].[etl_seq_import_lineage] (
    [id]              INT IDENTITY(1,1) NOT NULL,
    [import_id]       INT NOT NULL,
    [import_job_id]   INT NOT NULL,
    [direction]       NVARCHAR(30) NOT NULL, -- origem|destino|transformacao
    [object_type]     NVARCHAR(20) NOT NULL,
    [object_name]     NVARCHAR(500) NOT NULL,
    [stage_name]      VARCHAR(200) NULL,
    [stage_type_raw]  VARCHAR(100) NULL,
    [database_name]   VARCHAR(200) NULL,
    [sql_expression]  NVARCHAR(MAX) NULL,
    [file_path]       VARCHAR(500) NULL,
    [dsx_source_file] VARCHAR(500) NULL,
    [extracted_at]    DATETIME2(7) NULL,
    [extraction_method] VARCHAR(20) NULL,
    CONSTRAINT [PK_etl_seq_import_lineage] PRIMARY KEY CLUSTERED ([id] ASC),
    CONSTRAINT [FK_etl_seq_import_lineage_import] FOREIGN KEY ([import_id]) REFERENCES dbo.etl_seq_import([id]),
    CONSTRAINT [FK_etl_seq_import_lineage_job] FOREIGN KEY ([import_job_id]) REFERENCES dbo.etl_seq_import_job([id])
);
GO

