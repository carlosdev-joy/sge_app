using System.Net;
using System.Security.Cryptography;
using System.Text;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Orquestra.Application.Security;
using Orquestra.Application.Capabilities;
using Xunit;

namespace Orquestra.Tests;

public sealed class SecurityTests
{
    [Theory]
    [InlineData(null)] [InlineData("")] [InlineData("Bearer ")] [InlineData("bearer abc")]
    [InlineData("Basic %%%%")][InlineData("Basic YWJj")][InlineData("Bearer abc\n")]
    public async Task InvalidHeaderNeverReachesSql(string? header)
    {
        var sessions = new FakeSessions();
        var exception = await Assert.ThrowsAsync<SessionRejectedException>(() => new SessionAuthenticator(sessions, new FakeBasic()).AuthenticateAsync(header, default));
        Assert.Equal(401, exception.StatusCode); Assert.Null(sessions.LastHash);
    }

    [Fact]
    public async Task OpaqueBearerUsesExactUtf8BytesAndLowercaseSha256()
    {
        var sessions = new FakeSessions { Principal = Principal("tela_pipelines") };
        await new SessionAuthenticator(sessions, new FakeBasic()).AuthenticateAsync("Bearer token-sintético ", default);
        Assert.Equal(Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes("token-sintético "))), sessions.LastHash);
    }

    [Fact]
    public async Task ValidBasicDelegatesOnlyThisHeader()
    {
        var basic = new FakeBasic(); var sessions = new FakeSessions();
        await new SessionAuthenticator(sessions, basic).AuthenticateAsync("Basic VVNFUjpzeW50aGV0aWM=", default);
        Assert.Equal("Basic VVNFUjpzeW50aGV0aWM=", basic.LastHeader); Assert.Null(sessions.LastHash);
    }

    [Fact]
    public async Task BasicReloadsPermissionsAndFailsClosedWhenSqlIsUnavailable()
    {
        var sessions = new FakeSessions { Principal = Principal("tela_pipelines", "tela_jobs") };
        var authenticator = new SessionAuthenticator(sessions, new FakeBasic());
        var principal = await authenticator.AuthenticateAsync("Basic VVNFUjpzeW50aGV0aWM=", default);
        Assert.Contains("tela_jobs", principal.Permissions);
        sessions.Failure = new DependencyUnavailableException();
        await Assert.ThrowsAsync<DependencyUnavailableException>(() => authenticator.AuthenticateAsync("Basic VVNFUjpzeW50aGV0aWM=", default));
    }

    [Fact]
    public void ExperiencesAndAdminNameNeverGrantPermissions()
    {
        var user = new WorkspacePrincipal("SYNTHETIC", "admin", new HashSet<string>());
        var actions = WorkspaceAuthorization.Capabilities(user, true).Actions;
        Assert.False(actions.ConsultDefinition); Assert.False(actions.ConsultStages); Assert.False(actions.ConsultLogs);
        Assert.False(actions.EditDraft); Assert.False(actions.Publish); Assert.False(actions.Execute); Assert.False(actions.Administer);
    }

    [Fact]
    public void StageAndLogResourcesDoNotGrantPipelineContext()
    {
        var actions = WorkspaceAuthorization.Capabilities(Principal("tela_jobs", "tela_logs", "acao_editar", "acao_executar"), true).Actions;
        Assert.False(actions.ConsultStages); Assert.False(actions.ConsultLogs); Assert.False(actions.Execute);
    }

    [Fact]
    public void CapabilitiesDistinguishReadersAndDisableAllWrites()
    {
        var actions = WorkspaceAuthorization.Capabilities(Principal("tela_pipelines", "tela_jobs"), true).Actions;
        Assert.True(actions.ConsultDefinition); Assert.True(actions.ConsultStages); Assert.False(actions.ConsultLogs);
        Assert.False(actions.EditDraft); Assert.False(actions.Publish);
        Assert.False(WorkspaceAuthorization.Capabilities(Principal("tela_pipelines"), false).Actions.ConsultDefinition);
    }

    [Fact]
    public async Task ExpiredAndRevokedSessionCannotAccessCapabilities()
    {
        using var app = new TestApp(new FakeSessions()); using var client = app.CreateClient();
        client.DefaultRequestHeaders.Add("Authorization", "Bearer synthetic-missing");
        var response = await client.GetAsync("/workspace/capabilities");
        Assert.Equal(HttpStatusCode.Unauthorized, response.StatusCode);
        Assert.Equal("no-store", response.Headers.CacheControl?.ToString());
    }

    [Fact]
    public async Task InactiveUserIsForbiddenAndDependencyFailureIsSanitized()
    {
        var sessions = new FakeSessions { Failure = new SessionRejectedException(403, "user_inactive", "Usuário desativado no ORQUESTRA") };
        using var app = new TestApp(sessions); using var client = app.CreateClient();
        client.DefaultRequestHeaders.Add("Authorization", "Bearer synthetic");
        Assert.Equal(HttpStatusCode.Forbidden, (await client.GetAsync("/workspace/capabilities")).StatusCode);
        sessions.Failure = new DependencyUnavailableException();
        var response = await client.GetAsync("/workspace/capabilities");
        Assert.Equal(HttpStatusCode.ServiceUnavailable, response.StatusCode);
        Assert.DoesNotContain("synthetic", await response.Content.ReadAsStringAsync());
    }

    [Fact]
    public async Task LiveDoesNotRequireSqlAndReadyDoes()
    {
        using var app = new TestApp(new FakeSessions { Failure = new DependencyUnavailableException() });
        using var client = app.CreateClient();
        Assert.Equal(HttpStatusCode.OK, (await client.GetAsync("/health/live")).StatusCode);
        Assert.Equal(HttpStatusCode.ServiceUnavailable, (await client.GetAsync("/health/ready")).StatusCode);
    }

    [Fact]
    public async Task UnexpectedFailureNeverLeaksExceptionOrConfig()
    {
        using var app = new TestApp(new FakeSessions { Failure = new Exception("Password=private-fixture;server=private-fixture") });
        using var client = app.CreateClient(); client.DefaultRequestHeaders.Add("Authorization", "Bearer synthetic");
        var response = await client.GetAsync("/workspace/capabilities");
        Assert.Equal(HttpStatusCode.ServiceUnavailable, response.StatusCode);
        Assert.DoesNotContain("private-fixture", await response.Content.ReadAsStringAsync());
    }

    [Theory]
    [InlineData("/workspace/drafts/123")] [InlineData("/workspace/drafts/123/publish")] [InlineData("/workspace/pipelines")]
    public async Task FutureMutationsAreUnavailable(string path)
    {
        using var app = new TestApp(new FakeSessions { Principal = Principal("tela_pipelines", "acao_admin") });
        using var client = app.CreateClient();
        var response = await client.PostAsync(path, new StringContent("{}"));
        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
    }

    internal static WorkspacePrincipal Principal(params string[] permissions) => new("SYNTHETIC", "consulta", new HashSet<string>(permissions));
}

