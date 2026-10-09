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
   foreach(var name in new[]{"141_workspace_rascunhos.sql","144_workspace_publicacao.sql","144_workspace_publicacao.sql","146_workspace_comandos.sql","146_workspace_comandos.sql"})foreach(var batch in Regex.Split(await File.ReadAllTextAsync(Path.Combine(folder,name)),@"^\s*GO\s*$",RegexOptions.Multiline|RegexOptions.IgnoreCase))if(!string.IsNullOrWhiteSpace(batch))await Execute(c,batch);
   var repository=new SqlDraftRepository(options);Assert.True(await repository.PublicationSchemaAsync(default));
   var draft=await repository.ImportAsync("pub",Actor(),default);Assert.DoesNotContain("cipher-never",JsonSerializer.Serialize(draft,DraftValidation.Json));
   var lease=await repository.LeaseAsync(draft.DraftId,new(),Actor(),default);var command=new PublicationCommand(Guid.NewGuid(),draft.Revision,lease.Fence);
   Assert.Equal("permission_denied",(await Assert.ThrowsAsync<WorkspaceException>(()=>repository.PublishAsync(draft.DraftId,command,Actor(false),default))).Code);
   Assert.Equal("lease_conflict",(await Assert.ThrowsAsync<WorkspaceException>(()=>repository.PublishAsync(draft.DraftId,command with{Fence=lease.Fence+1},Actor(),default))).Code);
   await Execute(c,"INSERT dbo.etl_pipeline_execucao VALUES('PUB','RUNNING')");Assert.Equal("execution_active",(await Assert.ThrowsAsync<WorkspaceException>(()=>repository.PublishAsync(draft.DraftId,command,Actor(),default))).Code);await Execute(c,"UPDATE dbo.etl_pipeline_execucao SET status='AGUARDANDO_DEPENDENCIA'");Assert.Equal("execution_active",(await Assert.ThrowsAsync<WorkspaceException>(()=>repository.PublishAsync(draft.DraftId,command,Actor(),default))).Code);await Execute(c,"DELETE dbo.etl_pipeline_execucao");
   var before=(string)(await Scalar(c,"EXEC dbo.sp_workspace_active_hash @name='PUB'"))!;
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
 static WorkspacePrincipal Actor(bool publisher=true)=>new("ALICE","synthetic",new HashSet<string>(publisher?new[]{"tela_pipelines","tela_jobs","acao_editar","acao_publicar"}:new[]{"tela_pipelines","tela_jobs","acao_editar"})){SessionHash=new string('a',64)};
 static async Task<object?> Scalar(SqlConnection c,string sql){await using var cmd=new SqlCommand(sql,c);return await cmd.ExecuteScalarAsync();}
 static async Task Execute(SqlConnection c,string sql){await using var cmd=new SqlCommand(sql,c){CommandTimeout=30};await cmd.ExecuteNonQueryAsync();}
}
