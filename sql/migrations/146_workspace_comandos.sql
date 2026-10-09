-- F5: reserva durável de comando antes do efeito externo, sem persistir conf.
SET NOCOUNT ON;
SET XACT_ABORT ON;
IF OBJECT_ID('dbo.etl_workspace_pipeline','U') IS NULL THROW 50146,'Aplique migration 144 antes da 146.',1;
GO
IF OBJECT_ID('dbo.etl_workspace_comando','U') IS NULL
 CREATE TABLE dbo.etl_workspace_comando (
 pipeline_name NVARCHAR(200) NOT NULL, run_id NVARCHAR(300) NOT NULL,
 command_token UNIQUEIDENTIFIER NOT NULL, version_id UNIQUEIDENTIFIER NOT NULL,
 content_hash CHAR(64) NOT NULL, active_hash CHAR(64) NOT NULL, request_hash CHAR(64) NOT NULL,
 tipo VARCHAR(20) NOT NULL CHECK(tipo IN('execute','reprocess')),
 ator NVARCHAR(100) NOT NULL, estado VARCHAR(20) NOT NULL CHECK(estado IN('reservado','enviado','success','failed','erro')),
 ativa BIT NOT NULL, solicitada_em DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(), atualizada_em DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
 PRIMARY KEY(pipeline_name,run_id)
 );
GO
IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID('dbo.etl_workspace_comando') AND name='UX_workspace_comando_ativo')
 CREATE UNIQUE INDEX UX_workspace_comando_ativo ON dbo.etl_workspace_comando(pipeline_name) WHERE ativa=1;
GO
CREATE OR ALTER PROCEDURE dbo.sp_workspace_reserve_run
 @name NVARCHAR(200),@run_id NVARCHAR(300),@request_hash CHAR(64),@actor NVARCHAR(100),@reprocess BIT=0
