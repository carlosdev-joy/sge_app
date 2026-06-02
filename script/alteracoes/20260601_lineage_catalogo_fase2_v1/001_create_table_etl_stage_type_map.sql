USE [DMDB41];
GO

/* ORQUESTRA — Lineage Catálogo (Fase 2) v1.0 — CREATE TABLE */

IF OBJECT_ID('dbo.etl_stage_type_map', 'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[etl_stage_type_map] (
        [id]            INT IDENTITY(1,1) NOT NULL,
        [type_raw]      VARCHAR(100) NOT NULL,
        [type_label]    VARCHAR(100) NOT NULL,
        [type_category] VARCHAR(30)  NOT NULL, -- banco | arquivo | transformacao | debug
        [role_hint]     VARCHAR(20)  NOT NULL, -- origem | destino | ambos | transformacao
        [description]   VARCHAR(500) NULL,
        [created_at]    DATETIME     NOT NULL CONSTRAINT [DF_etl_stage_type_map_created_at] DEFAULT (GETDATE()),
        CONSTRAINT [PK_etl_stage_type_map] PRIMARY KEY CLUSTERED ([id] ASC),
        CONSTRAINT [UQ_etl_stage_type_map_type_raw] UNIQUE ([type_raw])
    );
    PRINT 'OK: dbo.etl_stage_type_map criada';
END
ELSE
    PRINT 'JA EXISTE: dbo.etl_stage_type_map';
GO

