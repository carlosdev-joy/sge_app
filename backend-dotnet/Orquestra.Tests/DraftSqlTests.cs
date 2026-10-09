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

public sealed class DraftSqlTests
{
    [SqlFact]
    public async Task DraftLifecycleIsDurableFencedAuditedAndNeverWritesPublishedConfiguration()
    {
        var database = "OrquestraF2Test_" + Guid.NewGuid().ToString("N");
        var login = "OrquestraF2Login_" + Guid.NewGuid().ToString("N");
        var password = Guid.NewGuid().ToString("N") + "aA1!";
        var options = new WorkspaceSqlOptions(Environment.GetEnvironmentVariable("WORKSPACE_TEST_SQL_SERVER") ?? "127.0.0.1,1433", database, Environment.GetEnvironmentVariable("WORKSPACE_TEST_SQL_USER") ?? "sa", Environment.GetEnvironmentVariable("WORKSPACE_TEST_SQL_PASSWORD")!, true);
        await using var master = new SqlConnection((options with { Database = "master" }).ConnectionString()); await master.OpenAsync();
        var created = false; var loginCreated = false;
        try
        {
            await Execute(master, $"CREATE DATABASE [{database}] COLLATE SQL_Latin1_General_CP1_CI_AS"); created = true;
            await Execute(master, $"CREATE LOGIN [{login}] WITH PASSWORD='{password}',CHECK_POLICY=ON"); loginCreated = true;
            await using var c = new SqlConnection(options.ConnectionString()); await c.OpenAsync();
            await Execute(c, """
                CREATE TABLE dbo.etl_sessao(token_hash CHAR(64) PRIMARY KEY,matricula VARCHAR(20),expira_em DATETIME);
                CREATE TABLE dbo.etl_pipeline(pipeline_name NVARCHAR(200) PRIMARY KEY,schedule_cron NVARCHAR(100),unknown_field NVARCHAR(100));
                CREATE TABLE dbo.etl_pipeline_job(pipeline_name NVARCHAR(200),job_name NVARCHAR(200),job_type VARCHAR(100),job_command NVARCHAR(MAX),execution_order INT,depends_on_jobs NVARCHAR(MAX),condition_json NVARCHAR(MAX),layout_x FLOAT,layout_y FLOAT,PRIMARY KEY(pipeline_name,job_name));
                CREATE TABLE dbo.etl_pipeline_job_param(pipeline_name NVARCHAR(200),job_name NVARCHAR(200),param_name VARCHAR(100),param_type VARCHAR(30),param_value NVARCHAR(MAX),param_order INT,param_descricao NVARCHAR(100));
                CREATE TABLE dbo.etl_valida_arquivo_no(pipeline_name NVARCHAR(200),task_id NVARCHAR(200),ssh_conn_id VARCHAR(100),timeout_segundos INT);
                CREATE TABLE dbo.etl_valida_arquivo_config(pipeline_name NVARCHAR(200),task_id NVARCHAR(200),entrada_id UNIQUEIDENTIFIER,ordem INT,arquivo NVARCHAR(300),alvo NVARCHAR(200));
                INSERT dbo.etl_valida_arquivo_no VALUES(N'Árvore Case ',N'etapa_a ',N'conn-id',30);
                INSERT dbo.etl_valida_arquivo_config VALUES(N'Árvore Case ',N'etapa_a ',NEWID(),1,N'dados.csv',N'Próximo');
                INSERT dbo.etl_sessao VALUES(REPLICATE('a',64),'ALICE',DATEADD(hour,1,GETDATE())),(REPLICATE('b',64),'BOB',DATEADD(hour,1,GETDATE()));
                INSERT dbo.etl_pipeline VALUES(N'Árvore Case ',N'0 2 * * *',N'preservado');
                INSERT dbo.etl_pipeline_job VALUES(N'Árvore Case ',N'Etapa_A','sql',N'SELECT 1',1,NULL,N'{"future":null}',10,20),(N'Árvore Case ',N'Próximo','python',N'print(1)',2,N'Etapa_A',NULL,NULL,NULL);
                INSERT dbo.etl_pipeline_job_param VALUES(N'Árvore Case ',N'etapa_a ',N'SEGREDO','encrypted',N'gAAAAfakecipher-do-not-persist',1,N'Descrição'),(N'Árvore Case ',N'Etapa_A',N'NORMAL','string',N'valor',2,NULL);
                """);
            var repository = new SqlDraftRepository(options);
            Assert.False(await repository.SchemaAvailableAsync(default));
            var missing = await Assert.ThrowsAsync<WorkspaceException>(() => repository.GetAsync(Guid.NewGuid(), Actor('a'), default)); Assert.Equal("draft_schema_unavailable", missing.Code);
            var migration = await File.ReadAllTextAsync(Environment.GetEnvironmentVariable("WORKSPACE_TEST_SCHEMA_PATH") ?? throw new InvalidOperationException("Bancada deve indicar migration 141"));
            for (var repeat = 0; repeat < 2; repeat++) foreach (var batch in Regex.Split(migration, @"^\s*GO\s*$", RegexOptions.Multiline | RegexOptions.IgnoreCase)) if (!string.IsNullOrWhiteSpace(batch)) await Execute(c, batch);
            Assert.True(await repository.SchemaAvailableAsync(default));
            await Execute(c, $"CREATE USER [{login}] FOR LOGIN [{login}]; GRANT SELECT ON dbo.etl_sessao TO [{login}]; GRANT SELECT ON dbo.etl_pipeline TO [{login}]; GRANT SELECT ON dbo.etl_pipeline_job TO [{login}]; GRANT SELECT ON dbo.etl_pipeline_job_param TO [{login}]; GRANT SELECT ON dbo.etl_valida_arquivo_no TO [{login}]; GRANT SELECT ON dbo.etl_valida_arquivo_config TO [{login}]; GRANT SELECT,INSERT,UPDATE ON dbo.etl_workspace_rascunho TO [{login}]; GRANT SELECT,INSERT,UPDATE ON dbo.etl_workspace_lease TO [{login}]; GRANT SELECT,INSERT ON dbo.etl_workspace_versao TO [{login}]; GRANT SELECT,INSERT ON dbo.etl_workspace_evento TO [{login}]");
            var restrictedOptions = options with { User = login, Password = password }; repository = new(restrictedOptions);
            var before = await Published(c);
            var draft = await repository.ImportAsync("árvore case", Actor('a'), default);
            Assert.Equal("Árvore Case ", draft.PipelineName); Assert.NotNull(draft.BaseVersionId); Assert.Empty(draft.ReadOnlyReasons);
            var json = JsonSerializer.Serialize(draft, DraftValidation.Json);
            Assert.DoesNotContain("gAAAAfakecipher", json); Assert.Contains("secretReference", json); Assert.Equal("Descrição", draft.Definition.Nodes[0].Configuration.GetProperty("etl_pipeline_job_param")[0].GetProperty("param_descricao").GetString());
            Assert.Equal(2, draft.Definition.Nodes[0].Configuration.GetProperty("etl_pipeline_job_param").GetArrayLength());
            Assert.Equal("etapa_a ", draft.Definition.Nodes[0].Configuration.GetProperty("etl_pipeline_job_param")[0].GetProperty("job_name").GetString());
            Assert.Single(draft.Definition.Nodes[0].Configuration.GetProperty("etl_valida_arquivo_no").EnumerateArray());
            Assert.Single(draft.Definition.Nodes[0].Configuration.GetProperty("etl_valida_arquivo_config").EnumerateArray());
            Assert.Equal(10, draft.Layout.Nodes["Etapa_A"].X); Assert.False(draft.Layout.Nodes.ContainsKey("Próximo"));
            Assert.Equal("preservado", draft.Definition.Metadata.GetProperty("legacyPipeline").GetProperty("unknown_field").GetString());
            await Assert.ThrowsAsync<WorkspaceException>(() => repository.ImportAsync("Árvore Case", Actor('a'), default));
            var results = await Task.WhenAll(new[] { 'a', 'b' }.Select(async actor => { try { return (Actor: actor, Lease: await repository.LeaseAsync(draft.DraftId, new(), Actor(actor), default)); } catch (WorkspaceException e) { Assert.Equal(409, e.StatusCode); return (Actor: actor, Lease: (LeaseInfo?)null); } }));
            var winner = Assert.Single(results, r => r.Lease is not null); var loser = winner.Actor == 'a' ? 'b' : 'a'; var fence = winner.Lease!.Fence;
            await Assert.ThrowsAsync<WorkspaceException>(() => repository.SaveAsync(draft.DraftId, new(1, fence, draft.Definition, draft.Layout), Actor(loser), default));
            var reordered = JsonNode.Parse(draft.Definition.Nodes[0].Configuration.GetRawText())!;
            var reference = reordered["etl_pipeline_job_param"]![0]!["secretReference"]!.AsObject();
            var first = reference["pipelineName"]!.DeepClone(); reference.Remove("pipelineName"); reference.Add("pipelineName", first);
            var equivalent = draft.Definition with { Nodes = [draft.Definition.Nodes[0] with { Configuration = JsonSerializer.SerializeToElement(reordered) }, draft.Definition.Nodes[1]] };
            var saved = await repository.SaveAsync(draft.DraftId, new(1, fence, equivalent, draft.Layout), Actor(winner.Actor), default); Assert.Equal(2, saved.Revision);
            Assert.Equal("revision_conflict", (await Assert.ThrowsAsync<WorkspaceException>(() => repository.SaveAsync(draft.DraftId, new(1, fence, draft.Definition, draft.Layout), Actor(winner.Actor), default))).Code);
            Assert.Equal(2, (await new SqlDraftRepository(restrictedOptions).GetAsync(draft.DraftId, Actor(loser), default)).Revision);
            var transferred = await repository.TransferAsync(draft.DraftId, new(2, fence), Actor(loser), default); Assert.Equal(fence + 1, transferred.Fence);
            Assert.Equal("lease_conflict", (await Assert.ThrowsAsync<WorkspaceException>(() => repository.SaveAsync(draft.DraftId, new(2, fence, draft.Definition, draft.Layout), Actor(winner.Actor), default))).Code);
            await repository.ReleaseAsync(draft.DraftId, new(2, transferred.Fence), Actor(loser), default);
            var reacquired = await repository.LeaseAsync(draft.DraftId, new(), Actor(winner.Actor), default); Assert.Equal(fence + 2, reacquired.Fence);
            await Execute(c, $"UPDATE dbo.etl_workspace_lease SET expires_at=DATEADD(second,-1,SYSUTCDATETIME()) WHERE draft_id='{draft.DraftId}'");
            await Assert.ThrowsAsync<WorkspaceException>(() => repository.SaveAsync(draft.DraftId, new(2, reacquired.Fence, draft.Definition, draft.Layout), Actor(winner.Actor), default));
            var renewed = await repository.LeaseAsync(draft.DraftId, new(), Actor(winner.Actor), default); Assert.Equal(reacquired.Fence + 1, renewed.Fence);
            await Execute(c, "CREATE TRIGGER dbo.test_audit_failure ON dbo.etl_workspace_evento INSTEAD OF INSERT AS THROW 51002,'synthetic audit failure',1;");
            await Assert.ThrowsAsync<DependencyUnavailableException>(() => repository.SaveAsync(draft.DraftId, new(2, renewed.Fence, draft.Definition, draft.Layout), Actor(winner.Actor), default));
            Assert.Equal(2, (await repository.GetAsync(draft.DraftId, Actor('a'), default)).Revision);
            await Execute(c, "DROP TRIGGER dbo.test_audit_failure");
            await using (var restricted = new SqlConnection(restrictedOptions.ConnectionString())) { await restricted.OpenAsync(); Assert.Equal(229, (await Assert.ThrowsAsync<SqlException>(() => Execute(restricted, "UPDATE dbo.etl_pipeline_job SET job_command='forbidden'"))).Number); }
            Assert.Equal(51001, (await Assert.ThrowsAsync<SqlException>(() => Execute(c, "UPDATE dbo.etl_workspace_versao SET definition_json='{}'"))).Number);
            Assert.Equal(51001, (await Assert.ThrowsAsync<SqlException>(() => Execute(c, "DELETE dbo.etl_workspace_versao"))).Number);
            await repository.DiscardAsync(draft.DraftId, new(2, renewed.Fence), Actor(winner.Actor), default);
            Assert.Equal("descartado", (await repository.GetAsync(draft.DraftId, Actor('a'), default)).State);
            Assert.Equal(before, await Published(c));
            var newDefinition = new PipelineDefinition { Identity = new("Novo Ω ") };
            var newDraft = await repository.CreateAsync(new(newDefinition, new(1, new Dictionary<string,NodePosition>())), Actor('a'), default);
            Assert.Null(newDraft.BaseVersionId); Assert.Equal(before, await Published(c));
            await Assert.ThrowsAsync<WorkspaceException>(() => repository.CreateAsync(new(newDefinition with { Identity = new("novo ω") }, newDraft.Layout), Actor('b'), default));
            await Execute(c, "UPDATE dbo.etl_pipeline_job SET job_type='future_type' WHERE job_name=N'Etapa_A'");
            var readOnly = await repository.ImportAsync("Árvore Case", Actor('a'), default); Assert.NotEmpty(readOnly.ReadOnlyReasons);
            var readOnlyLease = await repository.LeaseAsync(readOnly.DraftId, new(), Actor('a'), default);
            Assert.Equal("draft_read_only", (await Assert.ThrowsAsync<WorkspaceException>(() => repository.SaveAsync(readOnly.DraftId, new(1,readOnlyLease.Fence,readOnly.Definition,readOnly.Layout), Actor('a'), default))).Code);
            await repository.DiscardAsync(readOnly.DraftId, new(1,readOnlyLease.Fence), Actor('a'), default);
            await Execute(c, "UPDATE dbo.etl_pipeline_job SET job_type='sql',condition_json=N'  {\"headers\":{\"Authorization\":\"short-secret\"}}' WHERE job_name=N'Etapa_A'");
            var redacted = await repository.ImportAsync("Árvore Case", Actor('a'), default); Assert.NotEmpty(redacted.ReadOnlyReasons); Assert.DoesNotContain("short-secret", JsonSerializer.Serialize(redacted, DraftValidation.Json));
            await Execute(c, "INSERT dbo.etl_pipeline VALUES(N'Tipos',NULL,NULL)");
            var order = 1;
            foreach (var type in FlowNode.KnownTypes.Order(StringComparer.Ordinal))
                await Execute(c, $"INSERT dbo.etl_pipeline_job VALUES(N'Tipos',N'{type}','{type}',N'comando original',{order++},NULL,N'{{\"future\":null}}',NULL,NULL)");
            var allTypes = await repository.ImportAsync("Tipos", Actor('a'), default); Assert.Equal(11, allTypes.Definition.Nodes.Count); Assert.Empty(allTypes.ReadOnlyReasons);
            Assert.All(allTypes.Definition.Nodes,n=>Assert.Equal("comando original",n.Configuration.GetProperty("legacyJob").GetProperty("job_command").GetString()));
            await Execute(c, "DELETE dbo.etl_sessao WHERE matricula='ALICE'");
            Assert.Equal(401, (await Assert.ThrowsAsync<WorkspaceException>(() => repository.LeaseAsync(newDraft.DraftId, new(), Actor('a'), default))).StatusCode);
            Assert.DoesNotContain(new string('a',64), await Scalar(c, "SELECT acao,detalhe FROM dbo.etl_workspace_evento FOR JSON PATH"));
        }
        finally { SqlConnection.ClearAllPools(); if (created) await Execute(master, $"ALTER DATABASE [{database}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [{database}]"); if (loginCreated) await Execute(master, $"DROP LOGIN [{login}]"); }
    }
    private static WorkspacePrincipal Actor(char id) => new(id == 'a' ? "ALICE" : "BOB", "synthetic", new HashSet<string> { "tela_pipelines", "tela_jobs", "acao_editar", "acao_admin" }) { SessionHash = new string(id,64) };
    private static Task<string> Published(SqlConnection c) => Scalar(c, "SELECT (SELECT * FROM dbo.etl_pipeline ORDER BY pipeline_name FOR JSON PATH,INCLUDE_NULL_VALUES) p,(SELECT * FROM dbo.etl_pipeline_job ORDER BY pipeline_name,job_name FOR JSON PATH,INCLUDE_NULL_VALUES) j,(SELECT * FROM dbo.etl_pipeline_job_param ORDER BY pipeline_name,job_name,param_order FOR JSON PATH,INCLUDE_NULL_VALUES) a FOR JSON PATH");
    private static async Task<string> Scalar(SqlConnection c,string sql) { await using var cmd=new SqlCommand(sql,c); return (string)(await cmd.ExecuteScalarAsync())!; }
    private static async Task Execute(SqlConnection c,string sql) { await using var cmd=new SqlCommand(sql,c){CommandTimeout=30}; await cmd.ExecuteNonQueryAsync(); }
}
