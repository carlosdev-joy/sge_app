-- F7C: valores protegidos imutáveis fora de snapshots e logs.
SET NOCOUNT ON;
SET XACT_ABORT ON;
BEGIN TRANSACTION;
IF OBJECT_ID('dbo.etl_workspace_segredo','U') IS NULL
BEGIN
 CREATE TABLE dbo.etl_workspace_segredo (
  secret_id UNIQUEIDENTIFIER NOT NULL PRIMARY KEY,
  pipeline_name NVARCHAR(200) NOT NULL,
  job_name NVARCHAR(200) NULL,
  param_name NVARCHAR(128) NOT NULL,
  ciphertext NVARCHAR(MAX) NOT NULL,
  criado_por NVARCHAR(100) NOT NULL,
  draft_id UNIQUEIDENTIFIER NOT NULL REFERENCES dbo.etl_workspace_rascunho(draft_id),
  criado_em DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
 );
END;
IF OBJECT_ID('dbo.etl_workspace_segredo_legado','U') IS NULL
BEGIN
 CREATE TABLE dbo.etl_workspace_segredo_legado (
  baseline_id BIGINT IDENTITY NOT NULL PRIMARY KEY,
  version_id UNIQUEIDENTIFIER NOT NULL REFERENCES dbo.etl_workspace_versao(version_id),
  pipeline_name NVARCHAR(200) NOT NULL, job_name NVARCHAR(200) NULL,
  param_name NVARCHAR(128) COLLATE Latin1_General_100_BIN2 NOT NULL,
  ciphertext NVARCHAR(MAX) NOT NULL,
  criado_em DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
  CONSTRAINT UQ_workspace_segredo_legado UNIQUE(version_id,job_name,param_name)
 );
END;
COMMIT;
GO
CREATE OR ALTER TRIGGER dbo.tr_workspace_segredo_imutavel ON dbo.etl_workspace_segredo INSTEAD OF UPDATE, DELETE AS
BEGIN
 THROW 51002, 'Referencias protegidas workspace sao imutaveis', 1;
END;
GO
CREATE OR ALTER TRIGGER dbo.tr_workspace_segredo_legado_imutavel ON dbo.etl_workspace_segredo_legado INSTEAD OF UPDATE, DELETE AS
BEGIN
 THROW 51003, 'Valores protegidos historicos workspace sao imutaveis', 1;
END;
GO
CREATE OR ALTER PROCEDURE dbo.sp_workspace_capture_legacy_secrets @version UNIQUEIDENTIFIER, @name NVARCHAR(200) AS
BEGIN
 SET NOCOUNT ON;
 DECLARE @definition NVARCHAR(MAX);
 SELECT @definition=definition_json FROM dbo.etl_workspace_versao WHERE version_id=@version AND pipeline_name=@name;
 IF @definition IS NULL RETURN;
 IF OBJECT_ID('dbo.etl_pipeline_param','U') IS NOT NULL
 BEGIN
  INSERT dbo.etl_workspace_segredo_legado(version_id,pipeline_name,job_name,param_name,ciphertext)
  SELECT @version,@name,NULL,p.param_name,p.param_value
  FROM OPENJSON(@definition,'$.metadata.legacyTables.etl_pipeline_param') j
  JOIN dbo.etl_pipeline_param p ON p.pipeline_name=@name AND p.param_name COLLATE Latin1_General_100_BIN2=JSON_VALUE(j.value,'$.param_name') COLLATE Latin1_General_100_BIN2
  WHERE LOWER(p.param_type)='encrypted' AND JSON_VALUE(j.value,'$.secretReference.secretId') IS NULL
   AND JSON_VALUE(j.value,'$.secretReference.parameterName')=JSON_VALUE(j.value,'$.param_name')
   AND NOT EXISTS(SELECT 1 FROM dbo.etl_workspace_segredo_legado b WHERE b.version_id=@version AND b.job_name IS NULL AND b.param_name=p.param_name COLLATE Latin1_General_100_BIN2);
 END;
 IF OBJECT_ID('dbo.etl_pipeline_job_param','U') IS NOT NULL
 BEGIN
  INSERT dbo.etl_workspace_segredo_legado(version_id,pipeline_name,job_name,param_name,ciphertext)
  SELECT @version,@name,JSON_VALUE(j.value,'$.secretReference.jobName'),p.param_name,p.param_value
  FROM OPENJSON(@definition,'$.nodes') n CROSS APPLY OPENJSON(n.value,'$.configuration.etl_pipeline_job_param') j
  JOIN dbo.etl_pipeline_job_param p ON p.pipeline_name=@name AND p.job_name=JSON_VALUE(j.value,'$.secretReference.jobName') AND p.param_name COLLATE Latin1_General_100_BIN2=JSON_VALUE(j.value,'$.param_name') COLLATE Latin1_General_100_BIN2
  WHERE LOWER(p.param_type)='encrypted' AND JSON_VALUE(j.value,'$.secretReference.secretId') IS NULL
   AND JSON_VALUE(j.value,'$.secretReference.parameterName')=JSON_VALUE(j.value,'$.param_name')
   AND NOT EXISTS(SELECT 1 FROM dbo.etl_workspace_segredo_legado b WHERE b.version_id=@version AND b.job_name=p.job_name AND b.param_name=p.param_name COLLATE Latin1_General_100_BIN2);
 END;
