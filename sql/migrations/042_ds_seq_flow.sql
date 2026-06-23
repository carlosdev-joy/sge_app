-- 042_ds_seq_flow.sql
-- Cache do FLUXO (DAG de dependências) de uma Sequence do DataStage, extraído do
-- export XML. Parseia o XML na 1a vez e guarda aqui; as próximas consultas leem
-- do banco (sem reparsear). Atualização sob demanda (operador), pois o desenho da
-- sequence muda pouco e de forma programada.
--
-- Idempotente: cria a tabela só se não existir. Backend/UI degradam se faltar.

IF OBJECT_ID('dbo.etl_ds_seq_flow', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_ds_seq_flow (
        project     NVARCHAR(128)  NOT NULL,
        job         NVARCHAR(256)  NOT NULL,
        flow_json   NVARCHAR(MAX)  NOT NULL,   -- {nodes:[...], edges:[...]}
        nodes_count INT            NULL,
        edges_count INT            NULL,
        source_file NVARCHAR(512)  NULL,
        parsed_by   NVARCHAR(64)   NULL,
        parsed_at   DATETIME2(0)   NOT NULL CONSTRAINT DF_etl_ds_seq_flow_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_etl_ds_seq_flow PRIMARY KEY (project, job)
    );
    PRINT '[OK] Tabela etl_ds_seq_flow criada';
END
ELSE
    PRINT '[SKIP] Tabela etl_ds_seq_flow já existe';
GO
