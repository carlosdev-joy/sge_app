-- =============================================================
-- reset_dados_dev.sql — Dropa as tabelas de DADOS etl_* do DEV
-- para que o deploy_full.sql as recrie no schema canônico (igual
-- ao de produção), permitindo carregar o dump_prod.sql sem erro
-- de coluna (Msg 207).
--
-- NÃO toca nas tabelas de autenticação (etl_usuario, etl_sessao,
-- etl_perfil*) — assim o login do dev continua funcionando.
--
-- Fluxo:
--   1) docker exec ... -i /dev/stdin < sql/reset_dados_dev.sql
--   2) docker exec ... -i /dev/stdin < sql/deploy_full.sql   (recria schema)
--   3) bash scripts/carregar-dados-dev.sh dump_prod.sql       (carrega dados)
-- =============================================================
SET NOCOUNT ON;
GO

-- Tabelas de dados/lookup que o dump cobre (mesma lista do dump_dados.py).
-- Mantidas em variável de tabela para montar os DROPs dinamicamente.
DECLARE @alvos TABLE (nome SYSNAME);
INSERT INTO @alvos (nome) VALUES
 ('etl_project'),('etl_app_config'),('etl_job_type'),('etl_stage_type_map'),
 ('etl_versao_ferramenta'),('etl_pipeline'),('etl_pipeline_job'),
 ('etl_job_lineage'),('etl_job_execution'),('etl_pipeline_audit'),
 ('etl_pipeline_owner'),('etl_pipeline_performance_snapshot'),
 ('etl_object_tag'),('etl_calendario'),('etl_blackout'),
 ('etl_seq_import'),('etl_seq_import_job'),('etl_seq_import_lineage'),
 ('etl_datastage_job_log'),('etl_factory_log');

-- 1) Derruba todas as FKs que envolvem as tabelas alvo (como pai OU filho),
--    senão o DROP TABLE falha por dependência.
DECLARE @sql NVARCHAR(MAX) = N'';
SELECT @sql += 'ALTER TABLE ' + QUOTENAME(OBJECT_SCHEMA_NAME(fk.parent_object_id))
            + '.' + QUOTENAME(OBJECT_NAME(fk.parent_object_id))
            + ' DROP CONSTRAINT ' + QUOTENAME(fk.name) + ';' + CHAR(10)
FROM sys.foreign_keys fk
WHERE OBJECT_NAME(fk.parent_object_id)     IN (SELECT nome FROM @alvos)
   OR OBJECT_NAME(fk.referenced_object_id) IN (SELECT nome FROM @alvos);

IF @sql <> N''
BEGIN
    PRINT '== Removendo FKs das tabelas alvo ==';
    PRINT @sql;
    EXEC sys.sp_executesql @sql;
END
GO

-- 2) Dropa as tabelas alvo (IF EXISTS — re-executável).
DROP TABLE IF EXISTS dbo.etl_factory_log;
DROP TABLE IF EXISTS dbo.etl_datastage_job_log;
DROP TABLE IF EXISTS dbo.etl_seq_import_lineage;
DROP TABLE IF EXISTS dbo.etl_seq_import_job;
DROP TABLE IF EXISTS dbo.etl_seq_import;
DROP TABLE IF EXISTS dbo.etl_blackout;
DROP TABLE IF EXISTS dbo.etl_calendario;
DROP TABLE IF EXISTS dbo.etl_object_tag;
DROP TABLE IF EXISTS dbo.etl_pipeline_performance_snapshot;
DROP TABLE IF EXISTS dbo.etl_pipeline_owner;
DROP TABLE IF EXISTS dbo.etl_pipeline_audit;
DROP TABLE IF EXISTS dbo.etl_job_execution;
DROP TABLE IF EXISTS dbo.etl_job_lineage;
DROP TABLE IF EXISTS dbo.etl_pipeline_job;
DROP TABLE IF EXISTS dbo.etl_pipeline;
DROP TABLE IF EXISTS dbo.etl_versao_ferramenta;
DROP TABLE IF EXISTS dbo.etl_stage_type_map;
DROP TABLE IF EXISTS dbo.etl_job_type;
DROP TABLE IF EXISTS dbo.etl_app_config;
DROP TABLE IF EXISTS dbo.etl_project;
GO

PRINT '== Reset concluído. Rode agora o deploy_full.sql para recriar o schema canônico. ==';
GO