AS
BEGIN
 SET NOCOUNT ON; SET XACT_ABORT ON;
 BEGIN TRANSACTION;
 DECLARE @version UNIQUEIDENTIFIER,@pending UNIQUEIDENTIFIER,@hash CHAR(64),@active CHAR(64),@managed BIT=0,@token UNIQUEIDENTIFIER;
 SELECT @managed=1,@version=p.version_id,@pending=p.pending_operation_id,@active=p.active_hash,@hash=v.content_hash
 FROM dbo.etl_workspace_pipeline p WITH(UPDLOCK,HOLDLOCK) LEFT JOIN dbo.etl_workspace_versao v ON v.version_id=p.version_id WHERE p.pipeline_name=@name;
 IF @managed=0 BEGIN COMMIT; SELECT CAST(NULL AS UNIQUEIDENTIFIER) AS command_token,0 AS existing; RETURN; END;
 IF @pending IS NOT NULL OR @version IS NULL OR @hash IS NULL OR @active IS NULL
 BEGIN ROLLBACK; THROW 51146,'Publicacao nao confirmada.',1; END;
 IF EXISTS(SELECT 1 FROM dbo.etl_workspace_comando WITH(UPDLOCK,HOLDLOCK) WHERE pipeline_name=@name AND run_id=@run_id AND ativa=1)
 BEGIN
  IF @reprocess=1 OR NOT EXISTS(SELECT 1 FROM dbo.etl_workspace_comando WHERE pipeline_name=@name AND run_id=@run_id AND request_hash=@request_hash AND ator=@actor AND tipo='execute' AND version_id=@version AND content_hash=@hash)
  BEGIN ROLLBACK; THROW 51146,'Comando concorrente ou identidade reutilizada.',1; END;
  SELECT @token=command_token FROM dbo.etl_workspace_comando WHERE pipeline_name=@name AND run_id=@run_id;
  COMMIT; SELECT @token AS command_token,1 AS existing; RETURN;
 END;
 IF EXISTS(SELECT 1 FROM dbo.etl_workspace_comando WITH(UPDLOCK,HOLDLOCK) WHERE pipeline_name=@name AND ativa=1)
 OR EXISTS(SELECT 1 FROM dbo.etl_workspace_execucao WITH(UPDLOCK,HOLDLOCK) WHERE pipeline_name=@name AND ativa=1)
 OR EXISTS(SELECT 1 FROM dbo.etl_pipeline_execucao WITH(UPDLOCK,HOLDLOCK) WHERE pipeline_name=@name AND status IN('EXECUTANDO','RUNNING','QUEUED','AGUARDANDO','AGUARDANDO_DEPENDENCIA'))
 BEGIN ROLLBACK; THROW 51146,'Execucao ou comando ativo.',1; END;
 IF @reprocess=1 AND EXISTS(SELECT 1 FROM dbo.etl_workspace_comando WHERE pipeline_name=@name AND run_id=@run_id AND estado='erro')
 BEGIN ROLLBACK; THROW 51146,'Comando sem confirmacao: crie uma nova corrida.',1; END;
 IF @reprocess=1 AND NOT EXISTS(SELECT 1 FROM dbo.etl_workspace_execucao WHERE pipeline_name=@name AND run_id=@run_id AND version_id=@version AND content_hash=@hash)
 BEGIN ROLLBACK; THROW 51146,'Corrida sem vinculo com a versao atual.',1; END;
 IF @reprocess=0 AND EXISTS(SELECT 1 FROM dbo.etl_workspace_comando WHERE pipeline_name=@name AND run_id=@run_id)
 BEGIN
  IF NOT EXISTS(SELECT 1 FROM dbo.etl_workspace_comando WHERE pipeline_name=@name AND run_id=@run_id AND request_hash=@request_hash AND ator=@actor AND tipo='execute')
  BEGIN ROLLBACK; THROW 51146,'Identidade de comando reutilizada.',1; END;
  SELECT @token=command_token FROM dbo.etl_workspace_comando WHERE pipeline_name=@name AND run_id=@run_id;
  COMMIT; SELECT @token AS command_token,1 AS existing; RETURN;
 END;
 SET @token=NEWID();
 IF EXISTS(SELECT 1 FROM dbo.etl_workspace_comando WHERE pipeline_name=@name AND run_id=@run_id)
  UPDATE dbo.etl_workspace_comando SET command_token=@token,version_id=@version,content_hash=@hash,active_hash=@active,request_hash=@request_hash,tipo='reprocess',ator=@actor,estado='reservado',ativa=1,solicitada_em=SYSUTCDATETIME(),atualizada_em=SYSUTCDATETIME() WHERE pipeline_name=@name AND run_id=@run_id;
 ELSE
  INSERT dbo.etl_workspace_comando(pipeline_name,run_id,command_token,version_id,content_hash,active_hash,request_hash,tipo,ator,estado,ativa)
  VALUES(@name,@run_id,@token,@version,@hash,@active,@request_hash,IIF(@reprocess=1,'reprocess','execute'),@actor,'reservado',1);
 COMMIT; SELECT @token AS command_token,0 AS existing;
END;
GO
CREATE OR ALTER TRIGGER dbo.tr_workspace_command_publication ON dbo.etl_workspace_pipeline AFTER INSERT,UPDATE AS
BEGIN
 SET NOCOUNT ON;
 IF EXISTS(SELECT 1 FROM inserted i JOIN dbo.etl_workspace_comando c WITH(UPDLOCK,HOLDLOCK) ON c.pipeline_name=i.pipeline_name WHERE i.pending_operation_id IS NOT NULL AND c.ativa=1)
 THROW 51146,'Comando reservado: publicacao recusada.',1;
END;
GO
CREATE OR ALTER PROCEDURE dbo.sp_workspace_guard_run
 @name NVARCHAR(200),@run_id NVARCHAR(300),@version UNIQUEIDENTIFIER=NULL,@hash CHAR(64)=NULL,@queued_at DATETIME2=NULL
