using System.Data;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.Data.SqlClient;
using Orquestra.Application.Drafts;
using Orquestra.Application.Security;
using Orquestra.Domain.Flows;
using Orquestra.Infrastructure.Security;

namespace Orquestra.Infrastructure.Drafts;

public sealed record WorkspaceLeaseOptions(int DurationSeconds = 120);

public sealed class SqlDraftRepository(WorkspaceSqlOptions options, WorkspaceLeaseOptions? leases = null) : IDraftRepository
{
    private readonly int leaseSeconds = Math.Clamp(leases?.DurationSeconds ?? 120, 30, 600);
    private const string Columns = "draft_id,pipeline_name,base_version_id,definition_json,layout_json,revision,estado,criado_por,responsavel,criado_em,atualizado_em,read_only_json";
    private static WorkspaceException Missing() => new(503, "draft_schema_unavailable", "Rascunhos indisponíveis; aplique a migration 141_workspace_rascunhos.sql");
    private static WorkspaceException Conflict(string code, string detail) => new(409, code, detail);
    public Task<bool> SchemaAvailableAsync(CancellationToken ct) => Run(async (c, t) =>
    {
        try
        {
            foreach (var query in new[] { $"SELECT TOP(0) {Columns} FROM dbo.etl_workspace_rascunho", "SELECT TOP(0) draft_id,holder_user,holder_session_hash,fence,expires_at FROM dbo.etl_workspace_lease", "SELECT TOP(0) version_id,pipeline_name,numero,definition_json,layout_json,content_hash FROM dbo.etl_workspace_versao", "SELECT TOP(0) event_id,entidade_id,ator,acao,revision FROM dbo.etl_workspace_evento" })
            { await using var cmd = Command(c, t, query); await using var reader = await cmd.ExecuteReaderAsync(ct); }
            return true;
        }
        catch (SqlException e) when (e.Number is 208 or 207) { return false; }
    }, ct);
    public Task<PipelineContext> ContextAsync(string name, WorkspacePrincipal actor, bool stages, CancellationToken ct) => Run<PipelineContext>(async (c, t) =>
    {
        DraftValidation.Name(name);
        var available = await SchemaAvailableAsync(ct);
        Draft? draft = null;
        if (available)
        {
            await using var cmd = Command(c, t, $"SELECT {Columns} FROM dbo.etl_workspace_rascunho WHERE pipeline_name=@name AND estado='ativo'", ("@name", name));
            await using (var r = await cmd.ExecuteReaderAsync(ct)) if (await r.ReadAsync(ct)) draft = Read(r);
            if (draft is not null && stages) draft = draft with { Lease = await ReadLease(c, t, draft.DraftId, actor, false, ct) };
        }
        JsonElement? published = null;
        string canonical = draft?.PipelineName ?? name;
        if (stages)
        {
            try { var source = await LegacyFlowReader.ReadAsync(c, t, name, ct); canonical = source.Definition.Identity.PipelineName; published = JsonSerializer.SerializeToElement(new { source.Definition, source.Layout, readOnlyReasons = source.Reasons }, DraftValidation.Json); }
            catch (WorkspaceException e) when (e.StatusCode == 404 && draft is not null) { }
        }
        else
        {
            await using var cmd = Command(c, t, "SELECT pipeline_name FROM dbo.etl_pipeline WHERE pipeline_name=@name", ("@name", name));
            canonical = (await cmd.ExecuteScalarAsync(ct) as string) ?? draft?.PipelineName ?? throw new WorkspaceException(404, "pipeline_not_found", "Pipeline não encontrado");
            // Nenhuma configuração de nós é devolvida sem tela_jobs.
            draft = null;
        }
        return new(canonical, available, published, draft);
    }, ct);
    public Task<Draft> GetAsync(Guid id, WorkspacePrincipal actor, CancellationToken ct) => Run(async (c, t) =>
    {
        var draft = await Load(c, t, id, false, ct);
        return draft with { Lease = await ReadLease(c, t, id, actor, false, ct) };
    }, ct);
    public Task<Draft> CreateAsync(CreateDraft request, WorkspacePrincipal actor, CancellationToken ct) => Run(async (c, t) =>
    {
        DraftValidation.Validate(request.Definition, request.Layout);
        if (request.Definition.IsReadOnly) DraftValidation.Invalid("Novos rascunhos exigem tipos de nós suportados");
        PreserveReferences(new PipelineDefinition { Identity = request.Definition.Identity }, request.Definition);
        await CurrentSession(c, t, actor, ct);
        await using var check = Command(c, t, "SELECT pipeline_name FROM dbo.etl_pipeline WITH(UPDLOCK,HOLDLOCK) WHERE pipeline_name=@name", ("@name", request.Definition.Identity.PipelineName));
        if (await check.ExecuteScalarAsync(ct) is not null) throw Conflict("pipeline_exists", "Pipeline já publicado; importe sua configuração");
        return await Insert(c, t, request.Definition, request.Layout, null, [], actor, ct);
    }, ct);
    public Task<Draft> ImportAsync(string name, WorkspacePrincipal actor, CancellationToken ct) => Run(async (c, t) =>
    {
        DraftValidation.Name(name);
        await CurrentSession(c, t, actor, ct);
        var source = await LegacyFlowReader.ReadAsync(c, t, name, ct);
        var definition = JsonSerializer.Serialize(source.Definition, DraftValidation.Json);
        var layout = JsonSerializer.Serialize(source.Layout, DraftValidation.Json);
        var version = Guid.NewGuid();
        await using var cmd = Command(c, t, "INSERT dbo.etl_workspace_versao(version_id,pipeline_name,numero,definition_json,layout_json,content_hash,criada_por) SELECT @id,@name,ISNULL(MAX(numero),0)+1,@definition,@layout,@hash,@actor FROM dbo.etl_workspace_versao WITH(UPDLOCK,HOLDLOCK) WHERE pipeline_name=@name", ("@id", version), ("@name", source.Definition.Identity.PipelineName), ("@definition", definition), ("@layout", layout), ("@hash", Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(definition + "\n" + layout)))), ("@actor", actor.Matricula));
        await cmd.ExecuteNonQueryAsync(ct);
        return await Insert(c, t, source.Definition, source.Layout, version, source.Reasons, actor, ct);
    }, ct);
    public Task<Draft> SaveAsync(Guid id, SaveDraft request, WorkspacePrincipal actor, CancellationToken ct) => Run(async (c, t) =>
    {
        DraftValidation.Validate(request.Definition, request.Layout);
        var old = await Editable(c, t, id, actor, ct);
        Revision(old, request.ExpectedRevision);
        await OwnedLease(c, t, id, request.Fence, actor, ct);
        if (!string.Equals(old.PipelineName, request.Definition.Identity.PipelineName, StringComparison.Ordinal)) DraftValidation.Invalid("Identidade do pipeline não pode ser alterada");
        if (request.Definition.IsReadOnly) DraftValidation.Invalid("Tipo de nó não suportado para edição");
        PreserveReferences(old.Definition, request.Definition);
        await using var cmd = Command(c, t, "UPDATE dbo.etl_workspace_rascunho SET definition_json=@definition,layout_json=@layout,revision=revision+1,atualizado_em=SYSUTCDATETIME(),responsavel=@actor WHERE draft_id=@id", ("@id", id), ("@definition", JsonSerializer.Serialize(request.Definition, DraftValidation.Json)), ("@layout", JsonSerializer.Serialize(request.Layout, DraftValidation.Json)), ("@actor", actor.Matricula));
        await cmd.ExecuteNonQueryAsync(ct);
        await Audit(c, t, id, actor, "salvar", old.Revision + 1, ct);
        return (await Load(c, t, id, false, ct)) with { Lease = await ReadLease(c, t, id, actor, false, ct) };
    }, ct);
    public Task<LeaseInfo> LeaseAsync(Guid id, LeaseRequest request, WorkspacePrincipal actor, CancellationToken ct) => Run(async (c, t) =>
    {
        var draft = await Editable(c, t, id, actor, ct, true);
        var old = await ReadLease(c, t, id, actor, true, ct);
        var now = await Now(c, t, ct);
        var live = old is not null && old.ExpiresAt > now;
        if (live && !old!.HeldBySession) throw Conflict("lease_held", "Outro usuário possui a sessão de edição");
        if (request.Fence is { } fence && (old is null || old.Fence != fence || !live || !old.HeldBySession)) throw Conflict("lease_conflict", "Posse de edição expirada ou substituída");
        var next = live ? old!.Fence : checked((old?.Fence ?? 0) + 1);
        await SetLease(c, t, id, actor, next, ct, leaseSeconds);
        await Audit(c, t, id, actor, live ? "renovar_lease" : "adquirir_lease", draft.Revision, ct);
        return (await ReadLease(c, t, id, actor, false, ct))!;
    }, ct);
    public Task ReleaseAsync(Guid id, RevisionFence request, WorkspacePrincipal actor, CancellationToken ct) => MutateLease(id, request, actor, false, ct);
    public Task DiscardAsync(Guid id, RevisionFence request, WorkspacePrincipal actor, CancellationToken ct) => MutateLease(id, request, actor, true, ct);
    public Task<LeaseInfo> TransferAsync(Guid id, RevisionFence request, WorkspacePrincipal actor, CancellationToken ct) => Run(async (c, t) =>
    {
        if (!actor.Permissions.Contains("acao_admin")) throw new WorkspaceException(403, "permission_denied", "Permissão administrativa necessária");
        var draft = await Editable(c, t, id, actor, ct, true); Revision(draft, request.ExpectedRevision);
        var old = await ReadLease(c, t, id, actor, true, ct);
        if ((old?.Fence ?? 0) != request.Fence) throw Conflict("lease_conflict", "Posse de edição divergente");
        await SetLease(c, t, id, actor, checked(request.Fence + 1), ct, leaseSeconds);
        await Audit(c, t, id, actor, "transferir_lease", draft.Revision, ct);
        return (await ReadLease(c, t, id, actor, false, ct))!;
    }, ct);
    private Task MutateLease(Guid id, RevisionFence request, WorkspacePrincipal actor, bool discard, CancellationToken ct) => Run(async (c, t) =>
    {
        var draft = await Editable(c, t, id, actor, ct, true); Revision(draft, request.ExpectedRevision);
        await OwnedLease(c, t, id, request.Fence, actor, ct);
        await using var release = Command(c, t, "UPDATE dbo.etl_workspace_lease SET expires_at=SYSUTCDATETIME() WHERE draft_id=@id", ("@id", id)); await release.ExecuteNonQueryAsync(ct);
        if (discard)
        {
            await using var change = Command(c, t, "UPDATE dbo.etl_workspace_rascunho SET estado='descartado',revision=revision+1,atualizado_em=SYSUTCDATETIME(),responsavel=@actor WHERE draft_id=@id", ("@id", id), ("@actor", actor.Matricula)); await change.ExecuteNonQueryAsync(ct);
        }
        await Audit(c, t, id, actor, discard ? "descartar" : "liberar_lease", draft.Revision + (discard ? 1 : 0), ct);
        return true;
    }, ct);
    private static async Task<Draft> Editable(SqlConnection c, SqlTransaction t, Guid id, WorkspacePrincipal actor, CancellationToken ct, bool allowReadOnly = false)
    {
        var draft = await Load(c, t, id, true, ct);
        await CurrentSession(c, t, actor, ct);
        if (draft.State != "ativo") throw Conflict("draft_discarded", "Rascunho descartado");
        if (!allowReadOnly && (draft.Definition.IsReadOnly || draft.ReadOnlyReasons.Count != 0)) throw Conflict("draft_read_only", "Configuração somente leitura; consulte os motivos do rascunho");
        return draft;
    }
    private static async Task CurrentSession(SqlConnection c, SqlTransaction t, WorkspacePrincipal actor, CancellationToken ct)
    {
        if (actor.SessionHash is null) throw new WorkspaceException(401, "bearer_required", "Sessão Bearer necessária para editar");
        if (!actor.Permissions.IsSupersetOf(new[] { "tela_pipelines", "tela_jobs", "acao_editar" })) throw new WorkspaceException(403, "permission_denied", "Permissão de edição necessária");
        await using var cmd = Command(c, t, "SELECT matricula FROM dbo.etl_sessao WHERE token_hash=@hash AND expira_em>GETDATE() AND matricula=@actor", ("@hash", actor.SessionHash), ("@actor", actor.Matricula));
        if (await cmd.ExecuteScalarAsync(ct) is null) throw new WorkspaceException(401, "session_invalid", "Sessão expirada ou inválida");
    }
    private static void Revision(Draft draft, long expected) { if (draft.Revision != expected) throw Conflict("revision_conflict", "Rascunho foi alterado; recarregue antes de salvar"); }
    private static async Task OwnedLease(SqlConnection c, SqlTransaction t, Guid id, long fence, WorkspacePrincipal actor, CancellationToken ct)
    {
        var lease = await ReadLease(c, t, id, actor, true, ct);
        if (lease is null || !lease.HeldBySession || lease.Fence != fence || lease.ExpiresAt <= await Now(c, t, ct)) throw Conflict("lease_conflict", "Posse de edição expirada ou substituída");
    }
    private static async Task<Draft> Insert(SqlConnection c, SqlTransaction t, PipelineDefinition definition, FlowLayout layout, Guid? version, string[] reasons, WorkspacePrincipal actor, CancellationToken ct)
    {
        var id = Guid.NewGuid();
        await using var cmd = Command(c, t, "INSERT dbo.etl_workspace_rascunho(draft_id,pipeline_name,base_version_id,definition_json,layout_json,read_only_json,criado_por,responsavel) VALUES(@id,@name,@version,@definition,@layout,@reasons,@actor,@actor)", ("@id", id), ("@name", definition.Identity.PipelineName), ("@version", version), ("@definition", JsonSerializer.Serialize(definition, DraftValidation.Json)), ("@layout", JsonSerializer.Serialize(layout, DraftValidation.Json)), ("@reasons", JsonSerializer.Serialize(reasons)), ("@actor", actor.Matricula));
        await cmd.ExecuteNonQueryAsync(ct);
        await Audit(c, t, id, actor, version is null ? "criar" : "importar", 1, ct);
        return await Load(c, t, id, false, ct);
    }
    private static async Task<Draft> Load(SqlConnection c, SqlTransaction t, Guid id, bool locked, CancellationToken ct)
    {
        await using var cmd = Command(c, t, $"SELECT {Columns} FROM dbo.etl_workspace_rascunho {(locked ? "WITH(UPDLOCK,HOLDLOCK)" : "")} WHERE draft_id=@id", ("@id", id));
        await using var r = await cmd.ExecuteReaderAsync(ct);
        if (!await r.ReadAsync(ct)) throw new WorkspaceException(404, "draft_not_found", "Rascunho não encontrado");
        return Read(r);
    }
    private static Draft Read(SqlDataReader r) => new(r.GetGuid(0), r.GetString(1), r.IsDBNull(2) ? null : r.GetGuid(2), JsonSerializer.Deserialize<PipelineDefinition>(r.GetString(3), DraftValidation.Json)!, JsonSerializer.Deserialize<FlowLayout>(r.GetString(4), DraftValidation.Json)!, r.GetInt64(5), r.GetString(6), r.GetString(7), r.GetString(8), Utc(r.GetDateTime(9)), Utc(r.GetDateTime(10)), JsonSerializer.Deserialize<string[]>(r.GetString(11))!, null);
    private static DateTime Utc(DateTime date) => DateTime.SpecifyKind(date, DateTimeKind.Utc);
    private static async Task<LeaseInfo?> ReadLease(SqlConnection c, SqlTransaction t, Guid id, WorkspacePrincipal actor, bool locked, CancellationToken ct)
    {
        await using var cmd = Command(c, t, $"SELECT holder_user,fence,expires_at,holder_session_hash FROM dbo.etl_workspace_lease {(locked ? "WITH(UPDLOCK,HOLDLOCK)" : "")} WHERE draft_id=@id", ("@id", id));
        await using var r = await cmd.ExecuteReaderAsync(ct);
        return await r.ReadAsync(ct) ? new(r.GetString(0), r.GetInt64(1), Utc(r.GetDateTime(2)), actor.SessionHash is not null && string.Equals(r.GetString(3), actor.SessionHash, StringComparison.Ordinal) && r.GetString(0) == actor.Matricula) : null;
    }
    private static async Task<DateTime> Now(SqlConnection c, SqlTransaction t, CancellationToken ct) { await using var cmd = Command(c, t, "SELECT SYSUTCDATETIME()"); return Utc((DateTime)(await cmd.ExecuteScalarAsync(ct))!); }
    private static async Task SetLease(SqlConnection c, SqlTransaction t, Guid id, WorkspacePrincipal actor, long fence, CancellationToken ct, int seconds)
    {
        await using var cmd = Command(c, t, "UPDATE dbo.etl_workspace_lease SET holder_user=@actor,holder_session_hash=@hash,fence=@fence,expires_at=DATEADD(second,@seconds,SYSUTCDATETIME()) WHERE draft_id=@id; IF @@ROWCOUNT=0 INSERT dbo.etl_workspace_lease(draft_id,holder_user,holder_session_hash,fence,expires_at) VALUES(@id,@actor,@hash,@fence,DATEADD(second,@seconds,SYSUTCDATETIME()))", ("@id", id), ("@actor", actor.Matricula), ("@hash", actor.SessionHash), ("@fence", fence), ("@seconds", (long)seconds)); await cmd.ExecuteNonQueryAsync(ct);
    }
    private static async Task Audit(SqlConnection c, SqlTransaction t, Guid id, WorkspacePrincipal actor, string action, long revision, CancellationToken ct)
    {
        await using var cmd = Command(c, t, "INSERT dbo.etl_workspace_evento(entidade_id,ator,acao,revision) VALUES(@id,@actor,@action,@revision)", ("@id", id), ("@actor", actor.Matricula), ("@action", action), ("@revision", revision)); await cmd.ExecuteNonQueryAsync(ct);
    }
    private static void PreserveReferences(PipelineDefinition old, PipelineDefinition next)
    {
        // Referências a valores cifrados são imutáveis. Remover um parâmetro/nó é permitido;
        // recriar a referência para outra origem não é permitido.
        var allowed = References(JsonSerializer.SerializeToElement(old, DraftValidation.Json)).ToHashSet(StringComparer.Ordinal);
        if (References(JsonSerializer.SerializeToElement(next, DraftValidation.Json)).Any(r => !allowed.Contains(r))) DraftValidation.Invalid("Referência de segredo não pode ser criada ou alterada");
        static string Canonical(JsonElement value) => value.ValueKind == JsonValueKind.Object ? "{" + string.Join(",", value.EnumerateObject().OrderBy(p => p.Name, StringComparer.Ordinal).Select(p => JsonSerializer.Serialize(p.Name) + ":" + Canonical(p.Value))) + "}" : value.ValueKind == JsonValueKind.Array ? "[" + string.Join(",", value.EnumerateArray().Select(Canonical)) + "]" : value.GetRawText();
        static IEnumerable<string> References(JsonElement value)
        {
            if (value.ValueKind == JsonValueKind.Object)
                foreach (var p in value.EnumerateObject()) { if (p.Name == "secretReference") yield return Canonical(p.Value); foreach (var found in References(p.Value)) yield return found; }
            else if (value.ValueKind == JsonValueKind.Array) foreach (var item in value.EnumerateArray()) foreach (var found in References(item)) yield return found;
        }
    }
    private static SqlCommand Command(SqlConnection c, SqlTransaction t, string sql, params (string Name, object? Value)[] parameters)
    {
        var cmd = new SqlCommand(sql, c, t) { CommandTimeout = 10 };
        foreach (var (name, value) in parameters)
        {
            var parameter = value switch { Guid => new SqlParameter(name, SqlDbType.UniqueIdentifier), long => new SqlParameter(name, SqlDbType.BigInt), _ => new SqlParameter(name, SqlDbType.NVarChar, name is "@definition" or "@layout" or "@reasons" ? -1 : 200) };
            if (name == "@version") parameter = new(name, SqlDbType.UniqueIdentifier);
            parameter.Value = value ?? DBNull.Value; cmd.Parameters.Add(parameter);
        }
        return cmd;
    }
    private async Task<T> Run<T>(Func<SqlConnection, SqlTransaction, Task<T>> action, CancellationToken ct)
    {
        try
        {
            await using var c = new SqlConnection(options.ConnectionString()); await c.OpenAsync(ct);
            await using var t = (SqlTransaction)await c.BeginTransactionAsync(IsolationLevel.Serializable, ct);
            var result = await action(c, t); await t.CommitAsync(ct); return result;
        }
        catch (SqlException e) when (e.Number is 208 or 207) { throw Missing(); }
        catch (SqlException e) when (e.Number is 2601 or 2627 or 1205) { throw Conflict("draft_conflict", "Rascunho concorrente; recarregue e tente novamente"); }
        catch (SqlException) { throw new DependencyUnavailableException(); }
        catch (InvalidOperationException) { throw new DependencyUnavailableException(); }
    }
}
