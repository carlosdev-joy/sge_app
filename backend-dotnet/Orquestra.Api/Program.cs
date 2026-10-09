using System.Text.Json;
using System.Threading.RateLimiting;
using Microsoft.AspNetCore.RateLimiting;
using Orquestra.Application.Capabilities;
using Orquestra.Application.Drafts;
using Orquestra.Infrastructure.Drafts;
using Orquestra.Application.Security;
using Orquestra.Infrastructure.Security;

var builder = WebApplication.CreateBuilder(args);
builder.Services.ConfigureHttpJsonOptions(options => options.SerializerOptions.PropertyNamingPolicy = JsonNamingPolicy.CamelCase);
// Não usar logging de requests/headers nem mensagens de exceptions SQL/HTTP com configuração interna.
builder.Logging.AddFilter("System.Net.Http.HttpClient", LogLevel.None);
builder.Services.AddSingleton(new WorkspaceSqlOptions(
    builder.Configuration["Workspace:Sql:Server"] ?? "",
    builder.Configuration["Workspace:Sql:Database"] ?? "",
    builder.Configuration["Workspace:Sql:User"] ?? "",
    builder.Configuration["Workspace:Sql:Password"] ?? "",
    builder.Configuration.GetValue<bool>("Workspace:Sql:TrustServerCertificate")));
builder.Services.AddScoped<ISessionRepository, SqlSessionRepository>();
builder.Services.AddScoped<IDraftRepository, SqlDraftRepository>();
builder.Services.AddScoped<IPublicationRepository, SqlDraftRepository>();
builder.Services.AddSingleton(new WorkspaceLeaseOptions(builder.Configuration.GetValue<int?>("Workspace:LeaseSeconds") ?? 120));
builder.Services.AddScoped<SessionAuthenticator>();
builder.Services.AddScoped<PublishedExecutionClient>();
builder.Services.AddScoped<LegacyPublicationValidationClient>();
builder.Services.AddHttpClient("workspace-read", client =>
{
    var address = new Uri(builder.Configuration["Workspace:LegacyApiUrl"] ?? "http://orquestra-api:8000/", UriKind.Absolute);
    if (address.Scheme != "http" && address.Scheme != "https") throw new InvalidOperationException("URL interna inválida");
    client.BaseAddress = address;
    client.Timeout = TimeSpan.FromSeconds(5);
}).ConfigurePrimaryHttpMessageHandler(() => new HttpClientHandler { AllowAutoRedirect = false, UseProxy = false });
builder.Services.AddHttpClient<IBasicIdentityClient, LegacyBasicIdentityClient>(client =>
{
    var url = builder.Configuration["Workspace:LegacyApiUrl"] ?? "http://orquestra-api:8000/";
    var address = new Uri(url, UriKind.Absolute);
    if (address.Scheme != "http" && address.Scheme != "https") throw new InvalidOperationException("URL interna inválida");
    client.BaseAddress = address;
    client.Timeout = TimeSpan.FromSeconds(5);
}).ConfigurePrimaryHttpMessageHandler(() => new HttpClientHandler { AllowAutoRedirect = false, UseProxy = false });
builder.Services.AddRateLimiter(options =>
{
    options.AddConcurrencyLimiter("session", limiter => { limiter.PermitLimit = 32; limiter.QueueLimit = 0; });
    options.OnRejected = async (context, ct) =>
    {
        context.HttpContext.Response.StatusCode = 429;
        await context.HttpContext.Response.WriteAsJsonAsync(new { detail = "Limite de consultas atingido", code = "rate_limited" }, ct);
    };
});