END;
GO
-- A prova e a captura compartilham locks da fonte; edição legada não pode
-- trocar a cifra entre o hash e a captura. Falha/deadlock desfaz toda captura.
CREATE OR ALTER PROCEDURE dbo.sp_workspace_capture_verified_legacy @version UNIQUEIDENTIFIER,@name NVARCHAR(200),@expected CHAR(64) AS
BEGIN
 SET NOCOUNT ON; SET XACT_ABORT ON;
 SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
 BEGIN TRY
  BEGIN TRANSACTION;
  DECLARE @hash TABLE(active_hash CHAR(64));
  INSERT @hash EXEC dbo.sp_workspace_active_hash @name;
  IF @expected IS NOT NULL AND EXISTS(SELECT 1 FROM @hash WHERE active_hash=@expected)
   EXEC dbo.sp_workspace_capture_legacy_secrets @version,@name;
  COMMIT;
 END TRY
 BEGIN CATCH
  IF @@TRANCOUNT>0 ROLLBACK;
  THROW;
 END CATCH;
END;
GO
IF OBJECT_ID('dbo.etl_workspace_pipeline','U') IS NOT NULL AND OBJECT_ID('dbo.sp_workspace_active_hash','P') IS NOT NULL AND COL_LENGTH('dbo.etl_workspace_rascunho','base_active_hash') IS NOT NULL
 EXEC(N'DECLARE @name NVARCHAR(200),@version UNIQUEIDENTIFIER,@expected CHAR(64),@actual CHAR(64);
DECLARE @hash TABLE(active_hash CHAR(64));
DECLARE baseline CURSOR LOCAL FAST_FORWARD FOR
 SELECT p.pipeline_name,p.version_id,p.active_hash FROM dbo.etl_workspace_pipeline p WHERE p.version_id IS NOT NULL
 UNION SELECT d.pipeline_name,d.base_version_id,d.base_active_hash FROM dbo.etl_workspace_rascunho d WHERE d.estado=''ativo'' AND d.base_version_id IS NOT NULL;
OPEN baseline; FETCH NEXT FROM baseline INTO @name,@version,@expected;
WHILE @@FETCH_STATUS=0 BEGIN
 EXEC dbo.sp_workspace_capture_verified_legacy @version,@name,@expected;
 FETCH NEXT FROM baseline INTO @name,@version,@expected;
END;
CLOSE baseline; DEALLOCATE baseline;');
GO
