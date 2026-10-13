using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Orquestra.Application.Drafts;
using Orquestra.Application.Security;
using Xunit;

namespace Orquestra.Tests;

public sealed class PipelineIndexTests
{
    [Theory]
    [InlineData(null, "tela_pipelines,tela_jobs", true, 401)]
    [InlineData("Bearer synthetic", "tela_jobs,tela_logs", true, 403)]
    [InlineData("Bearer synthetic", "tela_pipelines,tela_jobs", false, 404)]
    public async Task SessionPermissionAndFlagAreCheckedBeforeTheIndex(string? header, string permissions, bool enabled, int expected)
    {
        using var app = new IndexTestApp(permissions, enabled); using var client = app.CreateClient();
        if (header is not null) client.DefaultRequestHeaders.Add("Authorization", header);
        var response = await client.GetAsync("/workspace/pipeline-index");
        Assert.Equal(expected, (int)response.StatusCode); Assert.Equal(0, app.Index.Calls);
    }

    // Resumo autorizado (SPEC §Descoberta): exatamente estes campos; nenhum dado de definição, layout, fence ou sessão.
    private static readonly string[] SummaryFields = ["pipelineName", "displayName", "project", "domain", "responsible", "hasDraft", "draftRevision", "hasPublished", "publishedVersionNumber", "isActive", "managed", "updatedAt", "updatedSource", "editorUser", "editorName", "leaseExpiresAt"];

