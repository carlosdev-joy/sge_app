-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 015 — Log estruturado da etl_dag_factory
--   Armazena o resultado de cada regeneração direto no banco,
--   eliminando dependência do log server do Airflow (403 por secret_key).
-- ═══════════════════════════════════════════════════════════════════════════

IF OBJECT_ID('dbo.etl_factory_log', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_factory_log (
        id              INT IDENTITY(1,1) PRIMARY KEY,
        dag_run_id      VARCHAR(200)  NOT NULL,
        iniciado_em     DATETIME      NOT NULL DEFAULT GETDATE(),
        finalizado_em   DATETIME      NULL,
        estado          VARCHAR(20)   NOT NULL DEFAULT 'RUNNING',  -- RUNNING | SUCCESS | FAILED
        escopo          NVARCHAR(500) NULL,
        pipeline_name   VARCHAR(200)  NULL,
        geradas         INT           NOT NULL DEFAULT 0,
        erros           INT           NOT NULL DEFAULT 0,
        detalhes_json   NVARCHAR(MAX) NULL,  -- JSON: lista de steps + erros
        CONSTRAINT UQ_etl_factory_log_run UNIQUE (dag_run_id)
    );
    PRINT '[OK] Tabela dbo.etl_factory_log criada';
END
GO
