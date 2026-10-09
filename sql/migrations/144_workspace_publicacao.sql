-- F4: intenção durável, identidade collation legada e fronteiras SQL.
SET NOCOUNT ON;
SET XACT_ABORT ON;
IF OBJECT_ID('dbo.etl_workspace_rascunho','U') IS NULL THROW 50144,'Aplique migration 141 antes da 144.',1;
GO
IF COL_LENGTH('dbo.etl_workspace_rascunho','base_active_hash') IS NULL
 ALTER TABLE dbo.etl_workspace_rascunho ADD base_active_hash CHAR(64) NULL;
GO
IF OBJECT_ID('dbo.etl_workspace_publicacao','U') IS NULL
BEGIN
 CREATE TABLE dbo.etl_workspace_publicacao (
 operation_id UNIQUEIDENTIFIER NOT NULL PRIMARY KEY,
 draft_id UNIQUEIDENTIFIER NOT NULL REFERENCES dbo.etl_workspace_rascunho(draft_id),
 version_id UNIQUEIDENTIFIER NOT NULL REFERENCES dbo.etl_workspace_versao(version_id),
 pipeline_name NVARCHAR(200) NOT NULL,
 revision BIGINT NOT NULL, fence BIGINT NOT NULL, ator NVARCHAR(100) NOT NULL,
 expected_active_hash CHAR(64) NULL, projection_hash CHAR(64) NULL, inherited_projection_hash CHAR(64) NULL,
 estado VARCHAR(20) NOT NULL DEFAULT 'pendente' CHECK(estado IN('pendente','projetado','gerando','publicado','erro')),
 tentativas INT NOT NULL DEFAULT 0, erro_resumido NVARCHAR(1000) NULL,
 factory_run_id VARCHAR(100) NOT NULL UNIQUE,
 criada_em DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(), atualizada_em DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
 processing_until DATETIME2 NULL, processing_token UNIQUEIDENTIFIER NULL, retry_requested BIT NOT NULL DEFAULT 0,
 CONSTRAINT UQ_workspace_publicacao_revision UNIQUE(draft_id,revision)
 );
END;
GO
IF COL_LENGTH('dbo.etl_workspace_publicacao','processing_token') IS NULL ALTER TABLE dbo.etl_workspace_publicacao ADD processing_token UNIQUEIDENTIFIER NULL;
IF COL_LENGTH('dbo.etl_workspace_publicacao','retry_requested') IS NULL ALTER TABLE dbo.etl_workspace_publicacao ADD retry_requested BIT NOT NULL DEFAULT 0;
IF COL_LENGTH('dbo.etl_workspace_publicacao','inherited_projection_hash') IS NULL ALTER TABLE dbo.etl_workspace_publicacao ADD inherited_projection_hash CHAR(64) NULL;
GO
IF OBJECT_ID('dbo.etl_workspace_pipeline','U') IS NULL
 CREATE TABLE dbo.etl_workspace_pipeline (
 pipeline_name NVARCHAR(200) NOT NULL PRIMARY KEY,
 version_id UNIQUEIDENTIFIER NULL REFERENCES dbo.etl_workspace_versao(version_id),
 pending_operation_id UNIQUEIDENTIFIER NULL REFERENCES dbo.etl_workspace_publicacao(operation_id),
 active_hash CHAR(64) NULL, criada_em DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
 );
GO
IF OBJECT_ID('dbo.etl_workspace_execucao','U') IS NULL
 CREATE TABLE dbo.etl_workspace_execucao (
 pipeline_name NVARCHAR(200) NOT NULL, run_id NVARCHAR(300) NOT NULL,
 version_id UNIQUEIDENTIFIER NOT NULL, content_hash CHAR(64) NOT NULL,
 activity_epoch BIGINT NOT NULL DEFAULT 1, ativa BIT NOT NULL DEFAULT 1, iniciada_em DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(), encerrada_em DATETIME2 NULL,
 PRIMARY KEY(pipeline_name,run_id)
 );
