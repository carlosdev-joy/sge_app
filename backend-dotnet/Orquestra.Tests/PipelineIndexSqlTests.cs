using System.Data;
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
        var options = Options(database);
        await using var master = new SqlConnection((options with { Database = "master" }).ConnectionString()); await master.OpenAsync();
        var created = false; Exception? failure = null;
        using var running = new Running(TimeSpan.FromMinutes(3));
        try
        {
            // Collation real do legado: sem distinção de maiúsculas, com distinção de acentos.
            await Execute(master, $"CREATE DATABASE [{database}] COLLATE SQL_Latin1_General_CP1_CI_AS"); created = true;
            await using var c = new SqlConnection(options.ConnectionString()); await c.OpenAsync();
            await Execute(c, BaseTables);
            await Execute(c, """
                INSERT dbo.etl_sessao VALUES(REPLICATE('a',64),'ALICE',DATEADD(hour,1,GETDATE())),(REPLICATE('b',64),'BOB',DATEADD(hour,1,GETDATE()));
                INSERT dbo.etl_usuario(matricula,perfil_nome,primeiro_nome,ultimo_nome) VALUES('ALICE','dev','Alice','Souza'),('BOB','dev','Bob','Silva');
                INSERT dbo.etl_pipeline VALUES(N'Árvore',N'BI Corporativo',N'Cobrança','on_demand',1,1,NULL,NULL),(N'beta_inativo',N'BI Corporativo',N'',NULL,0,1,NULL,NULL),
                 (N'com%curinga',N'',N'',NULL,1,0,NULL,NULL),(N'comXcuringa',N'',N'',NULL,1,0,NULL,NULL),(N'sem_ativo',N'',N'',NULL,NULL,0,NULL,NULL),(N'PUBC',N'Proj',N'Dom','on_demand',1,1,NULL,NULL),(N'Gerido',N'Proj Projetado',N'Dom',NULL,1,1,NULL,NULL),(N'Novo_Pendente',N'Projetado',N'',NULL,1,0,NULL,NULL);
                INSERT dbo.etl_pipeline_job VALUES(N'Árvore',N'Etapa','shell','true',1,NULL,10,20),(N'PUBC',N'Etapa','shell','true',1,NULL,10,20);
                """);
            for (var i = 0; i < 120; i++) await Execute(c, $"INSERT dbo.etl_pipeline(pipeline_name,project_name,domain,active) VALUES(N'carga_{i:D3}',N'Carga',N'Lote',1)");
            var index = new SqlPipelineIndex(options);
            Assert.Equal("draft_schema_unavailable", (await Assert.ThrowsAsync<WorkspaceException>(() => index.ReadAsync(Query(), default))).Code);
            await Migrate(c);
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

            // Publicação, criação, posse e descarte concorrentes com quatro leitores: nenhuma resposta duplica ou perde
            // PUBC nem mostra a versão pendente como confirmada; nenhuma escrita vira 409 por causa do índice (a vítima
            // de deadlock é sempre a leitura, que refaz a página inteira).
            var target = await drafts.ImportAsync("PUBC", Actor('a'), default); var targetLease = await drafts.LeaseAsync(target.DraftId, new(), Actor('a'), default);
            var retriesBefore = index.DeadlockRetries; var stopsBefore = index.Stops;
            using var stop = new CancellationTokenSource();
            // Prazo finito da bancada, contado a partir dos leitores: leitura presa derruba o teste em vez de travá-lo.
            // Se a escrita falhar, o finally cancela este token e aguarda os leitores antes do DROP.
            running.Restart(TimeSpan.FromMinutes(3));
            // Busca e lista completa medidas separadamente: a falha do root foi na lista completa.
            var readers = Enumerable.Range(0, 4).Select(_ => running.Track(Task.Run(async () =>
            {
                var searchMs = new List<double>(); var fullMs = new List<double>();
                while (!stop.IsCancellationRequested)
                {
                    var clock = Stopwatch.StartNew(); var page = await index.ReadAsync(Query(search: "pubc"), running.Token); searchMs.Add(clock.Elapsed.TotalMilliseconds);
                    var row = Assert.Single(page.Items); Assert.True(row.HasDraft); Assert.True(row.HasPublished); Assert.Null(row.PublishedVersionNumber);
                    clock.Restart(); var full = await index.ReadAsync(Query(limit: 100), running.Token); fullMs.Add(clock.Elapsed.TotalMilliseconds);
                    Assert.Equal(full.Items.Count, full.Items.Select(i => i.PipelineName).Distinct(StringComparer.OrdinalIgnoreCase).Count());
                }
                return (Search: searchMs, Full: fullMs);
            }))).ToArray();
            // Cada escrita (publicação, criação, posse, descarte) é cronometrada: a escrita não pode esperar o monitor de deadlock.
            var writes = new List<double>();
            async Task<T> Write<T>(Func<Task<T>> write) { var clock = Stopwatch.StartNew(); try { return await write(); } finally { writes.Add(clock.Elapsed.TotalMilliseconds); } }
            var operationId = Guid.NewGuid();
            var operation = await Write(() => drafts.PublishAsync(target.DraftId, new(operationId, target.Revision, targetLease.Fence), Actor('a'), default));
            for (var i = 0; i < 10; i++) { var other = await Write(() => drafts.CreateAsync(new(new PipelineDefinition { Identity = new($"concorrente_{i}") }, new(1, new Dictionary<string, NodePosition>())), Actor('a'), default)); var otherLease = await Write(() => drafts.LeaseAsync(other.DraftId, new(), Actor('a'), default)); await Write(async () => { await drafts.DiscardAsync(other.DraftId, new(other.Revision, otherLease.Fence), Actor('a'), default); return true; }); }
            await Task.Delay(500);
            // Leitores terminam a volta corrente; a falha de qualquer um (asserção, SQL ou prazo) derruba o teste aqui.
            stop.Cancel();
            var samples = await Task.WhenAll(readers);
            Assert.Equal("pendente", operation.State); Assert.Equal(operationId, operation.OperationId);
            Assert.Equal(1, await Count(c, $"SELECT COUNT(*) FROM dbo.etl_workspace_publicacao WHERE draft_id='{target.DraftId}'"));
            var pending = Assert.Single((await index.ReadAsync(Query(search: "pubc"), default)).Items);
            Assert.True(pending.Managed); Assert.True(pending.HasPublished); Assert.Null(pending.PublishedVersionNumber);
            var stops = index.Stops;
            output.WriteLine($"Leituras concorrentes: busca {Percentiles(samples.SelectMany(s => s.Search))}; lista completa {Percentiles(samples.SelectMany(s => s.Full))}; escritas {Percentiles(writes)}; vítimas 1205 refeitas {index.DeadlockRetries - retriesBefore}; 503 por tentativas {stops.Exhausted - stopsBefore.Exhausted}, por prazo {stops.Expired - stopsBefore.Expired}; espera entre tentativas {(stops.Backoff - stopsBefore.Backoff).TotalMilliseconds:F0} ms; maior nº de tentativas de uma leitura bem-sucedida {stops.LongestSuccess} (bancada SQL; não é medição de produção)");
            Assert.Empty((await index.ReadAsync(Query(search: "concorrente"), default)).Items);
            Assert.DoesNotContain("definition", JsonSerializer.Serialize(await index.ReadAsync(Query(limit: 100), default), DraftValidation.Json));
        }
        catch (Exception e) { failure = e; throw; }
        finally { await Drop(running, failure, master, created ? database : null); }
    }

    // Correção EOC-F2 do deadlock: o índice lê em LOW num pool próprio, espera o dado confirmado e perde o deadlock
    // para a escrita; nenhuma sessão do pool de escrita (nem o caminho real de autoria) roda em LOW.
    [SqlFact]
    public async Task IndexRunsAtLowPriorityInItsOwnPoolWaitsForCommittedDataAndLosesTheDeadlockToWriters()
    {
        var database = "OrquestraIndexTest_" + Guid.NewGuid().ToString("N");
        var options = Options(database);
        await using var master = new SqlConnection((options with { Database = "master" }).ConnectionString()); await master.OpenAsync();
        var created = false; Exception? failure = null;
        // Pedidos deixados bloqueados e conexões com transação aberta: o finally cancela, aguarda e desfaz antes do DROP.
        using var running = new Running(TimeSpan.FromMinutes(2));
        try
        {
            await Execute(master, $"CREATE DATABASE [{database}] COLLATE SQL_Latin1_General_CP1_CI_AS"); created = true;
            await using var c = new SqlConnection(options.ConnectionString()); await c.OpenAsync();
            await Execute(c, BaseTables);
            await Execute(c, "INSERT dbo.etl_sessao VALUES(REPLICATE('a',64),'ALICE',DATEADD(hour,1,GETDATE())); INSERT dbo.etl_usuario(matricula,perfil_nome,primeiro_nome,ultimo_nome) VALUES('ALICE','dev','Alice','Souza'); INSERT dbo.etl_pipeline(pipeline_name,project_name,domain,active) VALUES(N'BLOQUEIO',N'Antes',N'Dom',1),(N'OUTRO',N'Proj',N'Dom',1)");
            await Migrate(c);
            var index = new SqlPipelineIndex(options);
            Assert.Equal(2, (await index.ReadAsync(Query(), default)).Total);

            // 1. Escrita sem commit: o índice espera (sem NOLOCK/READPAST), em LOW, READ COMMITTED, no pool próprio, e lê o confirmado.
            var writer = await running.Open(options.ConnectionString());
            var writerSession = await Int(writer, "SELECT @@SPID");
            await Execute(writer, "BEGIN TRANSACTION; UPDATE dbo.etl_pipeline SET project_name=N'Confirmado' WHERE pipeline_name=N'BLOQUEIO'");
            var read = running.Track(index.ReadAsync(Query(search: "BLOQUEIO"), running.Token));
            var reading = await Blocked(c, writerSession);
            Assert.Equal(SqlPipelineIndex.ApplicationName, reading.Program); Assert.Equal(-5, reading.Priority); Assert.Equal(2, reading.Isolation);
            Assert.False(read.IsCompleted);
            Assert.Equal(0, await Int(writer, "SELECT deadlock_priority FROM sys.dm_exec_sessions WHERE session_id=@@SPID"));
            await Execute(writer, "COMMIT");
            Assert.Equal("Confirmado", Assert.Single((await read).Items).Project);

            // 2. Depois do índice usar o pool dele: conexões de escrita continuam NORMAL, e o caminho real de autoria também.
            var writers = new List<SqlConnection>();
            try
            {
                for (var i = 0; i < 4; i++) { var w = new SqlConnection(options.ConnectionString()); writers.Add(w); await w.OpenAsync(); }
                foreach (var w in writers) Assert.Equal(0, await Int(w, "SELECT deadlock_priority FROM sys.dm_exec_sessions WHERE session_id=@@SPID"));
            }
            finally { foreach (var w in writers) await w.DisposeAsync(); }
            var blocker = await running.Open(options.ConnectionString());
            var blockerSession = await Int(blocker, "SELECT @@SPID");
            await Execute(blocker, "BEGIN TRANSACTION; INSERT dbo.etl_pipeline(pipeline_name,project_name,domain,active) VALUES(N'Criacao_Bloqueada',N'',N'',1)");
            var create = running.Track(new SqlDraftRepository(options).CreateAsync(new(new PipelineDefinition { Identity = new("Criacao_Bloqueada") }, new(1, new Dictionary<string, NodePosition>())), Actor('a'), running.Token));
            var authoring = await Blocked(c, blockerSession);
            Assert.Equal("Orquestra.Workspace", authoring.Program); Assert.Equal(0, authoring.Priority); Assert.Equal(4, authoring.Isolation);
            await Execute(blocker, "ROLLBACK");
            Assert.Equal("Criacao_Bloqueada", (await create).PipelineName);
            foreach (var session in await Sessions(c)) if (session.Program != SqlPipelineIndex.ApplicationName) Assert.Equal(0, session.Priority);

            // 3. Deadlock determinístico: sessão com a configuração do índice × sessão do pool de escrita. A do índice
            // tem mais trabalho a desfazer (sem prioridade, a escrita seria a vítima); com LOW, a vítima é o índice.
            await Execute(c, "CREATE TABLE dbo.prova_deadlock(id INT PRIMARY KEY,valor INT NOT NULL); INSERT dbo.prova_deadlock(id,valor) SELECT TOP(400) ROW_NUMBER() OVER(ORDER BY (SELECT NULL)),0 FROM sys.all_columns");
            var low = await running.Open(SqlPipelineIndex.ConnectionString(options));
            var lowSession = await Int(low, "SELECT @@SPID");
            await Execute(low, SqlPipelineIndex.SessionSettings + "BEGIN TRANSACTION; UPDATE dbo.prova_deadlock SET valor=valor+1 WHERE id=1 OR id>2");
            var normal = await running.Open(options.ConnectionString());
            var normalSession = await Int(normal, "SELECT @@SPID");
            await Execute(normal, "BEGIN TRANSACTION; UPDATE dbo.prova_deadlock SET valor=valor+1 WHERE id=2");
            var lowRead = running.Track(Execute(low, "SELECT valor FROM dbo.prova_deadlock WHERE id=2", running.Token));
            Assert.Equal(lowSession, (await Blocked(c, normalSession)).Session);
            var normalWrite = running.Track(Execute(normal, "UPDATE dbo.prova_deadlock SET valor=valor+1 WHERE id=1", running.Token));
            Assert.Equal(1205, (await Assert.ThrowsAsync<SqlException>(() => lowRead)).Number);
            await normalWrite; await Execute(normal, "COMMIT");
            Assert.Equal(1, await Int(c, "SELECT valor FROM dbo.prova_deadlock WHERE id=1"));
            Assert.Equal(1, await Int(c, "SELECT valor FROM dbo.prova_deadlock WHERE id=2"));
            Assert.Equal(0, await Int(c, "SELECT COUNT(*) FROM dbo.prova_deadlock WHERE id>2 AND valor<>0"));
        }
        catch (Exception e) { failure = e; throw; }
        finally { await Drop(running, failure, master, created ? database : null); }
    }

    // O que o teste deixou rodando (pedidos bloqueados, leitores em paralelo) e as conexões que seguram transação.
    // Todo pedido acompanhado leva Token (prazo local finito) e CommandTimeout, então a espera do fim sempre termina.
    private sealed class Running(TimeSpan limit) : IDisposable
    {
        private readonly CancellationTokenSource abort = new(limit);
        private readonly List<Task> tasks = []; private readonly List<SqlConnection> held = [];
        public CancellationToken Token => abort.Token;
        public void Restart(TimeSpan deadline) => abort.CancelAfter(deadline);
        public T Track<T>(T task) where T : Task { tasks.Add(task); return task; }
        public async Task<SqlConnection> Open(string connectionString) { var c = new SqlConnection(connectionString); held.Add(c); await c.OpenAsync(Token); return c; }
        // Cancela o que ainda roda, espera cada pedido terminar e só então desfaz as transações e fecha as conexões.
        // No caminho de sucesso o próprio teste já aguardou cada pedido e viu as falhas dele; na falha, a original é a que vale.
        public async Task<List<Exception>> StopAsync()
        {
            abort.Cancel();
            await Task.WhenAll(tasks).ConfigureAwait(ConfigureAwaitOptions.SuppressThrowing);
            var errors = new List<Exception>();
            foreach (var c in held)
            {
                try { if (c.State == ConnectionState.Open) await Execute(c, "IF @@TRANCOUNT > 0 ROLLBACK"); }
                catch (Exception e) { errors.Add(e); }
                finally { await c.DisposeAsync(); }
            }
            return errors;
        }
        public void Dispose() => abort.Dispose();
    }
    // Remove o banco só depois de nada do teste continuar rodando nele; falha da limpeza vem junto da falha original, sem escondê-la.
    private static async Task Drop(Running running, Exception? failure, SqlConnection master, string? database)
    {
        var errors = await running.StopAsync();
        SqlConnection.ClearAllPools();
        if (database is not null)
            try { await Execute(master, $"ALTER DATABASE [{database}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [{database}]"); }
            catch (Exception e) { errors.Add(e); }
        if (errors.Count > 0) throw new AggregateException("Limpeza da bancada SQL falhou", failure is null ? errors : [failure, .. errors]);
    }

    private const string BaseTables = """
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
        """;

    private static WorkspaceSqlOptions Options(string database) => new(Environment.GetEnvironmentVariable("WORKSPACE_TEST_SQL_SERVER") ?? "127.0.0.1,1433", database, Environment.GetEnvironmentVariable("WORKSPACE_TEST_SQL_USER") ?? "sa", Environment.GetEnvironmentVariable("WORKSPACE_TEST_SQL_PASSWORD")!, true);
    private static async Task Migrate(SqlConnection c)
    {
        var folder = Path.GetDirectoryName(Environment.GetEnvironmentVariable("WORKSPACE_TEST_SCHEMA_PATH"))!;
        foreach (var name in new[] { "141_workspace_rascunhos.sql", "144_workspace_publicacao.sql", "144_workspace_publicacao.sql", "146_workspace_comandos.sql", "159_workspace_lineage_hash.sql" })
            foreach (var batch in Regex.Split(await File.ReadAllTextAsync(Path.Combine(folder, name)), @"^\s*GO\s*$", RegexOptions.Multiline | RegexOptions.IgnoreCase)) if (!string.IsNullOrWhiteSpace(batch)) await Execute(c, batch);
    }
    // Pedido bloqueado pela sessão informada, visto pelo servidor (sessão, prioridade, aplicação e isolamento).
    private static async Task<(int Session, int Priority, string Program, int Isolation)> Blocked(SqlConnection monitor, int blocker)
    {
        for (var attempt = 0; attempt < 200; attempt++)
        {
            await using (var cmd = new SqlCommand("SELECT TOP(1) r.session_id,s.deadlock_priority,s.program_name,r.transaction_isolation_level FROM sys.dm_exec_requests r JOIN sys.dm_exec_sessions s ON s.session_id=r.session_id WHERE r.blocking_session_id=@blocker", monitor))
            {
                cmd.Parameters.AddWithValue("@blocker", blocker);
                await using var r = await cmd.ExecuteReaderAsync();
                if (await r.ReadAsync()) return (Convert.ToInt32(r.GetValue(0)), Convert.ToInt32(r.GetValue(1)), Convert.ToString(r.GetValue(2)) ?? "", Convert.ToInt32(r.GetValue(3)));
            }
            await Task.Delay(25);
        }
        throw new Xunit.Sdk.XunitException("Nenhum pedido ficou bloqueado pela sessão esperada");
    }
    private static async Task<List<(string Program, int Priority)>> Sessions(SqlConnection c)
    {
        await using var cmd = new SqlCommand("SELECT program_name,deadlock_priority FROM sys.dm_exec_sessions WHERE database_id=DB_ID() AND is_user_process=1", c);
        await using var r = await cmd.ExecuteReaderAsync(); var sessions = new List<(string, int)>();
        while (await r.ReadAsync()) sessions.Add((Convert.ToString(r.GetValue(0)) ?? "", Convert.ToInt32(r.GetValue(1))));
        return sessions;
    }
    private static string Percentiles(IEnumerable<double> samples)
    {
        var ms = samples.Order().ToArray();
        return ms.Length == 0 ? "n 0" : $"n {ms.Length}, p50 {ms[ms.Length / 2]:F1} ms, p95 {ms[(int)(ms.Length * 0.95)]:F1} ms, máx {ms[^1]:F1} ms";
    }
    private static PipelineIndexQuery Query(string? search = null, string? project = null, string? domain = null, string state = "all", int limit = 100, int offset = 0) => new(search, project, domain, state, limit, offset);
    private static WorkspacePrincipal Actor(char id) => new(id == 'a' ? "ALICE" : "BOB", "synthetic", new HashSet<string> { "tela_pipelines", "tela_jobs", "acao_editar", "acao_publicar" }) { SessionHash = new string(id, 64) };
    private static async Task<int> Count(SqlConnection c, string sql) { await using var cmd = new SqlCommand(sql, c); return (int)(await cmd.ExecuteScalarAsync())!; }
    private static async Task<int> Int(SqlConnection c, string sql) { await using var cmd = new SqlCommand(sql, c); return Convert.ToInt32(await cmd.ExecuteScalarAsync()); }
    private static async Task Execute(SqlConnection c, string sql, CancellationToken ct = default) { await using var cmd = new SqlCommand(sql, c) { CommandTimeout = 30 }; await cmd.ExecuteNonQueryAsync(ct); }
}
