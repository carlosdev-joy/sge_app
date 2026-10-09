using System.Text.Json;
using Orquestra.Application.Drafts;
using Orquestra.Application.Security;

internal static class DraftEndpoints
{
    public static void MapDraftEndpoints(this WebApplication app)
    {
        var group = app.MapGroup("/workspace").RequireRateLimiting("session");
        group.AddEndpointFilter(async (invocation, next) =>
        {
            var context = invocation.HttpContext;
            var config = context.RequestServices.GetRequiredService<IConfiguration>();
            if (!config.GetValue<bool>("Workspace:Enabled")) throw new WorkspaceException(404, "workspace_disabled", "Workspace desabilitado");
            if (context.Request.Headers.Authorization.Count != 1) throw new SessionRejectedException(401, "session_invalid", "Autenticação necessária");
            var actor = await context.RequestServices.GetRequiredService<SessionAuthenticator>().AuthenticateAsync(context.Request.Headers.Authorization[0], context.RequestAborted);
            if (!actor.Permissions.Contains("tela_pipelines")) throw new WorkspaceException(403, "permission_denied", "Permissão de consulta necessária");
            if (context.Request.Path.StartsWithSegments("/workspace/executions") && !actor.Permissions.Contains("tela_logs")) throw new WorkspaceException(403, "permission_denied", "Permissão de consulta dos logs necessária");
            var mutation = context.Request.Method != "GET";
            var pipelineContext = context.Request.Method == "GET" && (context.Request.Path.StartsWithSegments("/workspace/pipelines") || context.Request.Path.StartsWithSegments("/workspace/pipeline-context"));
            if (!pipelineContext && !actor.Permissions.Contains("tela_jobs")) throw new WorkspaceException(403, "permission_denied", "Permissão de consulta das etapas necessária");
            if (mutation)
            {
                if (!config.GetValue<bool>("Workspace:DraftsEnabled")) throw new WorkspaceException(503, "drafts_disabled", "Edição de rascunhos desabilitada");
                if (actor.SessionHash is null) throw new WorkspaceException(401, "bearer_required", "Sessão Bearer necessária para editar");
                if (!actor.Permissions.Contains("acao_editar")) throw new WorkspaceException(403, "permission_denied", "Permissão de edição necessária");
            }
            context.Items["workspaceActor"] = actor;
            return await next(invocation);
        });
        group.MapGet("/pipeline-context", async (string name, HttpContext c, IDraftRepository repository, IConfiguration configuration, CancellationToken ct) => Results.Json((await repository.ContextAsync(name, Actor(c), Actor(c).Permissions.Contains("tela_jobs"), ct)) with { EnvironmentLabel = configuration["Workspace:EnvironmentLabel"] ?? "Workspace" }));
        group.MapPost("/pipeline-drafts", async (string name, HttpContext c, IDraftRepository repository, CancellationToken ct) => Results.Json(await repository.ImportAsync(name, Actor(c), ct), statusCode: 201));
        group.MapGet("/executions", async (string name, string? date, HttpContext c, PublishedExecutionClient client, CancellationToken ct) => Results.Json(await client.ReadAsync(name, date, c.Request.Headers.Authorization[0]!, ct)));
        group.MapGet("/pipelines/{name}", async (string name, HttpContext c, IDraftRepository repository, CancellationToken ct) => Results.Json(await repository.ContextAsync(name, Actor(c), Actor(c).Permissions.Contains("tela_jobs"), ct)));
        group.MapGet("/drafts/{id:guid}", async (Guid id, HttpContext c, IDraftRepository repository, CancellationToken ct) => Results.Json(await repository.GetAsync(id, Actor(c), ct)));
        group.MapPost("/pipelines", async (HttpContext c, IDraftRepository repository, CancellationToken ct) => Results.Json(await repository.CreateAsync(await Body<CreateDraft>(c, ct), Actor(c), ct), statusCode: 201));
        group.MapPost("/pipelines/{name}/drafts", async (string name, HttpContext c, IDraftRepository repository, CancellationToken ct) => Results.Json(await repository.ImportAsync(name, Actor(c), ct), statusCode: 201));
        group.MapPut("/drafts/{id:guid}", async (Guid id, HttpContext c, IDraftRepository repository, CancellationToken ct) => Results.Json(await repository.SaveAsync(id, await Body<SaveDraft>(c, ct), Actor(c), ct)));
        group.MapPost("/drafts/{id:guid}/lease", async (Guid id, HttpContext c, IDraftRepository repository, CancellationToken ct) => Results.Json(await repository.LeaseAsync(id, await Body<LeaseRequest>(c, ct), Actor(c), ct)));
        group.MapDelete("/drafts/{id:guid}/lease", async (Guid id, HttpContext c, IDraftRepository repository, CancellationToken ct) => { await repository.ReleaseAsync(id, await Body<RevisionFence>(c, ct), Actor(c), ct); return Results.NoContent(); });
        group.MapPost("/drafts/{id:guid}/transfer", async (Guid id, HttpContext c, IDraftRepository repository, CancellationToken ct) => Results.Json(await repository.TransferAsync(id, await Body<RevisionFence>(c, ct), Actor(c), ct)));
        group.MapDelete("/drafts/{id:guid}", async (Guid id, HttpContext c, IDraftRepository repository, CancellationToken ct) => { await repository.DiscardAsync(id, await Body<RevisionFence>(c, ct), Actor(c), ct); return Results.NoContent(); });
    }
    private static WorkspacePrincipal Actor(HttpContext c) => (WorkspacePrincipal)c.Items["workspaceActor"]!;
    private static async Task<T> Body<T>(HttpContext c, CancellationToken ct)
    {
        const int limit = 1024 * 1024;
        if (!c.Request.HasJsonContentType()) throw new WorkspaceException(422, "draft_invalid", "Corpo JSON obrigatório");
        if (c.Request.ContentLength > limit) throw new WorkspaceException(422, "body_too_large", "Corpo excede 1 MiB");
        await using var buffer = new MemoryStream();
        var block = new byte[8192];
        int read;
        while ((read = await c.Request.Body.ReadAsync(block, ct)) != 0)
        {
            if (buffer.Length + read > limit) throw new WorkspaceException(422, "body_too_large", "Corpo excede 1 MiB");
            await buffer.WriteAsync(block.AsMemory(0, read), ct);
        }
        try { return JsonSerializer.Deserialize<T>(buffer.GetBuffer().AsSpan(0, (int)buffer.Length), DraftValidation.Json) ?? throw new JsonException(); }
        catch (JsonException) { throw new WorkspaceException(422, "draft_invalid", "Corpo JSON inválido"); }
    }
}