GO
IF COL_LENGTH('dbo.etl_workspace_execucao','activity_epoch') IS NULL ALTER TABLE dbo.etl_workspace_execucao ADD activity_epoch BIGINT NOT NULL DEFAULT 1;
GO
-- Nome de constraint da 141 era gerado pelo SQL Server. Migrar pelo catálogo.
DECLARE @ck sysname;
SELECT @ck=name FROM sys.check_constraints WHERE parent_object_id=OBJECT_ID('dbo.etl_workspace_rascunho') AND definition LIKE '%estado%' AND definition NOT LIKE '%publicado%';
IF @ck IS NOT NULL
BEGIN
 DECLARE @drop_constraint NVARCHAR(MAX)=N'ALTER TABLE dbo.etl_workspace_rascunho DROP CONSTRAINT '+QUOTENAME(@ck);
 EXEC sp_executesql @drop_constraint;
END;
IF NOT EXISTS(SELECT 1 FROM sys.check_constraints WHERE parent_object_id=OBJECT_ID('dbo.etl_workspace_rascunho') AND name='CK_workspace_rascunho_estado')
 ALTER TABLE dbo.etl_workspace_rascunho ADD CONSTRAINT CK_workspace_rascunho_estado CHECK(estado IN('ativo','descartado','publicado'));
