-- Migration 068 — aguarde_json em etl_pipeline_job: config do nó Aguarde.
--
-- Novo nó de fluxo 'aguarde': ponto de encontro entre pernas paralelas. Segura
-- o fluxo até que TODAS as etapas ligadas a ele terminem, e só então libera o
-- que vem depois (caso típico: duas pernas usam os mesmos arquivos de trabalho
-- e a remoção só é segura quando as duas acabaram).
-- Análogo a condition_json (decisão), notify_json (notificação) e sql_json (nó
-- SQL): JSON por-coluna, idempotente, e o backend/UI degradam se a coluna não
-- existir.
--
-- Conteúdo de aguarde_json: {"politica": "todas_sucesso" | "todas_terminarem"}
--   todas_sucesso    (default) — só libera se todas as pernas derem certo
--   todas_terminarem           — libera quando todas terminarem, mesmo com
--                                falha (o pipeline SEGUE marcado como falho)
-- Ausente/inválido degrada para 'todas_sucesso' (o conservador).

IF COL_LENGTH('dbo.etl_pipeline_job', 'aguarde_json') IS NULL
BEGIN
    ALTER TABLE dbo.etl_pipeline_job ADD aguarde_json NVARCHAR(MAX) NULL;
    PRINT '[OK] etl_pipeline_job.aguarde_json adicionada';
END
ELSE
    PRINT '[SKIP] etl_pipeline_job.aguarde_json já existe';
GO
