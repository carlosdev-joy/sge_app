-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 053 — Cópia de Dados: query SQL livre como fonte da carga
--   src_query em dbo.etl_copy_job — quando preenchida, a cópia ignora as
--   transformações e o filtro do wizard e usa a query como select_sql
--   (a API valida/compila; a DAG etl_copy_exec envolve em subquery).
-- Idempotente — seguro para rodar mais de uma vez.
-- ═══════════════════════════════════════════════════════════════════════════

IF COL_LENGTH('dbo.etl_copy_job', 'src_query') IS NULL
BEGIN
    ALTER TABLE dbo.etl_copy_job ADD src_query NVARCHAR(MAX) NULL;
    PRINT '[OK] Coluna src_query adicionada em dbo.etl_copy_job';
END
ELSE
    PRINT '[SKIP] Coluna src_query ja existe em dbo.etl_copy_job';
GO
