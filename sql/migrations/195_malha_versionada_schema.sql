-- EOC-F16 contrato/leitura: schema inerte, sem opt-in nem backfill.
-- Idempotente — seguro para rodar mais de uma vez.
SET XACT_ABORT ON;
BEGIN TRANSACTION;
IF OBJECT_ID('dbo.etl_malha_versionamento','U') IS NULL
BEGIN
 CREATE TABLE dbo.etl_malha_versionamento (
  malha_id UNIQUEIDENTIFIER NOT NULL PRIMARY KEY,
  malha_name NVARCHAR(200) NOT NULL UNIQUE,
  effective_version_id UNIQUEIDENTIFIER NULL,
  revision BIGINT NOT NULL DEFAULT 1 CHECK(revision>0),
  estado VARCHAR(20) NOT NULL DEFAULT 'compatibilidade' CHECK(estado IN ('compatibilidade','gerido'))
 );
END;
IF OBJECT_ID('dbo.etl_malha_versao','U') IS NULL
BEGIN
 CREATE TABLE dbo.etl_malha_versao (
  version_id UNIQUEIDENTIFIER NOT NULL PRIMARY KEY,
  malha_id UNIQUEIDENTIFIER NOT NULL REFERENCES dbo.etl_malha_versionamento(malha_id),
  malha_name NVARCHAR(200) NOT NULL,
  numero INT NOT NULL CHECK(numero>0), schema_version INT NOT NULL DEFAULT 1 CHECK(schema_version=1),
  definition_json NVARCHAR(MAX) NOT NULL CHECK(ISJSON(definition_json)=1),
  layout_json NVARCHAR(MAX) NOT NULL CHECK(ISJSON(layout_json)=1),
  definition_hash CHAR(64) NOT NULL, layout_hash CHAR(64) NOT NULL,
  criada_por NVARCHAR(100) NOT NULL, criada_em DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
  CONSTRAINT UQ_malha_versao_numero UNIQUE(malha_id,numero),
  CONSTRAINT UQ_malha_versao_dono UNIQUE(malha_id,version_id)
 );
END;
IF NOT EXISTS(SELECT 1 FROM sys.foreign_keys WHERE name='FK_malha_effective_dono' AND parent_object_id=OBJECT_ID('dbo.etl_malha_versionamento'))
 ALTER TABLE dbo.etl_malha_versionamento ADD CONSTRAINT FK_malha_effective_dono
 FOREIGN KEY(malha_id,effective_version_id) REFERENCES dbo.etl_malha_versao(malha_id,version_id);
IF OBJECT_ID('dbo.etl_malha_versao_membro','U') IS NULL
BEGIN
 CREATE TABLE dbo.etl_malha_versao_membro (
  malha_version_id UNIQUEIDENTIFIER NOT NULL REFERENCES dbo.etl_malha_versao(version_id),
  pipeline_name NVARCHAR(200) NOT NULL,
  pipeline_version_id UNIQUEIDENTIFIER NOT NULL REFERENCES dbo.etl_workspace_versao(version_id),
  content_hash CHAR(64) NOT NULL,
  PRIMARY KEY(malha_version_id,pipeline_name)
 );
END;
IF OBJECT_ID('dbo.etl_malha_rascunho','U') IS NULL
BEGIN
 CREATE TABLE dbo.etl_malha_rascunho (
  draft_id UNIQUEIDENTIFIER NOT NULL PRIMARY KEY,
  malha_id UNIQUEIDENTIFIER NOT NULL REFERENCES dbo.etl_malha_versionamento(malha_id),
  malha_name NVARCHAR(200) NOT NULL, base_version_id UNIQUEIDENTIFIER NULL,
  definition_json NVARCHAR(MAX) NOT NULL CHECK(ISJSON(definition_json)=1),
  layout_json NVARCHAR(MAX) NOT NULL CHECK(ISJSON(layout_json)=1),
  revision BIGINT NOT NULL DEFAULT 1 CHECK(revision>0),
  estado VARCHAR(20) NOT NULL DEFAULT 'ativo' CHECK(estado IN ('ativo','descartado','publicado')),
  criado_por NVARCHAR(100) NOT NULL, responsavel NVARCHAR(100) NOT NULL,
  criado_em DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(), atualizado_em DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
  CONSTRAINT FK_malha_draft_base_dono FOREIGN KEY(malha_id,base_version_id)
   REFERENCES dbo.etl_malha_versao(malha_id,version_id)
 );
END;
IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.etl_malha_rascunho') AND name='UX_malha_draft_ativo')
 CREATE UNIQUE INDEX UX_malha_draft_ativo ON dbo.etl_malha_rascunho(malha_id) WHERE estado='ativo';
IF OBJECT_ID('dbo.etl_malha_corrida_versao','U') IS NULL
BEGIN
 CREATE TABLE dbo.etl_malha_corrida_versao (
  corrida_id BIGINT NOT NULL PRIMARY KEY REFERENCES dbo.etl_malha_execucao(id),
  malha_version_id UNIQUEIDENTIFIER NOT NULL REFERENCES dbo.etl_malha_versao(version_id),
  definition_hash CHAR(64) NOT NULL, capturada_em DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
 );
END;
COMMIT;
GO
CREATE OR ALTER TRIGGER dbo.tr_malha_versao_imutavel ON dbo.etl_malha_versao INSTEAD OF UPDATE, DELETE AS
BEGIN
 THROW 51195, 'Versoes de malha sao imutaveis', 1;
END;
GO
CREATE OR ALTER TRIGGER dbo.tr_malha_membro_imutavel ON dbo.etl_malha_versao_membro INSTEAD OF UPDATE, DELETE AS
BEGIN
 THROW 51195, 'Referencias de malha sao imutaveis', 1;
END;
GO
CREATE OR ALTER TRIGGER dbo.tr_malha_corrida_versao_imutavel ON dbo.etl_malha_corrida_versao INSTEAD OF UPDATE, DELETE AS
BEGIN
 THROW 51195, 'Vinculo de corrida e imutavel', 1;
END;
GO
-- INSERT de referencia exige identidade e hash exatos da versao workspace.
CREATE OR ALTER TRIGGER dbo.tr_malha_membro_identidade ON dbo.etl_malha_versao_membro AFTER INSERT AS
BEGIN
 IF EXISTS(SELECT 1 FROM inserted i JOIN dbo.etl_workspace_versao v ON v.version_id=i.pipeline_version_id
           WHERE i.pipeline_name<>v.pipeline_name OR i.content_hash COLLATE Latin1_General_100_BIN2<>v.content_hash COLLATE Latin1_General_100_BIN2)
  THROW 51195, 'Referencia workspace divergente', 1;
END;
GO
