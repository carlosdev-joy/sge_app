using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using Microsoft.Data.SqlClient;
using Orquestra.Application.Drafts;
using Orquestra.Application.Security;
using Orquestra.Domain.Flows;
using Orquestra.Infrastructure.Drafts;
using Orquestra.Infrastructure.Security;
using Xunit;
namespace Orquestra.Tests;
public sealed class LineageSqlTests
{
 [SqlFact]
 public async Task LineageCaptureHashMigrationSaveAndHistoricalRestoreAreVersioned()
 {
  var database="OrquestraLineageTest_"+Guid.NewGuid().ToString("N");
  var options=new WorkspaceSqlOptions(Environment.GetEnvironmentVariable("WORKSPACE_TEST_SQL_SERVER")??"127.0.0.1,1433",database,Environment.GetEnvironmentVariable("WORKSPACE_TEST_SQL_USER")??"sa",Environment.GetEnvironmentVariable("WORKSPACE_TEST_SQL_PASSWORD")!,true);
  await using var master=new SqlConnection((options with{Database="master"}).ConnectionString());await master.OpenAsync();var created=false;
  try{
   await Exec(master,$"CREATE DATABASE [{database}] COLLATE SQL_Latin1_General_CP1_CI_AS");created=true;await using var c=new SqlConnection(options.ConnectionString());await c.OpenAsync();
   await Exec(c,"""
    CREATE TABLE dbo.etl_sessao(token_hash CHAR(64),matricula VARCHAR(20),expira_em DATETIME);
    CREATE TABLE dbo.etl_pipeline(pipeline_name NVARCHAR(200) PRIMARY KEY,project_name NVARCHAR(100),domain NVARCHAR(100),schedule_type VARCHAR(50),active BIT);
    CREATE TABLE dbo.etl_pipeline_job(pipeline_name NVARCHAR(200),job_name NVARCHAR(200),job_type VARCHAR(100),job_command NVARCHAR(MAX),execution_order INT,depends_on_jobs NVARCHAR(MAX),PRIMARY KEY(pipeline_name,job_name));
    CREATE TABLE dbo.etl_pipeline_execucao(pipeline_name NVARCHAR(200),status VARCHAR(100));
    CREATE TABLE dbo.etl_job_lineage(id INT IDENTITY PRIMARY KEY,pipeline_name NVARCHAR(200),job_name NVARCHAR(200),direction NVARCHAR(30),object_name NVARCHAR(500),apt_code NVARCHAR(MAX),columns_json NVARCHAR(MAX),extra_column NVARCHAR(MAX),created_at DATETIME2 DEFAULT SYSUTCDATETIME(),extracted_at DATETIME2);
    INSERT dbo.etl_sessao VALUES(REPLICATE('a',64),'QA',DATEADD(hour,1,GETDATE()));
    INSERT dbo.etl_pipeline VALUES('PIPE','Project','Domain','on_demand',0),('OLD','Project','Domain','on_demand',0);
    INSERT dbo.etl_pipeline_job VALUES('PIPE','NODE','shell','true',1,NULL),('OLD','NODE','shell','true',1,NULL);
    INSERT dbo.etl_job_lineage(pipeline_name,job_name,direction,object_name,apt_code,extra_column) VALUES('PIPE','NODE','origem','A','a','preserve'),('PIPE','NODE','destino','B','b','preserve'),('PIPE','NODE','origem','A','a','preserve');
    """);
   var folder=Path.GetDirectoryName(Environment.GetEnvironmentVariable("WORKSPACE_TEST_SCHEMA_PATH"))!;
   async Task Migrate(string file){foreach(var batch in Regex.Split(await File.ReadAllTextAsync(Path.Combine(folder,file)),@"^\s*GO\s*$",RegexOptions.Multiline|RegexOptions.IgnoreCase))if(!string.IsNullOrWhiteSpace(batch))await Exec(c,batch);}
   await Migrate("141_workspace_rascunhos.sql");await Migrate("144_workspace_publicacao.sql");
   var oldHash=await Scalar(c,"EXEC dbo.sp_workspace_active_hash @name='PIPE'");
   await Migrate("159_workspace_lineage_hash.sql");await Migrate("159_workspace_lineage_hash.sql");
   Assert.Equal(oldHash,await Scalar(c,"EXEC dbo.sp_workspace_active_hash @name='PIPE',@include_lineage=0"));
   var lineageHash=await Scalar(c,"EXEC dbo.sp_workspace_active_hash @name='PIPE',@include_lineage=1");Assert.NotEqual(oldHash,lineageHash);
   await Exec(c,"DELETE dbo.etl_job_lineage;INSERT dbo.etl_job_lineage(pipeline_name,job_name,direction,object_name,apt_code,extra_column) VALUES('PIPE','NODE','origem','A','a','preserve'),('PIPE','NODE','origem','A','a','preserve'),('PIPE','NODE','destino','B','b','preserve')");
   Assert.Equal(lineageHash,await Scalar(c,"EXEC dbo.sp_workspace_active_hash @name='PIPE',@include_lineage=1"));
   foreach(var field in new[]{"direction","object_name","apt_code","columns_json","extra_column"}){
    await using var tx=(SqlTransaction)await c.BeginTransactionAsync();await using var change=new SqlCommand($"UPDATE dbo.etl_job_lineage SET [{field}]=N'changed < & 😀' WHERE id=(SELECT MIN(id) FROM dbo.etl_job_lineage)",c,tx);await change.ExecuteNonQueryAsync();
    await using var hash=new SqlCommand("EXEC dbo.sp_workspace_active_hash @name='PIPE',@include_lineage=1",c,tx);Assert.NotEqual(lineageHash,await hash.ExecuteScalarAsync());await tx.RollbackAsync();
   }
   var repo=new SqlDraftRepository(options);var actor=new WorkspacePrincipal("QA","synthetic",new HashSet<string>{"tela_pipelines","tela_jobs","acao_editar","acao_publicar"}){SessionHash=new string('a',64)};
   var draft=await repo.ImportAsync("pipe",actor,default);Assert.Equal(1,draft.Definition.Metadata.GetProperty("workspaceLineageVersion").GetInt32());Assert.Equal(3,draft.Definition.Nodes[0].Configuration.GetProperty("etl_job_lineage").GetArrayLength());Assert.Contains("preserve",draft.Definition.Nodes[0].Configuration.GetRawText());
   var lease=await repo.LeaseAsync(draft.DraftId,new(),actor,default);
   PipelineDefinition Mutate(Action<JsonObject> change){var root=JsonNode.Parse(JsonSerializer.Serialize(draft.Definition,DraftValidation.Json))!.AsObject();change(root);return root.Deserialize<PipelineDefinition>(DraftValidation.Json)!;}
   foreach(var malformed in new[]{Mutate(root=>root["metadata"]!.AsObject().Remove("workspaceLineageVersion")),Mutate(root=>root["metadata"]!["workspaceLineageVersion"]=2),Mutate(root=>root["nodes"]![0]!["configuration"]!.AsObject().Remove("etl_job_lineage")),Mutate(root=>root["metadata"]!["etl_job_lineage"]=new JsonArray())})Assert.Equal(422,(await Assert.ThrowsAsync<WorkspaceException>(()=>repo.SaveAsync(draft.DraftId,new(draft.Revision,lease.Fence,malformed,draft.Layout),actor,default))).StatusCode);
   await Exec(c,"UPDATE dbo.etl_job_lineage SET apt_code='drift' WHERE object_name='A'");Assert.Equal("active_hash_conflict",(await Assert.ThrowsAsync<WorkspaceException>(()=>repo.PublishAsync(draft.DraftId,new(Guid.NewGuid(),draft.Revision,lease.Fence),actor,default))).Code);await Exec(c,"UPDATE dbo.etl_job_lineage SET apt_code='a' WHERE object_name='A'");
   var empty=Mutate(root=>root["nodes"]![0]!["configuration"]!["etl_job_lineage"]=new JsonArray());draft=await repo.SaveAsync(draft.DraftId,new(draft.Revision,lease.Fence,empty,draft.Layout),actor,default);
   var publication=await repo.PublishAsync(draft.DraftId,new(Guid.NewGuid(),draft.Revision,lease.Fence),actor,default);Assert.Equal(lineageHash,await Scalar(c,"EXEC dbo.sp_workspace_active_hash @name='PIPE'"));
   // Projeção inteira pode reverter sem perder sequer uma duplicata.
   await Exec(c,$"EXEC sp_set_session_context @key=N'workspace_operation',@value=N'{publication.OperationId}'");
   await using(var tx=(SqlTransaction)await c.BeginTransactionAsync()){await using var remove=new SqlCommand("DELETE dbo.etl_job_lineage WHERE pipeline_name='PIPE'",c,tx);await remove.ExecuteNonQueryAsync();await tx.RollbackAsync();}Assert.Equal(3,await Scalar(c,"SELECT COUNT(*) FROM dbo.etl_job_lineage WHERE pipeline_name='PIPE'"));
   await Exec(c,$"DELETE dbo.etl_job_lineage WHERE pipeline_name='PIPE';EXEC sp_set_session_context @key=N'workspace_operation',@value=NULL;UPDATE dbo.etl_workspace_publicacao SET estado='publicado' WHERE operation_id='{publication.OperationId}';UPDATE dbo.etl_workspace_pipeline SET version_id='{publication.VersionId}',pending_operation_id=NULL WHERE pipeline_name='PIPE';UPDATE dbo.etl_workspace_rascunho SET estado='publicado' WHERE draft_id='{draft.DraftId}'");
   var restored=await repo.RestoreAsync("PIPE",publication.VersionId,actor,default);Assert.Empty(restored.ReadOnlyReasons);Assert.Empty(restored.Definition.Nodes[0].Configuration.GetProperty("etl_job_lineage").EnumerateArray());
   // Fixture pré-D: core editável, mesmo hash0 após migration; restore histórico em consulta.
   var historical=new PipelineDefinition{Identity=new("OLD"),Metadata=JsonSerializer.SerializeToElement(new{legacyPipeline=new{project_name="Project",domain="Domain",schedule_type="on_demand",active=false}},DraftValidation.Json),Nodes=[new(){Id="NODE",Type="shell",Configuration=JsonSerializer.SerializeToElement(new{legacyJob=new{job_command="true"}},DraftValidation.Json)}]};
   var version=Guid.NewGuid();var oldDraft=Guid.NewGuid();var operation=Guid.NewGuid();var definition=JsonSerializer.Serialize(historical,DraftValidation.Json);var layout=JsonSerializer.Serialize(new FlowLayout(1,new Dictionary<string,NodePosition>()),DraftValidation.Json);
   await using(var insert=new SqlCommand("INSERT dbo.etl_workspace_versao(version_id,pipeline_name,numero,definition_json,layout_json,content_hash,criada_por) VALUES(@version,'OLD',1,@definition,@layout,REPLICATE('a',64),'QA');INSERT dbo.etl_workspace_rascunho(draft_id,pipeline_name,base_version_id,definition_json,layout_json,criado_por,responsavel) VALUES(@draft,'OLD',@version,@definition,@layout,'QA','QA')",c)){insert.Parameters.AddWithValue("@version",version);insert.Parameters.AddWithValue("@draft",oldDraft);insert.Parameters.AddWithValue("@definition",definition);insert.Parameters.AddWithValue("@layout",layout);await insert.ExecuteNonQueryAsync();}
   var old=await repo.GetAsync(oldDraft,actor,default);var oldLease=await repo.LeaseAsync(oldDraft,new(),actor,default);old=await repo.SaveAsync(oldDraft,new(old.Revision,oldLease.Fence,old.Definition,old.Layout),actor,default);Assert.Equal(2,old.Revision);
   await Exec(c,$"INSERT dbo.etl_workspace_publicacao(operation_id,draft_id,version_id,pipeline_name,revision,fence,ator,factory_run_id,estado,projection_hash) VALUES('{operation}','{oldDraft}','{version}','OLD',2,{oldLease.Fence},'QA','synthetic-old','erro',REPLICATE('b',64));INSERT dbo.etl_workspace_pipeline(pipeline_name,pending_operation_id) VALUES('OLD','{operation}')");
   var hash0=await Scalar(c,"EXEC dbo.sp_workspace_active_hash @name='OLD',@include_lineage=0");await Migrate("159_workspace_lineage_hash.sql");Assert.Equal(hash0,await Scalar(c,"EXEC dbo.sp_workspace_active_hash @name='OLD'"));Assert.Equal("projetado",(await repo.RetryAsync(operation,new(operation,old.Revision,oldLease.Fence),actor,default)).State);
   await Exec(c,$"UPDATE dbo.etl_workspace_publicacao SET estado='publicado' WHERE operation_id='{operation}';UPDATE dbo.etl_workspace_pipeline SET pending_operation_id=NULL,version_id='{version}' WHERE pipeline_name='OLD';UPDATE dbo.etl_workspace_rascunho SET estado='publicado' WHERE draft_id='{oldDraft}'");
   var unknown=await repo.RestoreAsync("OLD",version,actor,default);Assert.Contains(unknown.ReadOnlyReasons,reason=>reason.Contains("lineage histórico"));var readLease=await repo.LeaseAsync(unknown.DraftId,new(),actor,default);Assert.Equal(409,(await Assert.ThrowsAsync<WorkspaceException>(()=>repo.SaveAsync(unknown.DraftId,new(unknown.Revision,readLease.Fence,unknown.Definition,unknown.Layout),actor,default))).StatusCode);
  }finally{SqlConnection.ClearAllPools();if(created)await Exec(master,$"ALTER DATABASE [{database}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE;DROP DATABASE [{database}]");}
 }
 private static async Task Exec(SqlConnection c,string sql){await using var command=new SqlCommand(sql,c){CommandTimeout=30};await command.ExecuteNonQueryAsync();}
 private static async Task<object?> Scalar(SqlConnection c,string sql){await using var command=new SqlCommand(sql,c){CommandTimeout=30};return await command.ExecuteScalarAsync();}
}
