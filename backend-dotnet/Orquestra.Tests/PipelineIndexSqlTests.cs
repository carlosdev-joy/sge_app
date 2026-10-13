using System.Diagnostics;
using System.Text.Json;
using System.Text.RegularExpressions;
using Microsoft.Data.SqlClient;
using Orquestra.Application.Drafts;
using Orquestra.Application.Security;
using Orquestra.Domain.Flows;
using Orquestra.Infrastructure.Drafts;
using Orquestra.Infrastructure.Security;
using Xunit;
using Xunit.Abstractions;

namespace Orquestra.Tests;

public sealed class PipelineIndexSqlTests(ITestOutputHelper output)
{
    [SqlFact]
    public async Task IndexUnionsPublishedAndDraftsByRealCollationWithStablePagesFiltersLeaseAndConcurrentPublication()
    {
        var database = "OrquestraIndexTest_" + Guid.NewGuid().ToString("N");
        var options = new WorkspaceSqlOptions(Environment.GetEnvironmentVariable("WORKSPACE_TEST_SQL_SERVER") ?? "127.0.0.1,1433", database, Environment.GetEnvironmentVariable("WORKSPACE_TEST_SQL_USER") ?? "sa", Environment.GetEnvironmentVariable("WORKSPACE_TEST_SQL_PASSWORD")!, true);
        await using var master = new SqlConnection((options with { Database = "master" }).ConnectionString()); await master.OpenAsync();
        var created = false;
        try
        {
            // Collation real do legado: sem distinção de maiúsculas, com distinção de acentos.
            await Execute(master, $"CREATE DATABASE [{database}] COLLATE SQL_Latin1_General_CP1_CI_AS"); created = true;
            await using var c = new SqlConnection(options.ConnectionString()); await c.OpenAsync();
            await Execute(c, """
                CREATE TABLE dbo.etl_sessao(token_hash CHAR(64) PRIMARY KEY,matricula VARCHAR(20),expira_em DATETIME);
                CREATE TABLE dbo.etl_usuario(matricula VARCHAR(20) PRIMARY KEY,perfil_nome VARCHAR(30),primeiro_nome VARCHAR(100),ultimo_nome VARCHAR(100),ativo BIT NOT NULL DEFAULT 1);
                CREATE TABLE dbo.etl_pipeline(pipeline_name NVARCHAR(200) PRIMARY KEY,project_name NVARCHAR(50) NOT NULL DEFAULT '',domain NVARCHAR(100) NOT NULL DEFAULT '',schedule_type VARCHAR(50),active BIT,dag_criada BIT,last_execution DATETIME,updated_at DATETIME);
                CREATE TABLE dbo.etl_pipeline_job(pipeline_name NVARCHAR(200),job_name NVARCHAR(200),job_type VARCHAR(100),job_command NVARCHAR(MAX),execution_order INT,depends_on_jobs NVARCHAR(MAX),layout_x FLOAT,layout_y FLOAT,PRIMARY KEY(pipeline_name,job_name));
                CREATE TABLE dbo.etl_pipeline_param(pipeline_name NVARCHAR(200),param_name VARCHAR(128) COLLATE Latin1_General_BIN2,param_type VARCHAR(30),param_value NVARCHAR(MAX));
                CREATE TABLE dbo.etl_pipeline_job_param(pipeline_name NVARCHAR(200),job_name NVARCHAR(200),param_name VARCHAR(128) COLLATE Latin1_General_BIN2,param_type VARCHAR(30),param_value NVARCHAR(MAX));
                CREATE TABLE dbo.etl_valida_arquivo_no(pipeline_name NVARCHAR(200),task_id NVARCHAR(200),ssh_conn_id VARCHAR(100));
                CREATE TABLE dbo.etl_valida_arquivo_config(pipeline_name NVARCHAR(200),task_id NVARCHAR(200),entrada_id UNIQUEIDENTIFIER);
                CREATE TABLE dbo.etl_pipeline_execucao(pipeline_name NVARCHAR(200),status VARCHAR(100));
                CREATE TABLE dbo.etl_job_lineage(pipeline_name NVARCHAR(200),job_name NVARCHAR(200));
                INSERT dbo.etl_sessao VALUES(REPLICATE('a',64),'ALICE',DATEADD(hour,1,GETDATE())),(REPLICATE('b',64),'BOB',DATEADD(hour,1,GETDATE()));
                INSERT dbo.etl_usuario(matricula,perfil_nome,primeiro_nome,ultimo_nome) VALUES('ALICE','dev','Alice','Souza'),('BOB','dev','Bob','Silva');
                INSERT dbo.etl_pipeline VALUES(N'Árvore',N'BI Corporativo',N'Cobrança','on_demand',1,1,NULL,NULL),(N'beta_inativo',N'BI Corporativo',N'',NULL,0,1,NULL,NULL),
                 (N'com%curinga',N'',N'',NULL,1,0,NULL,NULL),(N'comXcuringa',N'',N'',NULL,1,0,NULL,NULL),(N'sem_ativo',N'',N'',NULL,NULL,0,NULL,NULL),(N'PUBC',N'Proj',N'Dom','on_demand',1,1,NULL,NULL),(N'Gerido',N'Proj Projetado',N'Dom',NULL,1,1,NULL,NULL),(N'Novo_Pendente',N'Projetado',N'',NULL,1,0,NULL,NULL);
                INSERT dbo.etl_pipeline_job VALUES(N'Árvore',N'Etapa','shell','true',1,NULL,10,20),(N'PUBC',N'Etapa','shell','true',1,NULL,10,20);
                """);
            for (var i = 0; i < 120; i++) await Execute(c, $"INSERT dbo.etl_pipeline(pipeline_name,project_name,domain,active) VALUES(N'carga_{i:D3}',N'Carga',N'Lote',1)");
            var folder = Path.GetDirectoryName(Environment.GetEnvironmentVariable("WORKSPACE_TEST_SCHEMA_PATH"))!;
            var index = new SqlPipelineIndex(options);
            Assert.Equal("draft_schema_unavailable", (await Assert.ThrowsAsync<WorkspaceException>(() => index.ReadAsync(Query(), default))).Code);
            foreach (var name in new[] { "141_workspace_rascunhos.sql", "144_workspace_publicacao.sql", "144_workspace_publicacao.sql", "146_workspace_comandos.sql", "159_workspace_lineage_hash.sql" })
                foreach (var batch in Regex.Split(await File.ReadAllTextAsync(Path.Combine(folder, name)), @"^\s*GO\s*$", RegexOptions.Multiline | RegexOptions.IgnoreCase)) if (!string.IsNullOrWhiteSpace(batch)) await Execute(c, batch);
            var drafts = new SqlDraftRepository(options);

            // Draft novo: aparece para outro leitor sem cadastro ativo nem DAG.
            var metadata = JsonSerializer.SerializeToElement(new { legacyPipeline = new { pipeline_name = "Novo Ω", project_name = "Projeto Novo", domain = "Financeiro", schedule_type = "on_demand", active = 1 } });
            var fresh = await drafts.CreateAsync(new(new PipelineDefinition { Identity = new("Novo Ω") { DisplayName = JsonSerializer.SerializeToElement("Cobrança diária") }, Metadata = metadata }, new(1, new Dictionary<string, NodePosition>())), Actor('a'), default);
            var reader = await index.ReadAsync(Query(search: "novo ω"), default);
            var only = Assert.Single(reader.Items);
            Assert.Equal("Novo Ω", only.PipelineName); Assert.Equal("Cobrança diária", only.DisplayName); Assert.True(only.HasDraft); Assert.False(only.HasPublished); Assert.Null(only.IsActive);
            Assert.Equal("Projeto Novo", only.Project); Assert.Equal("draft", only.UpdatedSource); Assert.Equal(1, only.DraftRevision); Assert.Equal("ALICE", only.Responsible);
            Assert.Equal(0, await Count(c, "SELECT COUNT(*) FROM dbo.etl_pipeline WHERE pipeline_name=N'Novo Ω'"));
            Assert.Single((await index.ReadAsync(Query(search: "cobrança diária"), default)).Items);

            // Publicado + draft com grafia diferente: uma linha, grafia publicada.
            var imported = await drafts.ImportAsync("ÁRVORE", Actor('a'), default);
            // Grafia divergente só no rascunho: igualdade decidida pela collation (CI), nunca em memória.
            await Execute(c, $"UPDATE dbo.etl_workspace_rascunho SET pipeline_name=N'ÁRVORE' WHERE draft_id='{imported.DraftId}'");
            var tree = Assert.Single((await index.ReadAsync(Query(search: "árvore"), default)).Items);
            Assert.Equal("Árvore", tree.PipelineName); Assert.True(tree.HasDraft); Assert.True(tree.HasPublished); Assert.True(tree.IsActive); Assert.False(tree.Managed); Assert.Equal("BI Corporativo", tree.Project);
            // Sensível a acento, como a collation: não normalizar em memória.
            Assert.Empty((await index.ReadAsync(Query(search: "arvore"), default)).Items);
            Assert.Single((await index.ReadAsync(Query(project: "bi corporativo", search: "árvore"), default)).Items);

            // Curingas da entrada são literais.
            Assert.Equal(new[] { "com%curinga" }, (await index.ReadAsync(Query(search: "%"), default)).Items.Select(i => i.PipelineName).ToArray());
            Assert.DoesNotContain((await index.ReadAsync(Query(search: "_"), default)).Items, i => !i.PipelineName.Contains('_'));

            // Estados coexistem; inactive exige publicado explicitamente inativo (NULL não é inativo).
            Assert.Equal(new[] { "beta_inativo" }, (await index.ReadAsync(Query(state: "inactive"), default)).Items.Select(i => i.PipelineName).ToArray());
            Assert.Null((await index.ReadAsync(Query(search: "sem_ativo"), default)).Items.Single().IsActive);
            Assert.Equal(new[] { "Árvore", "Novo Ω" }.Order(StringComparer.Ordinal), (await index.ReadAsync(Query(state: "draft"), default)).Items.Select(i => i.PipelineName).Order(StringComparer.Ordinal));
            Assert.Contains((await index.ReadAsync(Query(state: "published", search: "árvore"), default)).Items, i => i.HasDraft);

            // Gerido: resumo da versão confirmada, não da projeção; novo em reconciliação não é publicado.
            var definitionJson = JsonSerializer.Serialize(new PipelineDefinition { Identity = new("Gerido") { DisplayName = JsonSerializer.SerializeToElement("Gerido bonito") }, Metadata = JsonSerializer.SerializeToElement(new { legacyPipeline = new { project_name = "Proj Versão", domain = "Dom", active = false } }) }, DraftValidation.Json);
            var version = Guid.NewGuid();
            await Execute(c, $"INSERT dbo.etl_workspace_versao(version_id,pipeline_name,numero,origem,definition_json,layout_json,content_hash,criada_por) VALUES('{version}',N'Gerido',3,'publicada',N'{definitionJson.Replace("'", "''")}',N'{{\"schemaVersion\":1,\"nodes\":{{}}}}',REPLICATE('0',64),'ALICE'); INSERT dbo.etl_workspace_pipeline(pipeline_name,version_id) VALUES(N'Gerido','{version}')");
            var managed = Assert.Single((await index.ReadAsync(Query(search: "gerido"), default)).Items);
            Assert.True(managed.Managed); Assert.True(managed.HasPublished); Assert.Equal(3, managed.PublishedVersionNumber); Assert.Equal("Proj Versão", managed.Project); Assert.Equal("Gerido bonito", managed.DisplayName); Assert.False(managed.IsActive); Assert.Equal("version", managed.UpdatedSource);
            var pendingDraft = await drafts.CreateAsync(new(new PipelineDefinition { Identity = new("Novo_Pendente2") }, new(1, new Dictionary<string, NodePosition>())), Actor('a'), default);
            var pendingVersion = Guid.NewGuid(); var pendingOperation = Guid.NewGuid();
            await Execute(c, $"UPDATE dbo.etl_workspace_rascunho SET pipeline_name=N'Novo_Pendente' WHERE draft_id='{pendingDraft.DraftId}'; INSERT dbo.etl_workspace_versao(version_id,pipeline_name,numero,origem,definition_json,layout_json,content_hash,criada_por) VALUES('{pendingVersion}',N'Novo_Pendente',1,'publicada',N'{{}}',N'{{}}',REPLICATE('0',64),'ALICE'); INSERT dbo.etl_workspace_publicacao(operation_id,draft_id,version_id,pipeline_name,revision,fence,ator,factory_run_id) VALUES('{pendingOperation}','{pendingDraft.DraftId}','{pendingVersion}',N'Novo_Pendente',1,1,'ALICE','run_{pendingOperation:N}'); INSERT dbo.etl_workspace_pipeline(pipeline_name,pending_operation_id) VALUES(N'Novo_Pendente','{pendingOperation}')");
            var projecting = Assert.Single((await index.ReadAsync(Query(search: "novo_pendente"), default)).Items);
            Assert.False(projecting.HasPublished); Assert.True(projecting.HasDraft); Assert.Null(projecting.IsActive); Assert.Null(projecting.PublishedVersionNumber);

            // Posse: só válida, calculada no servidor, e parte do resumo de todo leitor autorizado (o índice não recebe permissão).
            var lease = await drafts.LeaseAsync(fresh.DraftId, new(), Actor('b'), default);
            var editing = Assert.Single((await index.ReadAsync(Query(state: "editing"), default)).Items);
            Assert.Equal("Novo Ω", editing.PipelineName); Assert.Equal("BOB", editing.EditorUser); Assert.Equal("Bob Silva", editing.EditorName); Assert.NotNull(editing.LeaseExpiresAt);
            // Collation: posse do rascunho de grafia divergente (ÁRVORE) aparece na única linha publicada, contada uma vez.
            await drafts.LeaseAsync(imported.DraftId, new(), Actor('b'), default);
            var editingPage = await index.ReadAsync(Query(state: "editing"), default);
            Assert.Equal(2, editingPage.Total); Assert.Equal(new[] { "Novo Ω", "Árvore" }.Order(StringComparer.Ordinal), editingPage.Items.Select(i => i.PipelineName).Order(StringComparer.Ordinal));
            var treeEditing = Assert.Single((await index.ReadAsync(Query(state: "editing", search: "ÁRVORE"), default)).Items);
            Assert.Equal("Árvore", treeEditing.PipelineName); Assert.Equal("BOB", treeEditing.EditorUser); Assert.True(treeEditing.HasPublished);
            // Resumo nunca carrega definição, layout, fence nem sessão da posse.
            var summaryJson = JsonSerializer.Serialize(editingPage, DraftValidation.Json);
            foreach (var forbidden in new[] { "definition", "layout", "fence", "session", new string('b', 64) }) Assert.DoesNotContain(forbidden, summaryJson, StringComparison.OrdinalIgnoreCase);
            Assert.Equal(1, await Count(c, $"SELECT COUNT(*) FROM dbo.etl_workspace_lease WHERE draft_id='{fresh.DraftId}' AND fence={lease.Fence}"));
            // Posse expirada (ou liberada) some do resumo e do filtro; o rascunho continua listado.
            await Execute(c, $"UPDATE dbo.etl_workspace_lease SET expires_at=DATEADD(second,-1,SYSUTCDATETIME()) WHERE draft_id IN ('{fresh.DraftId}','{imported.DraftId}')");
            var expired = await index.ReadAsync(Query(state: "editing"), default); Assert.Empty(expired.Items); Assert.Equal(0, expired.Total);
            var afterExpiry = (await index.ReadAsync(Query(search: "novo ω"), default)).Items.Single();
            Assert.True(afterExpiry.HasDraft); Assert.Null(afterExpiry.EditorUser); Assert.Null(afterExpiry.EditorName); Assert.Null(afterExpiry.LeaseExpiresAt);

            // Paginação estável: páginas disjuntas cobrem o total, mesma ordem em leituras repetidas.
            var all = new List<string>(); var totals = new HashSet<int>();
            for (var offset = 0; ; offset += 50) { var page = await index.ReadAsync(Query(limit: 50, offset: offset), default); totals.Add(page.Total); all.AddRange(page.Items.Select(i => i.PipelineName)); if (page.Items.Count < 50) break; }
            Assert.Single(totals); Assert.Equal(totals.Single(), all.Count); Assert.Equal(all.Count, all.Distinct(StringComparer.OrdinalIgnoreCase).Count());
            var again = new List<string>(); for (var offset = 0; offset < all.Count; offset += 50) again.AddRange((await index.ReadAsync(Query(limit: 50, offset: offset), default)).Items.Select(i => i.PipelineName));
            Assert.Equal(all, again);
            var beyond = await index.ReadAsync(Query(limit: 50, offset: 5000), default); Assert.Empty(beyond.Items); Assert.Equal(all.Count, beyond.Total);
            Assert.Equal(120, (await index.ReadAsync(Query(project: "carga", domain: "LOTE", limit: 100), default)).Total);

            // Publicação concorrente com leitura: nenhuma resposta duplica ou perde PUBC.
            var target = await drafts.ImportAsync("PUBC", Actor('a'), default); var targetLease = await drafts.LeaseAsync(target.DraftId, new(), Actor('a'), default);
            using var stop = new CancellationTokenSource();
            var readers = Enumerable.Range(0, 4).Select(_ => Task.Run(async () =>
            {
                var samples = new List<double>();
                while (!stop.IsCancellationRequested)
                {
                    var clock = Stopwatch.StartNew(); var page = await index.ReadAsync(Query(search: "pubc"), default); samples.Add(clock.Elapsed.TotalMilliseconds);
                    var row = Assert.Single(page.Items); Assert.True(row.HasDraft); Assert.True(row.HasPublished);
                    var full = await index.ReadAsync(Query(limit: 100), default); Assert.Equal(full.Items.Count, full.Items.Select(i => i.PipelineName).Distinct(StringComparer.OrdinalIgnoreCase).Count());
                }
                return samples;
            })).ToArray();
            var operation = await drafts.PublishAsync(target.DraftId, new(Guid.NewGuid(), target.Revision, targetLease.Fence), Actor('a'), default);
            Assert.Equal("pendente", operation.State);
            for (var i = 0; i < 5; i++) { var other = await drafts.CreateAsync(new(new PipelineDefinition { Identity = new($"concorrente_{i}") }, new(1, new Dictionary<string, NodePosition>())), Actor('a'), default); var otherLease = await drafts.LeaseAsync(other.DraftId, new(), Actor('a'), default); await drafts.DiscardAsync(other.DraftId, new(other.Revision, otherLease.Fence), Actor('a'), default); }
            await Task.Delay(500); stop.Cancel();
            var latencies = (await Task.WhenAll(readers)).SelectMany(s => s).Order().ToArray();
            var pending = Assert.Single((await index.ReadAsync(Query(search: "pubc"), default)).Items);
            Assert.True(pending.Managed); Assert.True(pending.HasPublished); Assert.Null(pending.PublishedVersionNumber);
            output.WriteLine($"Leituras concorrentes: {latencies.Length}; p50 {latencies[latencies.Length / 2]:F1} ms; p95 {latencies[(int)(latencies.Length * 0.95)]:F1} ms (bancada SQL; não é medição de produção)");
            Assert.Empty((await index.ReadAsync(Query(search: "concorrente"), default)).Items);
            Assert.DoesNotContain("definition", JsonSerializer.Serialize(await index.ReadAsync(Query(limit: 100), default), DraftValidation.Json));
        }
        finally { SqlConnection.ClearAllPools(); if (created) await Execute(master, $"ALTER DATABASE [{database}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [{database}]"); }
    }

    private static PipelineIndexQuery Query(string? search = null, string? project = null, string? domain = null, string state = "all", int limit = 100, int offset = 0) => new(search, project, domain, state, limit, offset);
    private static WorkspacePrincipal Actor(char id) => new(id == 'a' ? "ALICE" : "BOB", "synthetic", new HashSet<string> { "tela_pipelines", "tela_jobs", "acao_editar", "acao_publicar" }) { SessionHash = new string(id, 64) };
    private static async Task<int> Count(SqlConnection c, string sql) { await using var cmd = new SqlCommand(sql, c); return (int)(await cmd.ExecuteScalarAsync())!; }
    private static async Task Execute(SqlConnection c, string sql) { await using var cmd = new SqlCommand(sql, c) { CommandTimeout = 30 }; await cmd.ExecuteNonQueryAsync(); }
}
