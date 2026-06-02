USE [DMDB41];
GO

/* ============================================================
   ORQUESTRA — Importação de Sequence (v1.0)
   Deploy único (produção): idempotente.

   Inclui:
   1) CREATE TABLE dbo.etl_seq_import
   2) CREATE TABLE dbo.etl_seq_import_job
   3) CREATE TABLE dbo.etl_seq_import_lineage
   4) CREATE/ALTER PROC dbo.sp_etl_seq_import_approve
   ============================================================ */

/* 1) etl_seq_import */
IF OBJECT_ID('dbo.etl_seq_import', 'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[etl_seq_import] (
        [id]                    INT IDENTITY(1,1) NOT NULL,
        [dsx_filename]          VARCHAR(200) NOT NULL,
        [seq_name_raw]          NVARCHAR(300) NOT NULL,
        [seq_name]              NVARCHAR(300) NOT NULL,
        [project_name]          NVARCHAR(50)  NOT NULL,
        [domain]                NVARCHAR(100) NULL,
        [pipeline_name_suggest] NVARCHAR(200) NULL,
        [pipeline_name_override] NVARCHAR(200) NULL,
        [schedule_type]         VARCHAR(20) NULL,
        [schedule_hour]         TINYINT NULL,
        [schedule_minute]       TINYINT NULL,
        [schedule_dow]          TINYINT NULL,
        [schedule_dom]          TINYINT NULL,
        [scheduled_time]        TIME(0) NULL,
        [status]                VARCHAR(30) NOT NULL DEFAULT ('pendente_aprovacao'),
        [imported_by]           NVARCHAR(100) NULL,
        [reviewed_by]           NVARCHAR(100) NULL,
        [created_at]            DATETIME2(0) NOT NULL DEFAULT (SYSDATETIME()),
        [updated_at]            DATETIME2(0) NOT NULL DEFAULT (SYSDATETIME()),
        CONSTRAINT [PK_etl_seq_import] PRIMARY KEY CLUSTERED ([id] ASC)
    );
    PRINT 'OK: dbo.etl_seq_import criada';
END
GO

/* 2) etl_seq_import_job */
IF OBJECT_ID('dbo.etl_seq_import_job', 'U') IS NULL
BEGIN
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
    PRINT 'OK: dbo.etl_seq_import_job criada';
END
GO

/* 3) etl_seq_import_lineage */
IF OBJECT_ID('dbo.etl_seq_import_lineage', 'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[etl_seq_import_lineage] (
        [id]              INT IDENTITY(1,1) NOT NULL,
        [import_id]       INT NOT NULL,
        [import_job_id]   INT NOT NULL,
        [direction]       NVARCHAR(30) NOT NULL,
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
    PRINT 'OK: dbo.etl_seq_import_lineage criada';
END
GO

/* 4) sp_etl_seq_import_approve */
CREATE OR ALTER PROCEDURE [dbo].[sp_etl_seq_import_approve]
(
    @import_id   INT,
    @reviewed_by NVARCHAR(100)
)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    BEGIN TRY
        BEGIN TRAN;

        DECLARE
            @pipeline_name NVARCHAR(200),
            @project_name  NVARCHAR(50),
            @domain        NVARCHAR(100),
            @stype         VARCHAR(20),
            @shour         TINYINT,
            @smin          TINYINT,
            @sdow          TINYINT,
            @sdom          TINYINT,
            @stime         TIME(0);

        SELECT
            @pipeline_name = COALESCE(NULLIF(pipeline_name_override,''), NULLIF(pipeline_name_suggest,'')),
            @project_name  = project_name,
            @domain        = COALESCE(NULLIF(domain,''), 'GERAL'),
            @stype         = schedule_type,
            @shour         = schedule_hour,
            @smin          = schedule_minute,
            @sdow          = schedule_dow,
            @sdom          = schedule_dom,
            @stime         = scheduled_time
        FROM dbo.etl_seq_import
        WHERE id = @import_id
          AND status = 'pendente_aprovacao';

        IF @pipeline_name IS NULL
            RAISERROR('Import %d sem pipeline_name definido (suggest/override).', 16, 1, @import_id);

        IF @stime IS NULL
        BEGIN
            DECLARE @hh INT = ISNULL(CAST(@shour AS INT), 6);
            DECLARE @mm INT = ISNULL(CAST(@smin  AS INT), 0);
            SET @stime = TIMEFROMPARTS(@hh, @mm, 0, 0, 0);
        END

        EXEC dbo.sp_etl_pipeline_upsert
            @pipeline_name    = @pipeline_name,
            @scheduled_time   = @stime,
            @schedule_type    = @stype,
            @schedule_hour    = @shour,
            @schedule_minute  = @smin,
            @schedule_dow     = @sdow,
            @schedule_dom     = @sdom,
            @active           = 1,
            @envia_msg_inicio = 1,
            @envia_msg_fim    = 1,
            @envia_msg_erro   = 1,
            @dag_criada       = 0,
            @project_name     = @project_name,
            @domain           = @domain,
            @tags             = '';

        -- Recria jobs
        DELETE FROM dbo.etl_pipeline_job WHERE pipeline_name = @pipeline_name;

        INSERT INTO dbo.etl_pipeline_job (pipeline_name, job_name, execution_order, job_type, job_command, active, created_at, updated_at)
        SELECT
            @pipeline_name,
            j.job_name_orq,
            j.execution_order,
            'datastage',
            NULL,
            1,
            SYSDATETIME(),
            SYSDATETIME()
        FROM dbo.etl_seq_import_job j
        WHERE j.import_id = @import_id
          AND j.ignored = 0
        ORDER BY j.execution_order;

        -- Lineage: remove e insere
        DELETE FROM dbo.etl_job_lineage WHERE pipeline_name = @pipeline_name;

        INSERT INTO dbo.etl_job_lineage
        (
            pipeline_name, job_name, direction, object_type, object_name,
            stage_name, stage_type_raw, database_name, sql_expression, file_path,
            dsx_source_file, extracted_at, extraction_method,
            created_at, updated_at
        )
        SELECT
            @pipeline_name,
            j.job_name_orq,
            l.direction,
            l.object_type,
            l.object_name,
            l.stage_name,
            l.stage_type_raw,
            l.database_name,
            l.sql_expression,
            l.file_path,
            l.dsx_source_file,
            l.extracted_at,
            l.extraction_method,
            SYSDATETIME(),
            SYSDATETIME()
        FROM dbo.etl_seq_import_lineage l
        INNER JOIN dbo.etl_seq_import_job j
            ON j.id = l.import_job_id
        WHERE l.import_id = @import_id
          AND j.ignored = 0;

        UPDATE dbo.etl_seq_import
        SET
            status = 'aprovado',
            reviewed_by = @reviewed_by,
            updated_at = SYSDATETIME()
        WHERE id = @import_id;

        COMMIT;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK;
        DECLARE @ErrorMessage NVARCHAR(4000) = ERROR_MESSAGE();
        DECLARE @ErrorSeverity INT = ERROR_SEVERITY();
        RAISERROR (@ErrorMessage, @ErrorSeverity, 1);
    END CATCH
END
GO

PRINT 'OK: sp_etl_seq_import_approve';
GO