GO
IF OBJECT_ID('dbo.etl_perfil_permissao','U') IS NOT NULL
 EXEC(N'IF NOT EXISTS(SELECT 1 FROM dbo.etl_perfil_permissao WHERE perfil_nome=''admin'' AND recurso=''acao_publicar'')
 INSERT dbo.etl_perfil_permissao(perfil_nome,recurso,criado_por) VALUES(''admin'',''acao_publicar'',''migration144'');');
GO
CREATE OR ALTER PROCEDURE dbo.sp_workspace_active_hash @name NVARCHAR(200) AS
BEGIN
 SET NOCOUNT ON;
 -- Somente hash sai do SQL; cifras nunca são transportadas ao .NET.
 DECLARE @payload NVARCHAR(MAX)=N'',@table sysname,@cols NVARCHAR(MAX),@query NVARCHAR(MAX),@rows NVARCHAR(MAX),@order NVARCHAR(MAX);
 IF NOT EXISTS(SELECT 1 FROM dbo.etl_pipeline WHERE pipeline_name=@name) BEGIN SELECT CAST(NULL AS CHAR(64)) AS active_hash; RETURN; END;
 DECLARE tables CURSOR LOCAL FAST_FORWARD FOR SELECT name FROM (VALUES
 ('etl_pipeline'),('etl_pipeline_job'),('etl_pipeline_param'),('etl_pipeline_job_param'),('etl_valida_arquivo_no'),('etl_valida_arquivo_config'),('etl_pipeline_dependencia'),('etl_pipeline_owner')) t(name) ORDER BY name;
 OPEN tables; FETCH NEXT FROM tables INTO @table;
 WHILE @@FETCH_STATUS=0
 BEGIN
  IF OBJECT_ID('dbo.'+@table,'U') IS NOT NULL
  BEGIN
   SELECT @cols=STRING_AGG(CAST(QUOTENAME(name) AS NVARCHAR(MAX)),',') WITHIN GROUP(ORDER BY column_id)
    FROM sys.columns WHERE object_id=OBJECT_ID('dbo.'+@table) AND name NOT IN('dag_criada','last_execution','updated_at','created_at','atualizado_em','criado_em','dag_config_pendente_em');
   SET @order=CASE @table WHEN 'etl_pipeline_job' THEN '[job_name]' WHEN 'etl_pipeline_param' THEN '[param_name]' WHEN 'etl_pipeline_job_param' THEN '[job_name],[param_name]' WHEN 'etl_valida_arquivo_no' THEN '[task_id]' WHEN 'etl_valida_arquivo_config' THEN '[task_id],[entrada_id]' WHEN 'etl_pipeline_dependencia' THEN '[depende_de]' ELSE '[pipeline_name]' END;
   SET @query=N'SELECT @rows=(SELECT '+@cols+' FROM dbo.'+QUOTENAME(@table)+' WHERE pipeline_name=@name ORDER BY '+@order+' FOR JSON PATH,INCLUDE_NULL_VALUES)';
   EXEC sp_executesql @query,N'@name NVARCHAR(200),@rows NVARCHAR(MAX) OUTPUT',@name,@rows OUTPUT;
   SET @payload=@payload+@table+CHAR(10)+COALESCE(@rows,N'[]')+CHAR(10);
  END;
  FETCH NEXT FROM tables INTO @table;
 END;
 CLOSE tables; DEALLOCATE tables;
 SELECT LOWER(CONVERT(CHAR(64),HASHBYTES('SHA2_256',@payload),2)) AS active_hash;
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
IF OBJECT_ID('dbo.etl_pipeline_execucao','U') IS NOT NULL
 EXEC(N'CREATE OR ALTER TRIGGER dbo.tr_workspace_guard_reserva ON dbo.etl_pipeline_execucao AFTER INSERT,UPDATE AS
 BEGIN SET NOCOUNT ON;
 IF EXISTS(SELECT 1 FROM inserted i JOIN dbo.etl_workspace_pipeline p WITH(UPDLOCK,HOLDLOCK) ON p.pipeline_name=i.pipeline_name
 WHERE p.pending_operation_id IS NOT NULL AND i.status IN(''EXECUTANDO'',''RUNNING'',''QUEUED'',''AGUARDANDO'',''AGUARDANDO_DEPENDENCIA''))
 THROW 51145,''Publicacao pendente: reserva de execucao recusada.'',1;
 END;');
GO
DECLARE @table sysname,@protected NVARCHAR(MAX),@sql NVARCHAR(MAX);
DECLARE guarded CURSOR LOCAL FAST_FORWARD FOR SELECT name FROM (VALUES
 ('etl_pipeline'),('etl_pipeline_job'),('etl_pipeline_param'),('etl_pipeline_job_param'),('etl_valida_arquivo_no'),('etl_valida_arquivo_config'),('etl_pipeline_dependencia'),('etl_pipeline_owner'),('etl_job_lineage')) t(name);
OPEN guarded; FETCH NEXT FROM guarded INTO @table;
WHILE @@FETCH_STATUS=0
BEGIN
 IF OBJECT_ID('dbo.'+@table,'U') IS NOT NULL
 BEGIN
  SELECT @protected=STRING_AGG(CAST('UPDATE('+QUOTENAME(name)+')' AS NVARCHAR(MAX)),' OR ') FROM sys.columns WHERE object_id=OBJECT_ID('dbo.'+@table) AND name NOT IN('dag_criada','last_execution','updated_at','created_at','atualizado_em','criado_em','dag_config_pendente_em');
  SET @sql=N'CREATE OR ALTER TRIGGER dbo.'+QUOTENAME('tr_workspace_guard_'+@table)+' ON dbo.'+QUOTENAME(@table)+' AFTER INSERT,UPDATE,DELETE AS BEGIN SET NOCOUNT ON;
   IF NOT EXISTS(SELECT 1 FROM inserted) AND NOT EXISTS(SELECT 1 FROM deleted) RETURN;
   IF EXISTS(SELECT 1 FROM inserted) AND EXISTS(SELECT 1 FROM deleted) AND NOT('+@protected+') RETURN;
   IF EXISTS(SELECT 1 FROM (SELECT pipeline_name FROM inserted UNION SELECT pipeline_name FROM deleted) n JOIN dbo.etl_workspace_pipeline p WITH(UPDLOCK,HOLDLOCK) ON p.pipeline_name=n.pipeline_name WHERE NOT EXISTS(SELECT 1 FROM dbo.etl_workspace_publicacao o WHERE o.operation_id=p.pending_operation_id AND o.operation_id=TRY_CONVERT(UNIQUEIDENTIFIER,SESSION_CONTEXT(N''workspace_operation'')) AND o.estado=''pendente'')) THROW 51144,''Pipeline gerido: alteracao somente pelo workspace.'',1;
  END;';
  EXEC sp_executesql @sql;
 END;
 FETCH NEXT FROM guarded INTO @table;
END;
CLOSE guarded; DEALLOCATE guarded;
GO
