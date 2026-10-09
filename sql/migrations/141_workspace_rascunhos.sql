-- F2. DDL apenas no deploy. Collation herdada da identidade legada.
SET NOCOUNT ON;
SET XACT_ABORT ON;
BEGIN TRANSACTION;
IF OBJECT_ID('dbo.etl_workspace_versao','U') IS NULL
CREATE TABLE dbo.etl_workspace_versao (
 version_id UNIQUEIDENTIFIER NOT NULL PRIMARY KEY,
 pipeline_name NVARCHAR(200) NOT NULL,
 numero INT NOT NULL CHECK(numero > 0), origem VARCHAR(20) NOT NULL DEFAULT 'importada' CHECK(origem IN ('importada','publicada')),
 definition_json NVARCHAR(MAX) NOT NULL CHECK(ISJSON(definition_json)=1),
 layout_json NVARCHAR(MAX) NOT NULL CHECK(ISJSON(layout_json)=1),
 content_hash CHAR(64) NOT NULL, criada_por NVARCHAR(100) NOT NULL,
 criada_em DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
 CONSTRAINT UQ_workspace_versao UNIQUE(pipeline_name,numero)
);
IF OBJECT_ID('dbo.etl_workspace_rascunho','U') IS NULL
CREATE TABLE dbo.etl_workspace_rascunho (
 draft_id UNIQUEIDENTIFIER NOT NULL PRIMARY KEY, pipeline_name NVARCHAR(200) NOT NULL,
 base_version_id UNIQUEIDENTIFIER NULL REFERENCES dbo.etl_workspace_versao(version_id),
 definition_json NVARCHAR(MAX) NOT NULL CHECK(ISJSON(definition_json)=1),
 layout_json NVARCHAR(MAX) NOT NULL CHECK(ISJSON(layout_json)=1),
 read_only_json NVARCHAR(MAX) NOT NULL DEFAULT '[]' CHECK(ISJSON(read_only_json)=1),
 revision BIGINT NOT NULL DEFAULT 1 CHECK(revision>0), estado VARCHAR(20) NOT NULL DEFAULT 'ativo' CHECK(estado IN ('ativo','descartado')),
 criado_por NVARCHAR(100) NOT NULL, responsavel NVARCHAR(100) NOT NULL,
 criado_em DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(), atualizado_em DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
);
IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.etl_workspace_rascunho') AND name='UX_workspace_rascunho_ativo')
CREATE UNIQUE INDEX UX_workspace_rascunho_ativo ON dbo.etl_workspace_rascunho(pipeline_name) WHERE estado='ativo';
IF OBJECT_ID('dbo.etl_workspace_lease','U') IS NULL
CREATE TABLE dbo.etl_workspace_lease (
 draft_id UNIQUEIDENTIFIER NOT NULL PRIMARY KEY REFERENCES dbo.etl_workspace_rascunho(draft_id),
 holder_user NVARCHAR(100) NOT NULL, holder_session_hash CHAR(64) NOT NULL,
 fence BIGINT NOT NULL CHECK(fence>0), expires_at DATETIME2 NOT NULL
);
IF OBJECT_ID('dbo.etl_workspace_evento','U') IS NULL
CREATE TABLE dbo.etl_workspace_evento (
 event_id BIGINT IDENTITY NOT NULL PRIMARY KEY,
 entidade VARCHAR(20) NOT NULL DEFAULT 'rascunho', entidade_id UNIQUEIDENTIFIER NOT NULL REFERENCES dbo.etl_workspace_rascunho(draft_id),
 ator NVARCHAR(100) NOT NULL, acao VARCHAR(30) NOT NULL, revision BIGINT NOT NULL,
 operation_id UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(), ocorrido_em DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
 detalhe NVARCHAR(1000) NOT NULL DEFAULT '{}'
);
COMMIT;
GO
CREATE OR ALTER TRIGGER dbo.tr_workspace_versao_imutavel ON dbo.etl_workspace_versao INSTEAD OF UPDATE, DELETE AS
BEGIN
 THROW 51001, 'Versoes workspace sao imutaveis', 1;
END;
GO
