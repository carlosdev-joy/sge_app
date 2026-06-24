-- 046_drop_ds_malha_tables.sql
-- Dropa as tabelas da feature "Malha DS" (mesh do DataStage), removida do produto
-- na migration 045 e na remoção de código backend/frontend/DAG. Não há FK entre
-- elas nem para outras tabelas (o ack de falha reusava execution_id, sem FK), então
-- a ordem de drop é indiferente — ainda assim dropamos filhas antes do cabeçalho.
--
-- ATENÇÃO: destrutivo e irreversível (apaga os dados de malha importados). Foi
-- pedido explicitamente. O DSX/lineage da Governança NÃO usa estas tabelas.
--
-- Idempotente: cada DROP é guardado por IF OBJECT_ID(...) IS NOT NULL.

IF OBJECT_ID('dbo.etl_ds_malha_falha', 'U') IS NOT NULL
    DROP TABLE dbo.etl_ds_malha_falha;
GO
IF OBJECT_ID('dbo.etl_ds_malha_status', 'U') IS NOT NULL
    DROP TABLE dbo.etl_ds_malha_status;
GO
IF OBJECT_ID('dbo.etl_ds_malha_edge', 'U') IS NOT NULL
    DROP TABLE dbo.etl_ds_malha_edge;
GO
IF OBJECT_ID('dbo.etl_ds_malha_node', 'U') IS NOT NULL
    DROP TABLE dbo.etl_ds_malha_node;
GO
IF OBJECT_ID('dbo.etl_ds_malha', 'U') IS NOT NULL
    DROP TABLE dbo.etl_ds_malha;
GO
