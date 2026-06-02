USE [DMDB41];
GO

/* ORQUESTRA — Importação de Sequence (v1.0) — Jobs (staging) */

CREATE TABLE [dbo].[etl_seq_import_job] (
    [id]             INT IDENTITY(1,1) NOT NULL,
    [import_id]      INT NOT NULL,
    [execution_order] INT NOT NULL,
    [job_name_ds]    NVARCHAR(200) NOT NULL,
    [job_name_orq]   NVARCHAR(200) NOT NULL,
    [ignored]        BIT NOT NULL DEFAULT (0),
    [lineage_extracted] BIT NOT NULL DEFAULT (0),
    [lineage_count]  INT NOT NULL DEFAULT (0),
    CONSTRAINT [PK_etl_seq_import_job] PRIMARY KEY CLUSTERED ([id] ASC),
    CONSTRAINT [FK_etl_seq_import_job_import] FOREIGN KEY ([import_id]) REFERENCES dbo.etl_seq_import([id])
);
GO