internal sealed class FakeSessions : ISessionRepository
{
    public WorkspacePrincipal? Principal { get; set; }
    public string? LastHash { get; private set; }
    public Exception? Failure { get; set; }
    public Task<WorkspacePrincipal?> FindValidAsync(string hash, CancellationToken cancellationToken)
    {
        LastHash = hash; if (Failure is not null) throw Failure; return Task.FromResult(Principal);
    }
    public Task CheckReadyAsync(CancellationToken cancellationToken)
    {
        if (Failure is not null) throw Failure; return Task.CompletedTask;
    }
    public Task<WorkspacePrincipal> LoadAsync(string matricula, CancellationToken cancellationToken)
    {
        if (Failure is not null) throw Failure;
        return Task.FromResult(Principal ?? SecurityTests.Principal());
    }
}

internal sealed class FakeBasic : IBasicIdentityClient
{
    public string? LastHeader { get; private set; }
    public Task<WorkspacePrincipal> AuthenticateAsync(string authorization, CancellationToken cancellationToken)
    {
        LastHeader = authorization; return Task.FromResult(SecurityTests.Principal());
    }
}

internal sealed class TestApp(FakeSessions sessions) : WebApplicationFactory<Program>
{
    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        builder.ConfigureAppConfiguration((_, configuration) => configuration.AddInMemoryCollection(new Dictionary<string, string?> { ["Workspace:Enabled"] = "true" }));
        builder.ConfigureServices(services =>
        {
            services.RemoveAll<ISessionRepository>(); services.AddSingleton<ISessionRepository>(sessions);
            services.RemoveAll<IBasicIdentityClient>(); services.AddSingleton<IBasicIdentityClient>(new FakeBasic());
        });
    }
}
