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

public sealed class SecretSqlTests
{
 [SqlFact]
 public async Task VaultReferencesRequireRegisteredScopeAndNeverPersistCipherInDraft()
 {
  var database="OrquestraSecretTest_"+Guid.NewGuid().ToString("N");
  var options=new WorkspaceSqlOptions(Environment.GetEnvironmentVariable("WORKSPACE_TEST_SQL_SERVER")??"127.0.0.1,1433",database,Environment.GetEnvironmentVariable("WORKSPACE_TEST_SQL_USER")??"sa",Environment.GetEnvironmentVariable("WORKSPACE_TEST_SQL_PASSWORD")!,true);
  await using var master=new SqlConnection((options with{Database="master"}).ConnectionString());await master.OpenAsync();var created=false;
  try{
   await Exec(master,$"CREATE DATABASE [{database}]");created=true;
   await using var c=new SqlConnection(options.ConnectionString());await c.OpenAsync();
   await Exec(c,"CREATE TABLE dbo.etl_sessao(token_hash CHAR(64),matricula NVARCHAR(100),expira_em DATETIME); CREATE TABLE dbo.etl_pipeline(pipeline_name NVARCHAR(200)); INSERT dbo.etl_sessao VALUES(REPLICATE('a',64),'QA',DATEADD(hour,1,GETDATE()));");
   var schemaPath=Environment.GetEnvironmentVariable("WORKSPACE_TEST_SCHEMA_PATH")!;
   foreach(var filename in new[]{schemaPath,Path.Combine(Path.GetDirectoryName(schemaPath)!,"157_workspace_catalogo_segredos.sql")})
    foreach(var batch in Regex.Split(await File.ReadAllTextAsync(filename),@"^\s*GO\s*$",RegexOptions.Multiline|RegexOptions.IgnoreCase))if(!string.IsNullOrWhiteSpace(batch))await Exec(c,batch);
   var actor=new WorkspacePrincipal("QA","synthetic",new HashSet<string>{"tela_pipelines","tela_jobs","acao_editar"}){SessionHash=new string('a',64)};
   var repo=new SqlDraftRepository(options);var definition=new PipelineDefinition{Identity=new("PIPE"),Metadata=JsonDocument.Parse("{\"legacyTables\":{\"etl_pipeline_param\":[]}}").RootElement};var layout=new FlowLayout(1,new Dictionary<string,NodePosition>());
   var draft=await repo.CreateAsync(new(definition,layout),actor,default);definition=draft.Definition;var lease=await repo.LeaseAsync(draft.DraftId,new(),actor,default);var secret=Guid.NewGuid();
   await using(var insert=new SqlCommand("INSERT dbo.etl_workspace_segredo(secret_id,pipeline_name,job_name,param_name,ciphertext,criado_por,draft_id) VALUES(@id,'PIPE',NULL,'Senha','cipher-unit-sentinel','QA',@draft)",c)){insert.Parameters.AddWithValue("@id",secret);insert.Parameters.AddWithValue("@draft",draft.DraftId);await insert.ExecuteNonQueryAsync();}
   PipelineDefinition WithParameter(string name="Senha",string type="Encrypted",Guid? identifier=null){var root=JsonNode.Parse(JsonSerializer.Serialize(definition,DraftValidation.Json))!.AsObject();root["metadata"]!["legacyTables"]!["etl_pipeline_param"]=JsonSerializer.SerializeToNode(new[]{new{param_name=name,param_type=type,param_value="***",secretReference=new{secretId=identifier??secret,pipelineName="PIPE",jobName=(string?)null,parameterName=name}}});return root.Deserialize<PipelineDefinition>(DraftValidation.Json)!;}
   foreach(var invalid in new[]{WithParameter("Other"),WithParameter(type:"String"),WithParameter(identifier:Guid.NewGuid())}){
    var error=await Assert.ThrowsAsync<WorkspaceException>(()=>repo.SaveAsync(draft.DraftId,new(draft.Revision,lease.Fence,invalid,layout),actor,default));Assert.Equal(422,error.StatusCode);
   }
   var valid=WithParameter();draft=await repo.SaveAsync(draft.DraftId,new(draft.Revision,lease.Fence,valid,layout),actor,default);
   Assert.DoesNotContain("cipher-unit-sentinel",JsonSerializer.Serialize(draft,DraftValidation.Json));
   var clone=JsonNode.Parse(JsonSerializer.Serialize(valid,DraftValidation.Json))!.AsObject();clone["metadata"]!["extra"]=new JsonObject{["secretReference"]=clone["metadata"]!["legacyTables"]!["etl_pipeline_param"]![0]!["secretReference"]!.DeepClone()};
   await Assert.ThrowsAsync<WorkspaceException>(()=>repo.SaveAsync(draft.DraftId,new(draft.Revision,lease.Fence,clone.Deserialize<PipelineDefinition>(DraftValidation.Json)!,layout),actor,default));
   draft=await repo.SaveAsync(draft.DraftId,new(draft.Revision,lease.Fence,valid,layout),actor,default);
   await Assert.ThrowsAsync<SqlException>(()=>Exec(c,"UPDATE dbo.etl_workspace_segredo SET ciphertext='replacement'"));
   await Assert.ThrowsAsync<SqlException>(()=>Exec(c,"DELETE dbo.etl_workspace_segredo"));
   // Import legado captura S1 na transação; alterar ativo para S2 não muda A.
   await Exec(c,"CREATE TABLE dbo.etl_job_lineage(pipeline_name NVARCHAR(200),job_name NVARCHAR(200)); CREATE TABLE dbo.etl_pipeline_param(pipeline_name NVARCHAR(200),param_name NVARCHAR(128),param_type VARCHAR(30),param_value NVARCHAR(MAX)); CREATE TABLE dbo.etl_pipeline_job(pipeline_name NVARCHAR(200),job_name NVARCHAR(200),job_type VARCHAR(100),job_command NVARCHAR(MAX)); INSERT dbo.etl_pipeline VALUES('LEGACY'); INSERT dbo.etl_pipeline_job VALUES('LEGACY','DS','datastage','job'); INSERT dbo.etl_pipeline_param VALUES('LEGACY','Senha','Encrypted','legacy-cipher-S1');");
   var legacy=await repo.ImportAsync("LEGACY",actor,default);var legacyVersion=legacy.BaseVersionId!.Value;
   await Exec(c,"UPDATE dbo.etl_pipeline_param SET param_value='legacy-cipher-S2' WHERE pipeline_name='LEGACY'; CREATE TABLE dbo.etl_workspace_publicacao(operation_id UNIQUEIDENTIFIER,version_id UNIQUEIDENTIFIER,draft_id UNIQUEIDENTIFIER,estado VARCHAR(20)); CREATE TABLE dbo.etl_workspace_pipeline(pipeline_name NVARCHAR(200),pending_operation_id UNIQUEIDENTIFIER);");
   await using(var published=new SqlCommand("INSERT dbo.etl_workspace_publicacao VALUES(NEWID(),@version,@draft,'publicado')",c)){published.Parameters.AddWithValue("@version",legacyVersion);published.Parameters.AddWithValue("@draft",legacy.DraftId);await published.ExecuteNonQueryAsync();}
   var legacyLease=await repo.LeaseAsync(legacy.DraftId,new(),actor,default);await repo.DiscardAsync(legacy.DraftId,new(legacy.Revision,legacyLease.Fence),actor,default);
   var restored=await repo.RestoreAsync("LEGACY",legacyVersion,actor,default);Assert.Empty(restored.ReadOnlyReasons);
   await using(var historical=new SqlCommand("SELECT ciphertext FROM dbo.etl_workspace_segredo_legado WHERE version_id=@version",c)){historical.Parameters.AddWithValue("@version",legacyVersion);Assert.Equal("legacy-cipher-S1",await historical.ExecuteScalarAsync());}
   Assert.DoesNotContain("legacy-cipher",JsonSerializer.Serialize(restored,DraftValidation.Json));
   // Duas conexões: uma alteração entre hash/captura deve aguardar o COMMIT.
   await Exec(c,"UPDATE dbo.etl_pipeline_param SET param_value='legacy-cipher-S1' WHERE pipeline_name='LEGACY'");
   var concurrentVersion=Guid.NewGuid();
   await using(var versionInsert=new SqlCommand("INSERT dbo.etl_workspace_versao(version_id,pipeline_name,numero,definition_json,layout_json,content_hash,criada_por) SELECT @version,pipeline_name,numero+1,definition_json,layout_json,content_hash,'QA' FROM dbo.etl_workspace_versao WHERE version_id=@source",c)){versionInsert.Parameters.AddWithValue("@version",concurrentVersion);versionInsert.Parameters.AddWithValue("@source",legacyVersion);await versionInsert.ExecuteNonQueryAsync();}
   await Exec(c,"CREATE OR ALTER PROCEDURE dbo.sp_workspace_active_hash @name NVARCHAR(200) AS BEGIN DECLARE @value NVARCHAR(MAX); SELECT @value=param_value FROM dbo.etl_pipeline_param WHERE pipeline_name=@name; SELECT LOWER(CONVERT(CHAR(64),HASHBYTES('SHA2_256',@value),2)) active_hash; WAITFOR DELAY '00:00:01'; END;");
   string expected;int sessionId;
   await using(var hash=new SqlCommand("SELECT LOWER(CONVERT(CHAR(64),HASHBYTES('SHA2_256',param_value),2)) FROM dbo.etl_pipeline_param WHERE pipeline_name='LEGACY'",c))expected=(string)(await hash.ExecuteScalarAsync())!;
   await using(var session=new SqlCommand("SELECT @@SPID",c))sessionId=Convert.ToInt32(await session.ExecuteScalarAsync());
   await using var concurrent=new SqlConnection(options.ConnectionString());await concurrent.OpenAsync();
   var capture=Exec(c,$"EXEC dbo.sp_workspace_capture_verified_legacy '{concurrentVersion}','LEGACY','{expected}'");
   var observed=false;
   for(var attempt=0;attempt<100;attempt++){await using var waiting=new SqlCommand("SELECT COUNT(*) FROM sys.dm_exec_requests WHERE session_id=@id AND wait_type='WAITFOR'",concurrent);waiting.Parameters.AddWithValue("@id",sessionId);if(Convert.ToInt32(await waiting.ExecuteScalarAsync())>0){observed=true;break;}await Task.Delay(10);}
   Assert.True(observed,"Prova de concorrência deve observar a fronteira hash/captura no servidor");
   var writer=Exec(concurrent,"UPDATE dbo.etl_pipeline_param SET param_value='legacy-cipher-S2' WHERE pipeline_name='LEGACY'");
   await Task.Delay(100);Assert.False(writer.IsCompleted,"A fonte deve continuar bloqueada durante hash/captura");
   await Task.WhenAll(capture,writer);
   await using(var historical=new SqlCommand("SELECT ciphertext FROM dbo.etl_workspace_segredo_legado WHERE version_id=@version",c)){historical.Parameters.AddWithValue("@version",concurrentVersion);Assert.Equal("legacy-cipher-S1",await historical.ExecuteScalarAsync());}
   await Exec(c,"DELETE dbo.etl_pipeline_param WHERE pipeline_name='LEGACY'");
   var restoredLease=await repo.LeaseAsync(restored.DraftId,new(),actor,default);await repo.DiscardAsync(restored.DraftId,new(restored.Revision,restoredLease.Fence),actor,default);
   var afterRemoval=await repo.RestoreAsync("LEGACY",legacyVersion,actor,default);Assert.Empty(afterRemoval.ReadOnlyReasons);
   var afterRemovalLease=await repo.LeaseAsync(afterRemoval.DraftId,new(),actor,default);await repo.DiscardAsync(afterRemoval.DraftId,new(afterRemoval.Revision,afterRemovalLease.Fence),actor,default);
   var unprovedVersion=Guid.NewGuid();
   await using(var unproved=new SqlCommand("INSERT dbo.etl_workspace_versao(version_id,pipeline_name,numero,definition_json,layout_json,content_hash,criada_por) SELECT @version,pipeline_name,numero+2,definition_json,layout_json,content_hash,'QA' FROM dbo.etl_workspace_versao WHERE version_id=@source; INSERT dbo.etl_workspace_publicacao VALUES(NEWID(),@version,@draft,'publicado')",c)){unproved.Parameters.AddWithValue("@version",unprovedVersion);unproved.Parameters.AddWithValue("@source",legacyVersion);unproved.Parameters.AddWithValue("@draft",legacy.DraftId);await unproved.ExecuteNonQueryAsync();}
   var blocked=await repo.RestoreAsync("LEGACY",unprovedVersion,actor,default);Assert.Contains(blocked.ReadOnlyReasons,reason=>reason.Contains("cifra histórica comprovada"));
   var blockedLease=await repo.LeaseAsync(blocked.DraftId,new(),actor,default);
   var readonlyError=await Assert.ThrowsAsync<WorkspaceException>(()=>repo.SaveAsync(blocked.DraftId,new(blocked.Revision,blockedLease.Fence,blocked.Definition,blocked.Layout),actor,default));Assert.Equal(409,readonlyError.StatusCode);
   // Reexecução da migration não altera nem apaga baseline histórico.
   foreach(var batch in Regex.Split(await File.ReadAllTextAsync(Path.Combine(Path.GetDirectoryName(schemaPath)!,"157_workspace_catalogo_segredos.sql")),@"^\s*GO\s*$",RegexOptions.Multiline|RegexOptions.IgnoreCase))if(!string.IsNullOrWhiteSpace(batch))await Exec(c,batch);
   await using(var unchanged=new SqlCommand("SELECT ciphertext FROM dbo.etl_workspace_segredo_legado WHERE version_id=@version",c)){unchanged.Parameters.AddWithValue("@version",legacyVersion);Assert.Equal("legacy-cipher-S1",await unchanged.ExecuteScalarAsync());}
   await using var select=new SqlCommand("SELECT definition_json FROM dbo.etl_workspace_rascunho",c);Assert.DoesNotContain("cipher-unit-sentinel",(string)(await select.ExecuteScalarAsync())!);
  }finally{SqlConnection.ClearAllPools();if(created)await Exec(master,$"ALTER DATABASE [{database}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [{database}]");}
 }
 private static async Task Exec(SqlConnection c,string sql){await using var cmd=new SqlCommand(sql,c){CommandTimeout=30};await cmd.ExecuteNonQueryAsync();}
}
