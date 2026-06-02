USE [DMDB41];
GO

/* ============================================================
   ORQUESTRA — Importação de Sequence (v1.0)
   Tabela de staging: dbo.etl_seq_import

   Objetivo:
   - Guardar upload/parse de DSX de Sequence para revisão antes de
     criar pipeline + jobs + lineage no ORQUESTRA.
   ============================================================ */

CREATE TABLE [dbo].[etl_seq_import] (
    [id]                    INT IDENTITY(1,1) NOT NULL,
    [dsx_filename]          VARCHAR(200) NOT NULL,
    [seq_name_raw]          NVARCHAR(300) NOT NULL,
    [seq_name]              NVARCHAR(300) NOT NULL,
    [project_name]          NVARCHAR(50)  NOT NULL,
    [domain]                NVARCHAR(100) NULL,
    [pipeline_name_suggest] NVARCHAR(200) NULL,
    [pipeline_name_override] NVARCHAR(200) NULL,

    -- Schedule (compatível com Fase 3)
    [schedule_type]         VARCHAR(20) NULL,  -- hourly|daily|weekly|monthly
    [schedule_hour]         TINYINT NULL,
    [schedule_minute]       TINYINT NULL,
    [schedule_dow]          TINYINT NULL,
    [schedule_dom]          TINYINT NULL,
    [scheduled_time]        TIME(0) NULL,      -- legado (derivado)

    [status]                VARCHAR(30) NOT NULL DEFAULT ('pendente_aprovacao'),
    [imported_by]           NVARCHAR(100) NULL,
    [reviewed_by]           NVARCHAR(100) NULL,

    [created_at]            DATETIME2(0) NOT NULL DEFAULT (SYSDATETIME()),
    [updated_at]            DATETIME2(0) NOT NULL DEFAULT (SYSDATETIME()),

    CONSTRAINT [PK_etl_seq_import] PRIMARY KEY CLUSTERED ([id] ASC)
);
GO