AS
BEGIN
 SET NOCOUNT ON; SET XACT_ABORT ON;
 BEGIN TRANSACTION;
 DECLARE @current UNIQUEIDENTIFIER,@pending UNIQUEIDENTIFIER,@expected CHAR(64),@managed BIT=0,@confirmed_at DATETIME2;
 SELECT @managed=1,@current=p.version_id,@pending=p.pending_operation_id,@expected=v.content_hash,@confirmed_at=o.atualizada_em FROM dbo.etl_workspace_pipeline p WITH(UPDLOCK,HOLDLOCK) LEFT JOIN dbo.etl_workspace_versao v ON v.version_id=p.version_id LEFT JOIN dbo.etl_workspace_publicacao o ON o.version_id=p.version_id AND o.estado='publicado' WHERE p.pipeline_name=@name;
 IF @managed=0 BEGIN COMMIT; RETURN; END;
 IF @pending IS NOT NULL OR @current IS NULL OR @version IS NULL OR @version<>@current OR @hash IS NULL OR @hash<>@expected
 BEGIN ROLLBACK; THROW 51145,'Publicacao pendente ou versao de execucao divergente.',1; END;
 IF EXISTS(SELECT 1 FROM dbo.etl_workspace_comando WITH(UPDLOCK,HOLDLOCK) WHERE pipeline_name=@name AND ativa=1 AND run_id<>@run_id)
 OR EXISTS(SELECT 1 FROM dbo.etl_workspace_execucao WITH(UPDLOCK,HOLDLOCK) WHERE pipeline_name=@name AND ativa=1 AND run_id<>@run_id)
 BEGIN ROLLBACK; THROW 51146,'Outra corrida ou comando ativo.',1; END;
 IF EXISTS(SELECT 1 FROM dbo.etl_workspace_comando WHERE pipeline_name=@name AND run_id=@run_id AND (version_id<>@current OR content_hash<>@expected OR estado='erro'))
 BEGIN ROLLBACK; THROW 51146,'Comando expirado ou versao reservada divergente.',1; END;
 IF @run_id LIKE N'workspace[_][_]%'
 AND NOT EXISTS(SELECT 1 FROM dbo.etl_workspace_comando WHERE pipeline_name=@name AND run_id=@run_id AND version_id=@current AND content_hash=@expected AND estado<>'erro')
 BEGIN ROLLBACK; THROW 51146,'Comando do workspace sem reserva valida.',1; END;
 IF NOT EXISTS(SELECT 1 FROM dbo.etl_workspace_execucao WITH(UPDLOCK,HOLDLOCK) WHERE pipeline_name=@name AND run_id=@run_id)
 BEGIN
 -- queued_at vem do registro confiável do Airflow, jamais da conf/data lógica.
 -- Uma DAG recém-parsed não pode adotar um comando anterior à sua confirmação.
 IF @queued_at IS NULL OR @confirmed_at IS NULL OR @queued_at<=@confirmed_at
 BEGIN ROLLBACK; THROW 51145,'Comando anterior a confirmacao da versao; crie uma nova corrida.',1; END;
 INSERT dbo.etl_workspace_execucao(pipeline_name,run_id,version_id,content_hash) VALUES(@name,@run_id,@current,@expected);
 END;
 ELSE
 BEGIN
  IF EXISTS(SELECT 1 FROM dbo.etl_workspace_execucao WHERE pipeline_name=@name AND run_id=@run_id AND (version_id<>@current OR content_hash<>@expected))
  BEGIN ROLLBACK; THROW 51145,'Versao original da corrida divergente; crie uma nova corrida.',1; END;
  UPDATE dbo.etl_workspace_execucao SET ativa=1,encerrada_em=NULL,activity_epoch=activity_epoch+1 WHERE pipeline_name=@name AND run_id=@run_id;
 END;
 COMMIT;
END;
GO