    [Theory]
    [InlineData("tela_pipelines")]
    [InlineData("tela_pipelines,tela_jobs")]
    public async Task EveryAuthorizedReaderSeesTheValidEditorAndFiltersEditingButNeverProtectedData(string permissions)
    {
        using var app = new IndexTestApp(permissions, true); using var client = Authorized(app);
        var response = await client.GetAsync("/workspace/pipeline-index");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var body = await response.Content.ReadAsStringAsync();
        var item = JsonDocument.Parse(body).RootElement.GetProperty("items")[0];
        Assert.Equal("BOB", item.GetProperty("editorUser").GetString()); Assert.Equal("Bob Silva", item.GetProperty("editorName").GetString());
        Assert.Equal(new DateTime(2026, 10, 11, 12, 2, 0, DateTimeKind.Utc), item.GetProperty("leaseExpiresAt").GetDateTime().ToUniversalTime());
        Assert.Equal(SummaryFields.Order(StringComparer.Ordinal), item.EnumerateObject().Select(p => p.Name).Order(StringComparer.Ordinal));
        Assert.Equal(new[] { "items", "limit", "offset", "total" }, JsonDocument.Parse(body).RootElement.EnumerateObject().Select(p => p.Name).Order(StringComparer.Ordinal));
        foreach (var forbidden in new[] { "definition", "layout", "fence", "session", "readOnly", "secret" }) Assert.DoesNotContain(forbidden, body, StringComparison.OrdinalIgnoreCase);
        // Filtrar edição em andamento é parte do resumo: 200 com o mesmo estado repassado ao índice.
        var editing = await client.GetAsync("/workspace/pipeline-index?state=editing");
        Assert.Equal(HttpStatusCode.OK, editing.StatusCode);
        Assert.Equal("editing", app.Index.LastQuery!.State); Assert.Equal(2, app.Index.Calls);
        Assert.Equal("BOB", (await editing.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("items")[0].GetProperty("editorUser").GetString());
    }

    [Fact]
    public async Task ReaderWithoutStagesStillCannotReadTheDraftDefinitionOrLease()
    {
        // O índice não amplia o restante do grupo: rotas de etapas/rascunho continuam exigindo tela_jobs.
        using var app = new IndexTestApp("tela_pipelines", true); using var client = Authorized(app);
        var draft = await client.GetAsync("/workspace/drafts/" + Guid.NewGuid());
        Assert.Equal(HttpStatusCode.Forbidden, draft.StatusCode);
        Assert.Equal("permission_denied", (await draft.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("code").GetString());
        Assert.Equal(0, app.Index.Calls);
    }

    [Fact]
    public async Task ReaderWithStagesSeesWhoEditsWithServerComputedLease()
    {
        using var app = new IndexTestApp("tela_pipelines,tela_jobs", true); using var client = Authorized(app);
        var page = await client.GetFromJsonAsync<JsonElement>("/workspace/pipeline-index?state=editing&search=%20cobran%C3%A7a%20&project=BI&domain=Cobran%C3%A7a&limit=10&offset=20");
        Assert.Equal(new PipelineIndexQuery("cobrança", "BI", "Cobrança", "editing", 10, 20), app.Index.LastQuery);
        var item = page.GetProperty("items")[0];
        Assert.Equal("BOB", item.GetProperty("editorUser").GetString()); Assert.Equal("Bob Silva", item.GetProperty("editorName").GetString());
        Assert.Equal(3, page.GetProperty("total").GetInt32()); Assert.Equal(10, page.GetProperty("limit").GetInt32()); Assert.Equal(20, page.GetProperty("offset").GetInt32());
    }

    [Theory]
    [InlineData("limit=0")]
    [InlineData("limit=101")]
    [InlineData("limit=abc")]
    [InlineData("limit=-1")]
    [InlineData("limit=%2B5")]
    [InlineData("offset=-1")]
    [InlineData("offset=1000001")]
    [InlineData("offset=1.5")]
    [InlineData("state=publicado")]
    [InlineData("state=ALL")]
    [InlineData("search=a%00b")]
    [InlineData("project=a%0Ab")]
    public async Task InvalidInputIsRejectedInPortugueseBeforeTheDatabase(string query)
    {
        using var app = new IndexTestApp("tela_pipelines,tela_jobs", true); using var client = Authorized(app);
        var response = await client.GetAsync("/workspace/pipeline-index?" + query);
        Assert.Equal(422, (int)response.StatusCode);
        var error = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("index_invalid", error.GetProperty("code").GetString()); Assert.Equal(0, app.Index.Calls);
    }

    [Fact]
    public async Task OversizedSearchIsRejectedAndDefaultsAreBounded()
    {
        using var app = new IndexTestApp("tela_pipelines,tela_jobs", true); using var client = Authorized(app);
        Assert.Equal(422, (int)(await client.GetAsync("/workspace/pipeline-index?search=" + new string('x', 201))).StatusCode);
        Assert.Equal(HttpStatusCode.OK, (await client.GetAsync("/workspace/pipeline-index?search=" + new string('x', 200) + "&limit=100&state=")).StatusCode);
        Assert.Equal(new PipelineIndexQuery(new string('x', 200), null, null, "all", 100, 0), app.Index.LastQuery);
        Assert.Equal(HttpStatusCode.OK, (await client.GetAsync("/workspace/pipeline-index?search=%20%20&project=")).StatusCode);
        Assert.Equal(new PipelineIndexQuery(null, null, null, "all", 50, 0), app.Index.LastQuery);
    }

    [Fact]
    public async Task ClientCancellationReachesTheIndexQuery()
    {
        using var app = new IndexTestApp("tela_pipelines,tela_jobs", true) ; app.Index.Block = true; using var client = Authorized(app);
        using var cancel = new CancellationTokenSource();
        var request = client.GetAsync("/workspace/pipeline-index?search=a", cancel.Token);
        await app.Index.Started.Task.WaitAsync(TimeSpan.FromSeconds(10));
        cancel.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => request);
        Assert.True(await app.Index.Cancelled.Task.WaitAsync(TimeSpan.FromSeconds(10)));
    }

    [Fact]
    public async Task MissingSchemaIsAnHonest503NamingTheMigration()
    {
        using var app = new IndexTestApp("tela_pipelines", true); app.Index.Failure = new WorkspaceException(503, "draft_schema_unavailable", "Rascunhos indisponíveis; aplique a migration 141_workspace_rascunhos.sql");
        using var client = Authorized(app);
        var response = await client.GetAsync("/workspace/pipeline-index");
        Assert.Equal(HttpStatusCode.ServiceUnavailable, response.StatusCode);
        var error = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("draft_schema_unavailable", error.GetProperty("code").GetString()); Assert.Contains("141", error.GetProperty("detail").GetString());
    }

    [Fact]
    public void LikePatternTreatsWildcardsAsLiteralsAndSummaryRedactsCredentials()
    {
        Assert.Equal("%a[%]b[_]c[[]d]%", PipelineIndexRules.LikePattern("a%b_c[d]"));
        Assert.Equal("%cobrança%", PipelineIndexRules.LikePattern("cobrança"));
        Assert.Equal("[conteúdo protegido]", PipelineIndexRules.Summary("password=abc123"));
        Assert.Equal("[conteúdo protegido]", PipelineIndexRules.Summary("gAAAAcipher"));
        Assert.Equal("Cobrança", PipelineIndexRules.Summary("Cobrança")); Assert.Null(PipelineIndexRules.Summary(null));
    }

    [Fact]
    public async Task RepositoryHasNoPermissionGateAndFailsHonestlyWithoutDatabase()
    {
        // Sem banco configurado: dependência indisponível (503), nunca 403 nem lista vazia, em qualquer estado.
        var index = new Orquestra.Infrastructure.Drafts.SqlPipelineIndex(new Orquestra.Infrastructure.Security.WorkspaceSqlOptions("", "", "", ""));
        foreach (var state in PipelineIndexRules.States)
            await Assert.ThrowsAsync<DependencyUnavailableException>(() => index.ReadAsync(new(null, null, null, state, 50, 0), default));
    }

    private static HttpClient Authorized(IndexTestApp app) { var client = app.CreateClient(); client.DefaultRequestHeaders.Add("Authorization", "Bearer synthetic"); return client; }
}

internal sealed class IndexTestApp(string permissions, bool enabled) : WebApplicationFactory<Program>
{
    public StubIndex Index { get; } = new();
    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        builder.ConfigureAppConfiguration((_, c) => c.AddInMemoryCollection(new Dictionary<string, string?> { ["Workspace:Enabled"] = enabled.ToString(), ["Workspace:DraftsEnabled"] = "true" }));
        builder.ConfigureServices(s => { s.RemoveAll<ISessionRepository>(); s.AddSingleton<ISessionRepository>(new FakeSessions { Principal = SecurityTests.Principal(permissions.Split(',')) }); s.RemoveAll<IBasicIdentityClient>(); s.AddSingleton<IBasicIdentityClient>(new FakeBasic()); s.RemoveAll<IPipelineIndex>(); s.AddSingleton<IPipelineIndex>(Index); });
    }
}

