-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 043 — Nó de Decisão (ramificação condicional) em pipelines
--   etl_pipeline_job.condition_json: configuração da condição de um job de
--   decisão (job_type='decisao'). JSON com:
--     tipo (contagem|query), tabela/database OU sql, operador, valor,
--     ramo_verdadeiro [..], ramo_falso [..]  (jobs do MESMO pipeline).
--   A factory cria as arestas Decisão → (t_start dos jobs do ramo). Degrada
--   graciosamente: factory/UI ignoram a decisão se a coluna não existir.
-- Idempotente.
-- ═══════════════════════════════════════════════════════════════════════════

IF COL_LENGTH('dbo.etl_pipeline_job', 'condition_json') IS NULL
BEGIN
    ALTER TABLE dbo.etl_pipeline_job ADD condition_json NVARCHAR(MAX) NULL;
    PRINT '[OK] etl_pipeline_job.condition_json adicionada';
END
GO

-- Tipo de job "Decisão" no catálogo do wizard (lineage não se aplica).
IF OBJECT_ID('dbo.etl_job_type', 'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM dbo.etl_job_type WHERE nome = 'Decisão')
BEGIN
    INSERT INTO dbo.etl_job_type (nome, descricao, lineage_enabled, status)
    VALUES ('Decisão',
            'Nó de decisão — desvia o fluxo por contagem de registros ou valor de uma query',
            0, 1);
    PRINT '[OK] etl_job_type ''Decisão'' inserido';
END
GO