var app = builder.Build();
app.Use(async (context, next) =>
{
    context.Response.Headers.CacheControl = "no-store";
    try { await next(); }
    catch (WorkspaceException exception) { await Error(context, exception.StatusCode, exception.Code, exception.Message); }
    catch (DependencyUnavailableException) { await Error(context, 503, "dependency_unavailable", "Dependência do workspace indisponível"); }
    catch (SessionRejectedException exception) { await Error(context, exception.StatusCode, exception.Code, exception.Message); }
    catch (OperationCanceledException) when (context.RequestAborted.IsCancellationRequested) { }
    catch (Exception)
    {
        app.Logger.LogError("Falha interna no workspace; detalhes redigidos");
        await Error(context, 503, "workspace_unavailable", "Workspace indisponível");
    }
});
app.UseRateLimiter();
app.MapGet("/health/live", () => Results.Json(new { status = "ok", contractVersion = 1 }));
app.MapGet("/health/ready", async (ISessionRepository repository, IDraftRepository drafts, IConfiguration configuration, CancellationToken ct) =>
{
    await repository.CheckReadyAsync(ct);
    if (configuration.GetValue<bool>("Workspace:DraftsEnabled") && !await drafts.SchemaAvailableAsync(ct))
        throw new WorkspaceException(503, "draft_schema_unavailable", "Rascunhos indisponíveis; aplique a migration 141_workspace_rascunhos.sql");
    return Results.Json(new { status = "ok", contractVersion = 1 });
});
// Roteadas no mesmo prefixo público /orquestra/workspace/* pelo proxy DEV.
app.MapGet("/workspace/health/live", () => Results.Json(new { status = "ok", contractVersion = 1 }));
app.MapGet("/workspace/health/ready", async (ISessionRepository repository, IDraftRepository drafts, IConfiguration configuration, CancellationToken ct) =>
{
    await repository.CheckReadyAsync(ct);
    if (configuration.GetValue<bool>("Workspace:DraftsEnabled") && !await drafts.SchemaAvailableAsync(ct))
        throw new WorkspaceException(503, "draft_schema_unavailable", "Rascunhos indisponíveis; aplique a migration 141_workspace_rascunhos.sql");
    return Results.Json(new { status = "ok", contractVersion = 1 });
});
app.MapGet("/workspace/capabilities", async (HttpContext context, SessionAuthenticator authentication, IConfiguration configuration, CancellationToken ct) =>
{
    if (context.Request.Headers.Authorization.Count != 1)
        throw new SessionRejectedException(401, "session_invalid", "Autenticação necessária");
    var principal = await authentication.AuthenticateAsync(context.Request.Headers.Authorization[0], ct);
    var capabilities = WorkspaceAuthorization.Capabilities(principal, configuration.GetValue<bool>("Workspace:Enabled"));
    if (capabilities.Actions.ConsultStages && principal.SessionHash is not null && configuration.GetValue<bool>("Workspace:DraftsEnabled") && await context.RequestServices.GetRequiredService<IDraftRepository>().SchemaAvailableAsync(ct))
        capabilities = capabilities with { Actions = capabilities.Actions with { EditDraft = principal.Permissions.Contains("acao_editar"), Administer = principal.Permissions.Contains("acao_editar") && principal.Permissions.Contains("acao_admin") } };
    if(capabilities.Actions.ConsultStages && configuration.GetValue<bool>("Workspace:PublicationsEnabled") && await context.RequestServices.GetRequiredService<IPublicationRepository>().PublicationSchemaAsync(ct)) capabilities=capabilities with { Actions=capabilities.Actions with { ConsultVersions=true, Publish=capabilities.Actions.EditDraft && principal.Permissions.Contains("acao_publicar") } };
    return Results.Json(capabilities);
}).RequireRateLimiting("session");
app.MapDraftEndpoints();
app.MapPublicationEndpoints();
app.MapFallback(() => Results.Json(new { detail = "Recurso do workspace indisponível nesta fase", code = "not_found" }, statusCode: 404));
app.Run();

static Task Error(HttpContext context, int status, string code, string detail)
{
    context.Response.StatusCode = status;
    return context.Response.WriteAsJsonAsync(new { detail, code });
}

public partial class Program;
