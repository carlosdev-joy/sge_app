-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 056 — Cópia de Dados: limite de linhas (TOP) na carga
--   src_top em dbo.etl_copy_job — quando preenchido (modo tabela/mapeamento),
--   o select_sql compilado ganha TOP (N) e a CARGA FINAL busca no máximo N
--   linhas (count_sql idem — progresso/ETA refletem o limite). Uso típico:
--   validar o mapeamento/transformações com uma amostra antes da carga
--   completa. No MODO QUERY o campo é ignorado (aplique TOP na própria
--   query). A coluna existe para a UI reabrir o wizard com o valor — o TOP
--   efetivo já vai embutido no select_sql gravado.
-- Idempotente — seguro para rodar mais de uma vez.
-- ═══════════════════════════════════════════════════════════════════════════

IF COL_LENGTH('dbo.etl_copy_job', 'src_top') IS NULL
BEGIN
    ALTER TABLE dbo.etl_copy_job ADD src_top INT NULL;
    PRINT '[OK] Coluna src_top adicionada em dbo.etl_copy_job';
END
ELSE
    PRINT '[SKIP] Coluna src_top ja existe em dbo.etl_copy_job';
GO
