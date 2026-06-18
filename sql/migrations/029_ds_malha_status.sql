-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 029 — Status por job da malha (varredura dsjob -jobinfo)
--   Snapshot do status de cada job monitorável da malha, atualizado a cada
--   varredura (DAG etl_ds_malha_status). APARTADO da geração de DAG.
-- ═══════════════════════════════════════════════════════════════════════════

IF OBJECT_ID('dbo.etl_ds_malha_status', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_ds_malha_status (
        id           INT IDENTITY(1,1) PRIMARY KEY,
        project      NVARCHAR(200) NOT NULL,
        job_name     NVARCHAR(300) NOT NULL,
        status_code  INT           NULL,      -- código dsjob (1=OK,2=WARN,3=ABORTED,0=RUNNING,...)
        status_label VARCHAR(30)   NULL,      -- rótulo legível
        info         NVARCHAR(500) NULL,      -- linha "Job Status" bruta
        scanned_at   DATETIME2(7)  NOT NULL DEFAULT SYSDATETIME()
    );
    CREATE UNIQUE INDEX UX_etl_ds_malha_status ON dbo.etl_ds_malha_status (project, job_name);
END
GO
