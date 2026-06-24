-- Migration 051 — sql_json em etl_pipeline_job: config do nó SQL no fluxo.
--
-- Novo nó de fluxo 'sql': roda um SELECT do usuário e PUBLICA o valor escalar
-- (XCom) para uma Decisão a jusante comparar (separação de responsabilidades —
-- o nó SQL roda a query; a decisão recebe o valor e escolhe o caminho).
-- Análogo a condition_json (decisão) e notify_json (notificação): JSON por-coluna,
-- idempotente, e o backend/UI degradam se a coluna não existir.
--
-- Conteúdo de sql_json: {"sql": "<SELECT>", "mssql_conn_id": "<conn>", "database": "<db>"}

IF COL_LENGTH('dbo.etl_pipeline_job', 'sql_json') IS NULL
BEGIN
    ALTER TABLE dbo.etl_pipeline_job ADD sql_json NVARCHAR(MAX) NULL;
    PRINT '[OK] etl_pipeline_job.sql_json adicionada';
END
ELSE
    PRINT '[SKIP] etl_pipeline_job.sql_json já existe';
GO
