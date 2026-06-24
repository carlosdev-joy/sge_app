-- 045_remove_tela_malha_ds.sql
-- Remove o recurso de tela tela_malha_ds: a feature "Malha DS" (estrutura/mesh do
-- DataStage) foi excluída do produto. A tela, o item de menu e o backend de mesh
-- saíram; o recurso virou vestigial. Limpamos para não ressuscitá-lo em ambientes
-- novos nem poluir a tela de Perfis (mesmo espírito do tela_ds_monitor na 044).
--
-- O DSX/lineage da Governança continua (router próprio, gateado por tela_governanca)
-- e a Malha de Pipelines (tela_malha) é outra feature — nenhuma é afetada aqui.
--
-- Idempotente: DELETE é no-op se já não existir. Degrada se a tabela não existir.

IF EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
           WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'etl_perfil_permissao')
BEGIN
    DELETE FROM dbo.etl_perfil_permissao WHERE recurso = 'tela_malha_ds';
    PRINT '[OK] Recurso tela_malha_ds removido (feature Malha DS excluida do produto)';
END
ELSE
    PRINT '[SKIP] Tabela etl_perfil_permissao ainda nao existe';
GO
