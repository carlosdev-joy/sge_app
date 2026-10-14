using System.Data;
using System.Text.Json;
using System.Text.RegularExpressions;
using Microsoft.Data.SqlClient;
using Orquestra.Application.Drafts;
using Orquestra.Application.Security;
using Orquestra.Infrastructure.Drafts;
using Orquestra.Infrastructure.Security;
using Xunit;
namespace Orquestra.Tests;
public sealed class PublicationSqlTests
{
 [SqlFact]
 public async Task IntentFencingImmutableVersionRuntimeGateAndReopenedRunUseRealSql()
 {
  var database="OrquestraF4Test_"+Guid.NewGuid().ToString("N");
  var options=new WorkspaceSqlOptions(Environment.GetEnvironmentVariable("WORKSPACE_TEST_SQL_SERVER")??"127.0.0.1,1433",database,Environment.GetEnvironmentVariable("WORKSPACE_TEST_SQL_USER")??"sa",Environment.GetEnvironmentVariable("WORKSPACE_TEST_SQL_PASSWORD")!,true);
  await using var master=new SqlConnection((options with{Database="master"}).ConnectionString());await master.OpenAsync();var created=false;
  try{
   await Execute(master,$"CREATE DATABASE [{database}] COLLATE SQL_Latin1_General_CP1_CI_AS");created=true;await using var c=new SqlConnection(options.ConnectionString());await c.OpenAsync();
   await Execute(c,"""
    CREATE TABLE dbo.etl_sessao(token_hash CHAR(64) PRIMARY KEY,matricula VARCHAR(20),expira_em DATETIME);
    CREATE TABLE dbo.etl_pipeline(pipeline_name NVARCHAR(200) PRIMARY KEY,project_name NVARCHAR(100),domain NVARCHAR(100),schedule_type VARCHAR(50),active BIT,dag_criada BIT,last_execution DATETIME,updated_at DATETIME);
    CREATE TABLE dbo.etl_pipeline_job(pipeline_name NVARCHAR(200),job_name NVARCHAR(200),job_type VARCHAR(100),job_command NVARCHAR(MAX),execution_order INT,depends_on_jobs NVARCHAR(MAX),layout_x FLOAT,layout_y FLOAT,PRIMARY KEY(pipeline_name,job_name));
    CREATE TABLE dbo.etl_pipeline_param(pipeline_name NVARCHAR(200),param_name VARCHAR(128) COLLATE Latin1_General_BIN2,param_type VARCHAR(30),param_value NVARCHAR(MAX));
    CREATE TABLE dbo.etl_pipeline_job_param(pipeline_name NVARCHAR(200),job_name NVARCHAR(200),param_name VARCHAR(128) COLLATE Latin1_General_BIN2,param_type VARCHAR(30),param_value NVARCHAR(MAX));
    CREATE TABLE dbo.etl_valida_arquivo_no(pipeline_name NVARCHAR(200),task_id NVARCHAR(200),ssh_conn_id VARCHAR(100));
    CREATE TABLE dbo.etl_valida_arquivo_config(pipeline_name NVARCHAR(200),task_id NVARCHAR(200),entrada_id UNIQUEIDENTIFIER);
    CREATE TABLE dbo.etl_pipeline_execucao(pipeline_name NVARCHAR(200),status VARCHAR(100));
    CREATE TABLE dbo.etl_job_lineage(pipeline_name NVARCHAR(200),job_name NVARCHAR(200));
    INSERT dbo.etl_sessao VALUES(REPLICATE('a',64),'ALICE',DATEADD(hour,1,GETDATE()));
    INSERT dbo.etl_pipeline VALUES('PUB','Projeto','Dominio','on_demand',1,1,NULL,NULL),('DRIFT','Projeto','Dominio','on_demand',1,1,NULL,NULL);
    INSERT dbo.etl_pipeline_job VALUES('PUB','Etapa','shell','true',1,NULL,10,20),('DRIFT','Etapa','shell','true',1,NULL,10,20);
    INSERT dbo.etl_pipeline_param VALUES('PUB','SEGREDO','Encrypted','cipher-never-return'),('PUB','segredo','Encrypted','other-cipher');
    """);
   var folder=Path.GetDirectoryName(Environment.GetEnvironmentVariable("WORKSPACE_TEST_SCHEMA_PATH"))!;
   foreach(var name in new[]{"141_workspace_rascunhos.sql","144_workspace_publicacao.sql","144_workspace_publicacao.sql","146_workspace_comandos.sql","146_workspace_comandos.sql","159_workspace_lineage_hash.sql","159_workspace_lineage_hash.sql"})foreach(var batch in Regex.Split(await File.ReadAllTextAsync(Path.Combine(folder,name)),@"^\s*GO\s*$",RegexOptions.Multiline|RegexOptions.IgnoreCase))if(!string.IsNullOrWhiteSpace(batch))await Execute(c,batch);
   var repository=new SqlDraftRepository(options);Assert.True(await repository.PublicationSchemaAsync(default));
   var draft=await repository.ImportAsync("pub",Actor(),default);Assert.DoesNotContain("cipher-never",JsonSerializer.Serialize(draft,DraftValidation.Json));
   var lease=await repository.LeaseAsync(draft.DraftId,new(),Actor(),default);var command=new PublicationCommand(Guid.NewGuid(),draft.Revision,lease.Fence);
   Assert.Equal("permission_denied",(await Assert.ThrowsAsync<WorkspaceException>(()=>repository.PublishAsync(draft.DraftId,command,Actor(false),default))).Code);
   Assert.Equal("lease_conflict",(await Assert.ThrowsAsync<WorkspaceException>(()=>repository.PublishAsync(draft.DraftId,command with{Fence=lease.Fence+1},Actor(),default))).Code);
   await Execute(c,"INSERT dbo.etl_pipeline_execucao VALUES('PUB','RUNNING')");Assert.Equal("execution_active",(await Assert.ThrowsAsync<WorkspaceException>(()=>repository.PublishAsync(draft.DraftId,command,Actor(),default))).Code);await Execute(c,"UPDATE dbo.etl_pipeline_execucao SET status='AGUARDANDO_DEPENDENCIA'");Assert.Equal("execution_active",(await Assert.ThrowsAsync<WorkspaceException>(()=>repository.PublishAsync(draft.DraftId,command,Actor(),default))).Code);await Execute(c,"DELETE dbo.etl_pipeline_execucao");
   var before=(string)(await Scalar(c,"EXEC dbo.sp_workspace_active_hash @name='PUB',@include_lineage=1"))!;
   var op=await repository.PublishAsync(draft.DraftId,command,Actor(),default);Assert.Equal("pendente",op.State);Assert.Equal(op,await repository.PublishAsync(draft.DraftId,command,Actor(),default));
   Assert.Equal("operation_conflict",(await Assert.ThrowsAsync<WorkspaceException>(()=>repository.PublishAsync(draft.DraftId,command with{OperationId=Guid.NewGuid()},Actor(),default))).Code);
   var pendingContext=await repository.ContextAsync("PUB",Actor(),true,default);Assert.Equal("true",pendingContext.Published!.Value.GetProperty("definition").GetProperty("nodes")[0].GetProperty("configuration").GetProperty("legacyJob").GetProperty("job_command").GetString());
   Assert.Equal("publication_pending",(await Assert.ThrowsAsync<WorkspaceException>(()=>repository.SaveAsync(draft.DraftId,new(draft.Revision,lease.Fence,draft.Definition,draft.Layout),Actor(),default))).Code);
   Assert.Equal(51144,(await Assert.ThrowsAsync<SqlException>(()=>Execute(c,"UPDATE dbo.etl_pipeline_job SET job_command='forbidden' WHERE pipeline_name='pub '"))).Number);
   await Execute(c,"UPDATE dbo.etl_pipeline SET last_execution=GETDATE(),updated_at=GETDATE(),dag_criada=0 WHERE pipeline_name='PUB'");Assert.Equal(before,await Scalar(c,"EXEC dbo.sp_workspace_active_hash @name='PUB'"));
   Assert.Equal(51145,(await Assert.ThrowsAsync<SqlException>(()=>Execute(c,"INSERT dbo.etl_pipeline_execucao VALUES('PUB','AGUARDANDO_DEPENDENCIA')"))).Number);
   Assert.Equal(51145,(await Assert.ThrowsAsync<SqlException>(()=>Execute(c,"EXEC dbo.sp_workspace_guard_run @name='PUB',@run_id='run'"))).Number);
   Assert.Equal(51001,(await Assert.ThrowsAsync<SqlException>(()=>Execute(c,$"UPDATE dbo.etl_workspace_versao SET content_hash=REPLICATE('0',64) WHERE version_id='{op.VersionId}'"))).Number);
   Assert.Contains(await repository.VersionsAsync("PUB",default),v=>v.VersionId==op.VersionId&&v.State=="pendente");
   Assert.Equal(404,(await Assert.ThrowsAsync<WorkspaceException>(()=>repository.RestoreAsync("PUB",op.VersionId,Actor(),default))).StatusCode);
   await Execute(c,$"EXEC sp_set_session_context @key=N'workspace_operation',@value=N'{op.OperationId}'; UPDATE dbo.etl_pipeline_job SET job_command='changed' WHERE pipeline_name='PUB'; EXEC sp_set_session_context @key=N'workspace_operation',@value=NULL; UPDATE dbo.etl_workspace_publicacao SET estado='publicado' WHERE operation_id='{op.OperationId}'; UPDATE dbo.etl_workspace_pipeline SET version_id='{op.VersionId}',pending_operation_id=NULL WHERE pipeline_name='PUB'; UPDATE dbo.etl_workspace_rascunho SET estado='publicado' WHERE draft_id='{draft.DraftId}'");
   var version=(await repository.VersionsAsync("PUB",default)).Single(v=>v.VersionId==op.VersionId);
   Assert.Equal(51145,(await Assert.ThrowsAsync<SqlException>(()=>Execute(c,$"EXEC dbo.sp_workspace_guard_run @name='PUB',@run_id='old-command',@version='{op.VersionId}',@hash='{version.ContentHash}',@queued_at='2020-01-01'"))).Number);
   var guard=$"DECLARE @queued DATETIME2=SYSUTCDATETIME();EXEC dbo.sp_workspace_guard_run @name='PUB',@run_id='run',@version='{op.VersionId}',@hash='{version.ContentHash}',@queued_at=@queued";
   await Execute(c,guard);Assert.Equal(true,await Scalar(c,"SELECT ativa FROM dbo.etl_workspace_execucao WHERE run_id='run'"));
   var epoch=(long)(await Scalar(c,"SELECT activity_epoch FROM dbo.etl_workspace_execucao WHERE run_id='run'"))!;await Execute(c,"UPDATE dbo.etl_workspace_execucao SET ativa=0 WHERE run_id='run'");await Execute(c,guard);
   await Execute(c,$"UPDATE dbo.etl_workspace_execucao SET ativa=0 WHERE run_id='run' AND activity_epoch={epoch}");Assert.Equal(true,await Scalar(c,"SELECT ativa FROM dbo.etl_workspace_execucao WHERE run_id='run'"));
   Assert.Equal(51145,(await Assert.ThrowsAsync<SqlException>(()=>Execute(c,$"EXEC dbo.sp_workspace_guard_run @name='PUB',@run_id='run',@version='{Guid.NewGuid()}',@hash='{version.ContentHash}'"))).Number);
   // F5: duas conexões reais disputam uma única reserva durável.
   await Execute(c,"UPDATE dbo.etl_workspace_execucao SET ativa=0 WHERE pipeline_name='PUB';UPDATE dbo.etl_workspace_pipeline SET active_hash=REPLICATE('b',64) WHERE pipeline_name='PUB'");
   async Task<int> Reserve(string runId) { await using var other=new SqlConnection(options.ConnectionString());await other.OpenAsync();try{await Execute(other,$"EXEC dbo.sp_workspace_reserve_run @name='PUB',@run_id='{runId}',@request_hash='{new string('c',64)}',@actor='ALICE'");return 0;}catch(SqlException e){return e.Number;} }
   var races=await Task.WhenAll(Reserve("workspace__first"),Reserve("workspace__second"));Assert.Single(races,v=>v==0);Assert.Single(races,v=>v==51146);
   Assert.Equal(1,(int)(await Scalar(c,"SELECT COUNT(*) FROM dbo.etl_workspace_comando WHERE pipeline_name='PUB' AND ativa=1"))!);
   var selected=(string)(await Scalar(c,"SELECT run_id FROM dbo.etl_workspace_comando WHERE pipeline_name='PUB' AND ativa=1"))!;
   Assert.Equal(51146,(await Assert.ThrowsAsync<SqlException>(()=>Execute(c,$"UPDATE dbo.etl_workspace_pipeline SET pending_operation_id='{op.OperationId}' WHERE pipeline_name='PUB'"))).Number);
   var commandGuard=$"DECLARE @queued DATETIME2=SYSUTCDATETIME();EXEC dbo.sp_workspace_guard_run @name='PUB',@run_id='{selected}',@version='{op.VersionId}',@hash='{version.ContentHash}',@queued_at=@queued";
   await Execute(c,commandGuard);await Execute(c,"UPDATE dbo.etl_workspace_execucao SET ativa=0 WHERE pipeline_name='PUB';UPDATE dbo.etl_workspace_comando SET estado='erro',ativa=0 WHERE pipeline_name='PUB'");
   Assert.Equal(51146,(await Assert.ThrowsAsync<SqlException>(()=>Execute(c,commandGuard))).Number);
   Assert.Equal(51146,(await Assert.ThrowsAsync<SqlException>(()=>Execute(c,$"EXEC dbo.sp_workspace_reserve_run @name='PUB',@run_id='{selected}',@request_hash='{new string('d',64)}',@actor='ALICE',@reprocess=1"))).Number);
   await Execute(c,$"EXEC dbo.sp_workspace_reserve_run @name='PUB',@run_id='run',@request_hash='{new string('d',64)}',@actor='ALICE',@reprocess=1");
   Assert.Equal(true,await Scalar(c,"SELECT ativa FROM dbo.etl_workspace_comando WHERE run_id='run'"));await Execute(c,"UPDATE dbo.etl_workspace_comando SET ativa=0,estado='success' WHERE pipeline_name='PUB'");
   var restored=await repository.RestoreAsync("PUB",op.VersionId,Actor(),default);Assert.Equal("true",restored.Definition.Nodes[0].Configuration.GetProperty("legacyJob").GetProperty("job_command").GetString());
   await Execute(c,"INSERT dbo.etl_pipeline VALUES('FIX','Projeto','Dominio','on_demand',1,1,NULL,NULL);INSERT dbo.etl_pipeline_job VALUES('FIX','Etapa','shell','true',1,NULL,10,20)");
   var broken=await repository.ImportAsync("FIX",Actor(),default);var fixLease=await repository.LeaseAsync(broken.DraftId,new(),Actor(),default);var first=await repository.PublishAsync(broken.DraftId,new(Guid.NewGuid(),broken.Revision,fixLease.Fence),Actor(),default);
   await Execute(c,$"EXEC sp_set_session_context @key=N'workspace_operation',@value=N'{first.OperationId}';UPDATE dbo.etl_pipeline_job SET job_command='broken' WHERE pipeline_name='FIX';EXEC sp_set_session_context @key=N'workspace_operation',@value=NULL");
   var projected=(string)(await Scalar(c,"EXEC dbo.sp_workspace_active_hash @name='FIX'"))!;await Execute(c,$"UPDATE dbo.etl_workspace_publicacao SET projection_hash='{projected}',estado='erro' WHERE operation_id='{first.OperationId}'");
   Assert.Equal("publication_pending",(await Assert.ThrowsAsync<WorkspaceException>(()=>repository.DiscardAsync(broken.DraftId,new(broken.Revision,fixLease.Fence),Actor(),default))).Code);
   var fixedDraft=await repository.SaveAsync(broken.DraftId,new(broken.Revision,fixLease.Fence,broken.Definition,broken.Layout),Actor(),default);var correction=await repository.PublishAsync(broken.DraftId,new(Guid.NewGuid(),fixedDraft.Revision,fixLease.Fence),Actor(),default);
   Assert.NotEqual(first.VersionId,correction.VersionId);Assert.Equal(correction.OperationId,await Scalar(c,"SELECT pending_operation_id FROM dbo.etl_workspace_pipeline WHERE pipeline_name='FIX'"));Assert.Equal("erro",(await repository.PublicationAsync(first.OperationId,default)).State);
   Assert.Equal(projected,await Scalar(c,$"SELECT inherited_projection_hash FROM dbo.etl_workspace_publicacao WHERE operation_id='{correction.OperationId}'"));await Execute(c,$"UPDATE dbo.etl_workspace_publicacao SET estado='erro' WHERE operation_id='{correction.OperationId}'");
   var adapterSource=await File.ReadAllTextAsync(Path.Combine(folder,"../../api/services/workspace_publication.py"));
   foreach(var constant in new[]{"REMOVE_UNPROJECTED_REGISTRY","RELEASE_UNPROJECTED_GATE"}){var statement=Regex.Match(adapterSource,constant+" = "+"\"\"\""+"(.*?)"+"\"\"\"",RegexOptions.Singleline).Groups[1].Value;Assert.NotEmpty(statement);await using var cleanup=new SqlCommand(statement.Replace("?","@operation"),c);cleanup.Parameters.AddWithValue("@operation",correction.OperationId);await cleanup.ExecuteNonQueryAsync();}
   Assert.Equal(correction.OperationId,await Scalar(c,"SELECT pending_operation_id FROM dbo.etl_workspace_pipeline WHERE pipeline_name='FIX'"));Assert.Equal(51145,(await Assert.ThrowsAsync<SqlException>(()=>Execute(c,"EXEC dbo.sp_workspace_guard_run @name='FIX',@run_id='blocked-correction'"))).Number);
   var drift=await repository.ImportAsync("DRIFT",Actor(),default);var driftLease=await repository.LeaseAsync(drift.DraftId,new(),Actor(),default);await Execute(c,"UPDATE dbo.etl_pipeline_job SET job_command='changed' WHERE pipeline_name='DRIFT'");Assert.Equal("active_hash_conflict",(await Assert.ThrowsAsync<WorkspaceException>(()=>repository.PublishAsync(drift.DraftId,new(Guid.NewGuid(),drift.Revision,driftLease.Fence),Actor(),default))).Code);
  }finally{SqlConnection.ClearAllPools();if(created)await Execute(master,$"ALTER DATABASE [{database}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [{database}]");}
 }
 // active_hash (projeção nas tabelas SQL) e content_hash (desenho da versão) são domínios distintos:
 // a publicação confirmada expõe o par mesmo com os dois diferentes; pendente ou sem hash ativo, não.
 [SqlFact]
 public async Task ContextExposesConfirmedPairWhenActiveHashDiffersFromContentHash()
 {
  var database="OrquestraF3Ctx_"+Guid.NewGuid().ToString("N");
  var options=new WorkspaceSqlOptions(Environment.GetEnvironmentVariable("WORKSPACE_TEST_SQL_SERVER")??"127.0.0.1,1433",database,Environment.GetEnvironmentVariable("WORKSPACE_TEST_SQL_USER")??"sa",Environment.GetEnvironmentVariable("WORKSPACE_TEST_SQL_PASSWORD")!,true);
  await using var master=new SqlConnection((options with{Database="master"}).ConnectionString());await master.OpenAsync();var created=false;
  try{
   await Execute(master,$"CREATE DATABASE [{database}] COLLATE SQL_Latin1_General_CP1_CI_AS");created=true;await using var c=new SqlConnection(options.ConnectionString());await c.OpenAsync();
   await Execute(c,"""
    CREATE TABLE dbo.etl_sessao(token_hash CHAR(64) PRIMARY KEY,matricula VARCHAR(20),expira_em DATETIME);
    CREATE TABLE dbo.etl_pipeline(pipeline_name NVARCHAR(200) PRIMARY KEY,project_name NVARCHAR(100),domain NVARCHAR(100),schedule_type VARCHAR(50),active BIT,dag_criada BIT,last_execution DATETIME,updated_at DATETIME);
    CREATE TABLE dbo.etl_pipeline_job(pipeline_name NVARCHAR(200),job_name NVARCHAR(200),job_type VARCHAR(100),job_command NVARCHAR(MAX),execution_order INT,depends_on_jobs NVARCHAR(MAX),layout_x FLOAT,layout_y FLOAT,PRIMARY KEY(pipeline_name,job_name));
    CREATE TABLE dbo.etl_pipeline_param(pipeline_name NVARCHAR(200),param_name VARCHAR(128) COLLATE Latin1_General_BIN2,param_type VARCHAR(30),param_value NVARCHAR(MAX));
    CREATE TABLE dbo.etl_pipeline_job_param(pipeline_name NVARCHAR(200),job_name NVARCHAR(200),param_name VARCHAR(128) COLLATE Latin1_General_BIN2,param_type VARCHAR(30),param_value NVARCHAR(MAX));
    CREATE TABLE dbo.etl_valida_arquivo_no(pipeline_name NVARCHAR(200),task_id NVARCHAR(200),ssh_conn_id VARCHAR(100));
    CREATE TABLE dbo.etl_valida_arquivo_config(pipeline_name NVARCHAR(200),task_id NVARCHAR(200),entrada_id UNIQUEIDENTIFIER);
    CREATE TABLE dbo.etl_pipeline_execucao(pipeline_name NVARCHAR(200),status VARCHAR(100));
    CREATE TABLE dbo.etl_job_lineage(pipeline_name NVARCHAR(200),job_name NVARCHAR(200));
    INSERT dbo.etl_sessao VALUES(REPLICATE('a',64),'ALICE',DATEADD(hour,1,GETDATE()));
    INSERT dbo.etl_pipeline VALUES('CTX','Projeto','Dominio','on_demand',1,1,NULL,NULL);
    INSERT dbo.etl_pipeline_job VALUES('CTX','Etapa','shell','true',1,NULL,10,20);
    """);
   var folder=Path.GetDirectoryName(Environment.GetEnvironmentVariable("WORKSPACE_TEST_SCHEMA_PATH"))!;
   foreach(var name in new[]{"141_workspace_rascunhos.sql","144_workspace_publicacao.sql","146_workspace_comandos.sql","159_workspace_lineage_hash.sql"})foreach(var batch in Regex.Split(await File.ReadAllTextAsync(Path.Combine(folder,name)),@"^\s*GO\s*$",RegexOptions.Multiline|RegexOptions.IgnoreCase))if(!string.IsNullOrWhiteSpace(batch))await Execute(c,batch);
   var repository=new SqlDraftRepository(options);
   static string Command(JsonElement published)=>published.GetProperty("definition").GetProperty("nodes")[0].GetProperty("configuration").GetProperty("legacyJob").GetProperty("job_command").GetString()!;
   static void NoPair(JsonElement published){Assert.False(published.TryGetProperty("versionId",out _));Assert.False(published.TryGetProperty("contentHash",out _));}
   var draft=await repository.ImportAsync("CTX",Actor(),default);var lease=await repository.LeaseAsync(draft.DraftId,new(),Actor(),default);
   var op=await repository.PublishAsync(draft.DraftId,new(Guid.NewGuid(),draft.Revision,lease.Fence),Actor(),default);
   // Pendente sem ponteiro: desenho da base importada, sem par.
   var pending=(await repository.ContextAsync("CTX",Actor(),true,default)).Published!.Value;Assert.Equal("true",Command(pending));NoPair(pending);
   // Projeção como a reconciliação faz: as tabelas SQL passam a divergir do desenho da versão.
   await Execute(c,$"EXEC sp_set_session_context @key=N'workspace_operation',@value=N'{op.OperationId}'; UPDATE dbo.etl_pipeline_job SET job_command='changed' WHERE pipeline_name='CTX'; EXEC sp_set_session_context @key=N'workspace_operation',@value=NULL");
   var projected=(string)(await Scalar(c,"EXEC dbo.sp_workspace_active_hash @name='CTX'"))!;
   var version=(await repository.VersionsAsync("CTX",default)).Single(v=>v.VersionId==op.VersionId);
   Assert.Matches("^[0-9a-f]{64}$",projected);Assert.Matches("^[0-9a-f]{64}$",version.ContentHash);Assert.NotEqual(projected,version.ContentHash);
   // Ponteiro confirmado sem hash ativo ainda não é publicação confirmada (a reserva recusaria).
   await Execute(c,$"UPDATE dbo.etl_workspace_publicacao SET estado='publicado',projection_hash='{projected}' WHERE operation_id='{op.OperationId}'; UPDATE dbo.etl_workspace_pipeline SET version_id='{op.VersionId}',pending_operation_id=NULL,active_hash=NULL WHERE pipeline_name='CTX'; UPDATE dbo.etl_workspace_rascunho SET estado='publicado' WHERE draft_id='{draft.DraftId}'");
   var withoutActive=(await repository.ContextAsync("CTX",Actor(),true,default)).Published!.Value;Assert.Equal("true",Command(withoutActive));NoPair(withoutActive);
   // Confirmação completa, como a de workspace_publication.py: active_hash = hash da projeção.
   await Execute(c,$"UPDATE dbo.etl_workspace_pipeline SET active_hash='{projected}' WHERE pipeline_name='CTX'");
   Assert.Equal(projected,await Scalar(c,"SELECT active_hash FROM dbo.etl_workspace_pipeline WHERE pipeline_name='CTX'"));
   var confirmed=(await repository.ContextAsync("CTX",Actor(),true,default)).Published!.Value;
   Assert.Equal(op.VersionId.ToString("D"),confirmed.GetProperty("versionId").GetString());Assert.NotEqual(draft.BaseVersionId,op.VersionId);
   Assert.Equal(version.ContentHash,confirmed.GetProperty("contentHash").GetString());
   // Desenho da versão confirmada (não das tabelas projetadas), lido junto com o par.
   Assert.Equal("true",Command(confirmed));Assert.Equal(JsonSerializer.Serialize(version.Definition,DraftValidation.Json),confirmed.GetProperty("definition").GetRawText());
   // Sem tela_jobs não há desenho nem par.
   Assert.Null((await repository.ContextAsync("CTX",Actor(),false,default)).Published);
   // Nova publicação pendente sobre a confirmada: desenho segue o do ponteiro, par some.
   var next=await repository.ImportAsync("CTX",Actor(),default);var nextLease=await repository.LeaseAsync(next.DraftId,new(),Actor(),default);
   var nextOp=await repository.PublishAsync(next.DraftId,new(Guid.NewGuid(),next.Revision,nextLease.Fence),Actor(),default);Assert.Equal("pendente",nextOp.State);
   var pendingAgain=(await repository.ContextAsync("CTX",Actor(),true,default)).Published!.Value;Assert.Equal("true",Command(pendingAgain));NoPair(pendingAgain);
  }finally{SqlConnection.ClearAllPools();if(created)await Execute(master,$"ALTER DATABASE [{database}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [{database}]");}
 }
 // 172: a reserva confere o par (versão + hash do conteúdo) da publicação confirmada exibida, sob o bloqueio
 // da 146. O teste acima segue histórico da 146 (sem par); aqui a 172 é aplicada duas vezes sobre um registro
 // de versões sintético em 2.22.1 e a procedure do produto é chamada em conexões reais, sem substituto.
 [SqlFact]
 public async Task ReserveRunChecksExpectedPublicationWithMigration172AppliedTwice()
 {
  var database="OrquestraF3Rsv_"+Guid.NewGuid().ToString("N");
  var options=new WorkspaceSqlOptions(Environment.GetEnvironmentVariable("WORKSPACE_TEST_SQL_SERVER")??"127.0.0.1,1433",database,Environment.GetEnvironmentVariable("WORKSPACE_TEST_SQL_USER")??"sa",Environment.GetEnvironmentVariable("WORKSPACE_TEST_SQL_PASSWORD")!,true);
  await using var master=new SqlConnection((options with{Database="master"}).ConnectionString());await master.OpenAsync();var created=false;
  try{
   await Execute(master,$"CREATE DATABASE [{database}] COLLATE SQL_Latin1_General_CP1_CI_AS");created=true;await using var c=new SqlConnection(options.ConnectionString());await c.OpenAsync();
   await Execute(c,"""
    CREATE TABLE dbo.etl_sessao(token_hash CHAR(64) PRIMARY KEY,matricula VARCHAR(20),expira_em DATETIME);
    CREATE TABLE dbo.etl_pipeline(pipeline_name NVARCHAR(200) PRIMARY KEY,project_name NVARCHAR(100),domain NVARCHAR(100),schedule_type VARCHAR(50),active BIT,dag_criada BIT,last_execution DATETIME,updated_at DATETIME);
    CREATE TABLE dbo.etl_pipeline_job(pipeline_name NVARCHAR(200),job_name NVARCHAR(200),job_type VARCHAR(100),job_command NVARCHAR(MAX),execution_order INT,depends_on_jobs NVARCHAR(MAX),layout_x FLOAT,layout_y FLOAT,PRIMARY KEY(pipeline_name,job_name));
    CREATE TABLE dbo.etl_pipeline_param(pipeline_name NVARCHAR(200),param_name VARCHAR(128) COLLATE Latin1_General_BIN2,param_type VARCHAR(30),param_value NVARCHAR(MAX));
    CREATE TABLE dbo.etl_pipeline_job_param(pipeline_name NVARCHAR(200),job_name NVARCHAR(200),param_name VARCHAR(128) COLLATE Latin1_General_BIN2,param_type VARCHAR(30),param_value NVARCHAR(MAX));
    CREATE TABLE dbo.etl_valida_arquivo_no(pipeline_name NVARCHAR(200),task_id NVARCHAR(200),ssh_conn_id VARCHAR(100));
    CREATE TABLE dbo.etl_valida_arquivo_config(pipeline_name NVARCHAR(200),task_id NVARCHAR(200),entrada_id UNIQUEIDENTIFIER);
    CREATE TABLE dbo.etl_pipeline_execucao(pipeline_name NVARCHAR(200),status VARCHAR(100));
    CREATE TABLE dbo.etl_job_lineage(pipeline_name NVARCHAR(200),job_name NVARCHAR(200));
    INSERT dbo.etl_sessao VALUES(REPLICATE('a',64),'ALICE',DATEADD(hour,1,GETDATE()));
    INSERT dbo.etl_pipeline VALUES('RSV','Projeto','Dominio','on_demand',1,1,NULL,NULL),('LEG','Projeto','Dominio','on_demand',1,1,NULL,NULL);
    INSERT dbo.etl_pipeline_job VALUES('RSV','Etapa','shell','true',1,NULL,10,20),('LEG','Etapa','shell','true',1,NULL,10,20);
    """);
   var folder=Path.GetDirectoryName(Environment.GetEnvironmentVariable("WORKSPACE_TEST_SCHEMA_PATH"))!;
   async Task Apply(string name){foreach(var batch in Regex.Split(await File.ReadAllTextAsync(Path.Combine(folder,name)),@"^\s*GO\s*$",RegexOptions.Multiline|RegexOptions.IgnoreCase))if(!string.IsNullOrWhiteSpace(batch))await Execute(c,batch);}
   foreach(var name in new[]{"141_workspace_rascunhos.sql","144_workspace_publicacao.sql","146_workspace_comandos.sql","159_workspace_lineage_hash.sql"})await Apply(name);
   // Registro de versões sintético na base local 2.22.1: o cálculo é numérico (2.22.1 > 2.9.9) e ignora fora do padrão.
   await Execute(c,"""
    CREATE TABLE dbo.etl_versao_ferramenta(id INT IDENTITY PRIMARY KEY,versao NVARCHAR(20) NOT NULL,titulo NVARCHAR(200) NOT NULL,descricao_md NVARCHAR(MAX),criado_por NVARCHAR(100),criado_em DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME());
    CREATE TABLE dbo.etl_app_config(config_key VARCHAR(100) PRIMARY KEY,config_value NVARCHAR(500));
    INSERT dbo.etl_versao_ferramenta(versao,titulo,criado_por) VALUES('2.9.9',N'Antiga','deploy'),('2.22.0',N'Posse','deploy'),('2.22.1',N'Aceite integrado','deploy'),('2.22.1-hotfix',N'Fora do padrão','deploy');
    INSERT dbo.etl_app_config VALUES('app_version','2.22.1'),('app_release_name',N'Aceite integrado');
    """);
   const string pairParameters="SELECT COUNT(*) FROM sys.parameters WHERE object_id=OBJECT_ID('dbo.sp_workspace_reserve_run') AND name IN('@expected_version','@expected_hash')";
   Assert.Equal(0,(int)(await Scalar(c,pairParameters))!);
   await Apply("172_workspace_reserva_publicacao_esperada.sql");await Apply("172_workspace_reserva_publicacao_esperada.sql");
   Assert.Equal(2,(int)(await Scalar(c,pairParameters))!);
   // Duas aplicações: uma só entrada, patch +1 sobre 2.22.1, configuração apontando para ela.
   const string title="Execução confere a publicação confirmada exibida antes de reservar";
   Assert.Equal(1,(int)(await Scalar(c,$"SELECT COUNT(*) FROM dbo.etl_versao_ferramenta WHERE titulo=N'{title}'"))!);
   Assert.Equal("2.22.2",await Scalar(c,$"SELECT versao FROM dbo.etl_versao_ferramenta WHERE titulo=N'{title}'"));
   Assert.Equal(5,(int)(await Scalar(c,"SELECT COUNT(*) FROM dbo.etl_versao_ferramenta"))!);
   Assert.Equal("2.22.2",await Scalar(c,"SELECT config_value FROM dbo.etl_app_config WHERE config_key='app_version'"));
   Assert.Equal(title,await Scalar(c,"SELECT config_value FROM dbo.etl_app_config WHERE config_key='app_release_name'"));
   Assert.Equal(2,(int)(await Scalar(c,"SELECT COUNT(*) FROM dbo.etl_app_config"))!);
   var repository=new SqlDraftRepository(options);
   async Task<int> Commands(string filter)=>(int)(await Scalar(c,"SELECT COUNT(*) FROM dbo.etl_workspace_comando WHERE "+filter))!;
   // Projeção e confirmação como a reconciliação: tabelas mudam sob a operação pendente e active_hash = hash projetado.
   async Task Confirm(Guid operation,Guid version,Guid draftId,string command){
    await Execute(c,$"EXEC sp_set_session_context @key=N'workspace_operation',@value=N'{operation}'; UPDATE dbo.etl_pipeline_job SET job_command='{command}' WHERE pipeline_name='RSV'; EXEC sp_set_session_context @key=N'workspace_operation',@value=NULL");
    var projected=(string)(await Scalar(c,"EXEC dbo.sp_workspace_active_hash @name='RSV'"))!;
    await Execute(c,$"UPDATE dbo.etl_workspace_publicacao SET estado='publicado',projection_hash='{projected}' WHERE operation_id='{operation}'; UPDATE dbo.etl_workspace_pipeline SET version_id='{version}',pending_operation_id=NULL,active_hash='{projected}' WHERE pipeline_name='RSV'; UPDATE dbo.etl_workspace_rascunho SET estado='publicado' WHERE draft_id='{draftId}'");
   }
   var draft=await repository.ImportAsync("RSV",Actor(),default);var lease=await repository.LeaseAsync(draft.DraftId,new(),Actor(),default);
   var first=await repository.PublishAsync(draft.DraftId,new(Guid.NewGuid(),draft.Revision,lease.Fence),Actor(),default);
   var v1=first.VersionId;var h1=(await repository.VersionsAsync("RSV",default)).Single(v=>v.VersionId==v1).ContentHash;
   // Pendente: nem o par da própria publicação reserva, nem a execução sem par.
   Assert.Equal(51172,(await ReserveRun(c,"RSV","workspace__pending",'c',"ALICE",v1,h1)).Error);
   Assert.Equal(51172,(await ReserveRun(c,"RSV","workspace__pending",'c',"ALICE",null,null)).Error);
   await Confirm(first.OperationId,v1,draft.DraftId,"changed");
   // Sem par, par incompleto, malformado (curto, longo que truncado bateria, não hexadecimal), inexistente ou incorreto:
   // recusa por publicação antes de qualquer gravação.
   foreach(var (version,hash) in new (Guid?,string?)[]{(null,null),(v1,null),(null,h1),(v1,h1[..63]),(v1,h1+"0"),(v1,"g"+h1[1..]),(v1," "+h1[1..]),(Guid.NewGuid(),h1),(Guid.Empty,h1),(v1,new string('e',64))})
    Assert.Equal(51172,(await ReserveRun(c,"RSV","workspace__bad",'c',"ALICE",version,hash)).Error);
   Assert.Equal(0,await Commands("pipeline_name='RSV'"));
   // Par correto (hash em maiúsculas é o mesmo hash): reserva com a versão e o hash gravados da publicação.
   var a=await ReserveRun(c,"RSV","workspace__a",'c',"ALICE",v1,h1.ToUpperInvariant());Assert.Equal((0,false),(a.Error,a.Existing));Assert.NotNull(a.Token);
   Assert.Equal(1,await Commands($"run_id='workspace__a' AND ativa=1 AND tipo='execute' AND version_id='{v1}' AND content_hash='{h1}'"));
   // Replay ativo: mesmo pedido, ator e par devolvem o mesmo token; qualquer outra identidade é recusada.
   var replay=await ReserveRun(c,"RSV","workspace__a",'c',"ALICE",v1,h1);Assert.Equal((0,a.Token,true),(replay.Error,replay.Token,replay.Existing));
   Assert.Equal(51146,(await ReserveRun(c,"RSV","workspace__a",'d',"ALICE",v1,h1)).Error);
   Assert.Equal(51146,(await ReserveRun(c,"RSV","workspace__a",'c',"BOB",v1,h1)).Error);
   Assert.Equal(51146,(await ReserveRun(c,"RSV","workspace__a",'c',"ALICE",v1,h1,true)).Error);
   Assert.Equal(51146,(await ReserveRun(c,"RSV","workspace__other",'c',"ALICE",v1,h1)).Error);
   Assert.Equal(51172,(await ReserveRun(c,"RSV","workspace__a",'c',"ALICE",v1,new string('e',64))).Error);
   Assert.Equal(a.Token,await Scalar(c,"SELECT command_token FROM dbo.etl_workspace_comando WHERE run_id='workspace__a'"));Assert.Equal(1,await Commands("pipeline_name='RSV'"));
   // Ack da API (o texto de workspace_operations.py): token alheio não avança; o da reserva leva reservado→enviado uma vez; repetir não muda nada.
   var acknowledge=Regex.Match(await File.ReadAllTextAsync(Path.Combine(folder,"../../api/services/workspace_operations.py")),"ACKNOWLEDGE_COMMAND = "+"\"\"\""+"(.*?)"+"\"\"\"",RegexOptions.Singleline).Groups[1].Value;Assert.NotEmpty(acknowledge);
   async Task Acknowledge(string runId,Guid? token){await using var cmd=new SqlCommand(string.Concat(acknowledge.Split('?').Select((part,i)=>i==0?part:"@p"+(i-1)+part)),c);cmd.Parameters.AddWithValue("@p0","RSV");cmd.Parameters.AddWithValue("@p1",runId);cmd.Parameters.AddWithValue("@p2",(object?)token??DBNull.Value);await cmd.ExecuteNonQueryAsync();}
   await Acknowledge("workspace__a",Guid.NewGuid());Assert.Equal(1,await Commands("run_id='workspace__a' AND ativa=1 AND estado='reservado'"));
   await Acknowledge("workspace__a",a.Token);Assert.Equal(1,await Commands("run_id='workspace__a' AND ativa=1 AND estado='enviado'"));
   var acked=await Scalar(c,"SELECT atualizada_em FROM dbo.etl_workspace_comando WHERE run_id='workspace__a'");
   await Acknowledge("workspace__a",a.Token);Assert.Equal(acked,await Scalar(c,"SELECT atualizada_em FROM dbo.etl_workspace_comando WHERE run_id='workspace__a'"));
   // Replay do comando já enviado: mesmo token, sem linha nova nem mudança de estado (a API ainda confirma a corrida no Airflow antes de responder).
   var resent=await ReserveRun(c,"RSV","workspace__a",'c',"ALICE",v1,h1);Assert.Equal((0,a.Token,true),(resent.Error,resent.Token,resent.Existing));
   Assert.Equal(1,await Commands("run_id='workspace__a' AND ativa=1 AND estado='enviado'"));Assert.Equal(1,await Commands("pipeline_name='RSV'"));
   // Replay inativo: devolve o mesmo token sem reativar; outro pedido ou ator é identidade reutilizada.
   await Execute(c,"UPDATE dbo.etl_workspace_comando SET ativa=0,estado='success' WHERE run_id='workspace__a'");
   var inactive=await ReserveRun(c,"RSV","workspace__a",'c',"ALICE",v1,h1);Assert.Equal((0,a.Token,true),(inactive.Error,inactive.Token,inactive.Existing));Assert.Equal(0,await Commands("ativa=1"));
   Assert.Equal(51146,(await ReserveRun(c,"RSV","workspace__a",'d',"ALICE",v1,h1)).Error);
   Assert.Equal(51146,(await ReserveRun(c,"RSV","workspace__a",'c',"BOB",v1,h1)).Error);
   // Encerrado em 'erro' (a reconciliação não achou a corrida): o mesmo pedido é recusado com instrução de nova corrida,
   // sem reativar nem trocar o token; o ack também não o reabre.
   var lost=await ReserveRun(c,"RSV","workspace__lost",'c',"ALICE",v1,h1);Assert.Equal((0,false),(lost.Error,lost.Existing));
   await Execute(c,"UPDATE dbo.etl_workspace_comando SET ativa=0,estado='erro' WHERE run_id='workspace__lost'");
   var refused=await Assert.ThrowsAsync<SqlException>(()=>Execute(c,$"EXEC dbo.sp_workspace_reserve_run @name='RSV',@run_id='workspace__lost',@request_hash='{new string('c',64)}',@actor='ALICE',@expected_version='{v1}',@expected_hash='{h1}'"));
   Assert.Equal(51146,refused.Number);Assert.Contains("Comando encerrado sem confirmacao",refused.Message);
   await Acknowledge("workspace__lost",lost.Token);
   Assert.Equal(1,await Commands("run_id='workspace__lost' AND ativa=0 AND estado='erro'"));Assert.Equal(lost.Token,await Scalar(c,"SELECT command_token FROM dbo.etl_workspace_comando WHERE run_id='workspace__lost'"));Assert.Equal(0,await Commands("ativa=1"));
   // Reprocessamento: regra da 146 (corrida da versão atual) mantida; com par informado, confere também.
   var b=await ReserveRun(c,"RSV","workspace__b",'c',"ALICE",v1,h1);Assert.Equal((0,false),(b.Error,b.Existing));
   await Execute(c,$"DECLARE @queued DATETIME2=SYSUTCDATETIME();EXEC dbo.sp_workspace_guard_run @name='RSV',@run_id='workspace__b',@version='{v1}',@hash='{h1}',@queued_at=@queued");
   await Execute(c,"UPDATE dbo.etl_workspace_execucao SET ativa=0 WHERE pipeline_name='RSV';UPDATE dbo.etl_workspace_comando SET ativa=0,estado='success' WHERE pipeline_name='RSV'");
   Assert.Equal(51172,(await ReserveRun(c,"RSV","workspace__b",'d',"ALICE",v1,new string('e',64),true)).Error);
   Assert.Equal(51146,(await ReserveRun(c,"RSV","workspace__never",'d',"ALICE",v1,h1,true)).Error);
   var reprocessed=await ReserveRun(c,"RSV","workspace__b",'d',"ALICE",v1,h1,true);Assert.Equal((0,false),(reprocessed.Error,reprocessed.Existing));Assert.NotEqual(b.Token,reprocessed.Token);
   Assert.Equal(1,await Commands("run_id='workspace__b' AND ativa=1 AND tipo='reprocess'"));await Execute(c,"UPDATE dbo.etl_workspace_comando SET ativa=0,estado='success' WHERE pipeline_name='RSV'");
   var withoutPair=await ReserveRun(c,"RSV","workspace__b",'e',"ALICE",null,null,true);Assert.Equal((0,false),(withoutPair.Error,withoutPair.Existing));
   await Execute(c,"UPDATE dbo.etl_workspace_comando SET ativa=0,estado='success' WHERE pipeline_name='RSV'");
   // Publicação trocada antes da reserva: nova publicação pendente e depois confirmada sobre a anterior.
   var next=await repository.ImportAsync("RSV",Actor(),default);var nextLease=await repository.LeaseAsync(next.DraftId,new(),Actor(),default);
   var second=await repository.PublishAsync(next.DraftId,new(Guid.NewGuid(),next.Revision,nextLease.Fence),Actor(),default);
   var v2=second.VersionId;var h2=(await repository.VersionsAsync("RSV",default)).Single(v=>v.VersionId==v2).ContentHash;Assert.NotEqual(v1,v2);Assert.NotEqual(h1,h2);
   Assert.Equal(51172,(await ReserveRun(c,"RSV","workspace__swap",'c',"ALICE",v1,h1)).Error);
   Assert.Equal(51172,(await ReserveRun(c,"RSV","workspace__swap",'c',"ALICE",v2,h2)).Error);
   await Confirm(second.OperationId,v2,next.DraftId,"changed-again");
   foreach(var (version,hash) in new (Guid?,string?)[]{(v1,h1),(v2,h1),(v1,h2)})Assert.Equal(51172,(await ReserveRun(c,"RSV","workspace__swap",'c',"ALICE",version,hash)).Error);
   Assert.Equal(0,await Commands("run_id='workspace__swap'"));
   // Comando antigo (par v1) não é reaproveitado com o par novo; corrida de v1 não reprocessa sobre v2.
   Assert.Equal(51146,(await ReserveRun(c,"RSV","workspace__a",'c',"ALICE",v2,h2)).Error);
   Assert.Equal(51146,(await ReserveRun(c,"RSV","workspace__b",'f',"ALICE",null,null,true)).Error);
   Assert.Equal(a.Token,await Scalar(c,"SELECT command_token FROM dbo.etl_workspace_comando WHERE run_id='workspace__a'"));Assert.Equal(0,await Commands("ativa=1"));
   // Pipeline fora do workspace: par informado é recusado; sem par segue sem reserva, como na 146.
   Assert.Equal(51172,(await ReserveRun(c,"LEG","manual__leg",'c',"ALICE",v2,h2)).Error);
   Assert.Equal((0,(Guid?)null,false),await ReserveRun(c,"LEG","manual__leg",'c',"ALICE",null,null));Assert.Equal(0,await Commands("pipeline_name='LEG'"));
   // Duas conexões reais repetem o mesmo pedido ao mesmo tempo: uma reserva e um replay do mesmo token, uma linha só.
   await using(var one=new SqlConnection(options.ConnectionString()))
   await using(var two=new SqlConnection(options.ConnectionString())){
    await one.OpenAsync();await two.OpenAsync();
    var twins=await Task.WhenAll(ReserveRun(one,"RSV","workspace__twin",'7',"ALICE",v2,h2),ReserveRun(two,"RSV","workspace__twin",'7',"ALICE",v2,h2));
    Assert.All(twins,r=>Assert.Equal(0,r.Error));Assert.Single(twins,r=>!r.Existing);Assert.NotNull(twins[0].Token);Assert.Equal(twins[0].Token,twins[1].Token);
   }
   Assert.Equal(1,await Commands("run_id='workspace__twin' AND ativa=1 AND estado='reservado'"));Assert.Equal(1,await Commands("run_id='workspace__twin'"));
   await Execute(c,"UPDATE dbo.etl_workspace_comando SET ativa=0,estado='success' WHERE run_id='workspace__twin'");
   // Duas conexões reais, identidades diferentes (corrida, ator e pedido), mesmo par: uma única reserva.
   await using(var one=new SqlConnection(options.ConnectionString()))
   await using(var two=new SqlConnection(options.ConnectionString())){
    await one.OpenAsync();await two.OpenAsync();
    var races=await Task.WhenAll(ReserveRun(one,"RSV","workspace__race1",'1',"ALICE",v2,h2),ReserveRun(two,"RSV","workspace__race2",'2',"BOB",v2,h2));
    Assert.Single(races,r=>r.Error==0);Assert.Single(races,r=>r.Error==51146);
   }
   Assert.Equal(1,await Commands("ativa=1"));Assert.Equal(1,await Commands("run_id LIKE 'workspace[_][_]race%'"));
  }finally{SqlConnection.ClearAllPools();if(created)await Execute(master,$"ALTER DATABASE [{database}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [{database}]");}
 }
 static WorkspacePrincipal Actor(bool publisher=true)=>new("ALICE","synthetic",new HashSet<string>(publisher?new[]{"tela_pipelines","tela_jobs","acao_editar","acao_publicar"}:new[]{"tela_pipelines","tela_jobs","acao_editar"})){SessionHash=new string('a',64)};
 static async Task<object?> Scalar(SqlConnection c,string sql){await using var cmd=new SqlCommand(sql,c);return await cmd.ExecuteScalarAsync();}
 static async Task Execute(SqlConnection c,string sql){await using var cmd=new SqlCommand(sql,c){CommandTimeout=30};await cmd.ExecuteNonQueryAsync();}
 // Procedure do produto com parâmetros tipados; devolve o número do erro SQL ou o resultado da reserva.
 static async Task<(int Error,Guid? Token,bool Existing)> ReserveRun(SqlConnection c,string name,string runId,char request,string actor,Guid? version,string? hash,bool reprocess=false)
 {
  await using var cmd=new SqlCommand("dbo.sp_workspace_reserve_run",c){CommandType=CommandType.StoredProcedure,CommandTimeout=30};
  cmd.Parameters.Add("@name",SqlDbType.NVarChar,200).Value=name;cmd.Parameters.Add("@run_id",SqlDbType.NVarChar,300).Value=runId;
  cmd.Parameters.Add("@request_hash",SqlDbType.Char,64).Value=new string(request,64);cmd.Parameters.Add("@actor",SqlDbType.NVarChar,100).Value=actor;cmd.Parameters.Add("@reprocess",SqlDbType.Bit).Value=reprocess;
  cmd.Parameters.Add("@expected_version",SqlDbType.UniqueIdentifier).Value=(object?)version??DBNull.Value;cmd.Parameters.Add("@expected_hash",SqlDbType.VarChar).Value=(object?)hash??DBNull.Value;
  try{await using var reader=await cmd.ExecuteReaderAsync();Assert.True(await reader.ReadAsync());return(0,reader.IsDBNull(0)?(Guid?)null:reader.GetGuid(0),reader.GetInt32(1)==1);}
  catch(SqlException e){return(e.Number,null,false);}
 }
}