internal sealed class StubIndex : IPipelineIndex
{
    public int Calls { get; private set; }
    public PipelineIndexQuery? LastQuery { get; private set; }
    public bool Block { get; set; }
    public WorkspaceException? Failure { get; set; }
    public TaskCompletionSource Started { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
    public TaskCompletionSource<bool> Cancelled { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
    public async Task<PipelineIndexPage> ReadAsync(PipelineIndexQuery query, CancellationToken ct)
    {
        Calls++; LastQuery = query;
        if (Failure is not null) throw Failure;
        if (Block)
        {
            Started.TrySetResult();
            try { await Task.Delay(Timeout.Infinite, ct); }
            catch (OperationCanceledException) { Cancelled.TrySetResult(true); throw; }
        }
        // Posse válida já calculada pelo índice; o endpoint a repassa a todo leitor autorizado.
        var item = new PipelineIndexItem("cobranca_diaria", "Cobrança diária", "BI", "Cobrança", "ALICE", true, 4, false, null, null, false,
            new DateTime(2026, 10, 11, 12, 0, 0, DateTimeKind.Utc), "draft", "BOB", "Bob Silva", new DateTime(2026, 10, 11, 12, 2, 0, DateTimeKind.Utc));
        return new(3, query.Limit, query.Offset, [item]);
    }
}
