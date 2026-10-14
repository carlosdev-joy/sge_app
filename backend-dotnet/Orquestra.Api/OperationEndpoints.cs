using System.Net.Http.Json;
using System.Text.Json;
using Orquestra.Application.Drafts;
using Orquestra.Application.Security;

internal static class OperationEndpoints
{
    public static void MapOperationEndpoints(this WebApplication app)
    {
        app.MapPost("/workspace/runs", async (string name, HttpContext context, SessionAuthenticator authentication, IConfiguration config, IHttpClientFactory factory, CancellationToken ct) =>
        {
            if (!config.GetValue<bool>("Workspace:Enabled") || !config.GetValue<bool>("Workspace:OperationsEnabled")) throw new WorkspaceException(404, "operations_disabled", "Operação contextual desabilitada");
            if (context.Request.Headers.Authorization.Count != 1) throw new SessionRejectedException(401, "session_invalid", "Autenticação necessária");
            var principal = await authentication.AuthenticateAsync(context.Request.Headers.Authorization[0], ct);
            if (principal.SessionHash is null) throw new WorkspaceException(401, "bearer_required", "Sessão Bearer necessária para operar");
            if (!new[] { "tela_pipelines", "tela_jobs", "tela_logs", "acao_executar" }.All(principal.Permissions.Contains)) throw new WorkspaceException(403, "permission_denied", "Permissão de operação necessária");
            DraftValidation.Name(name);
            var body = await DraftEndpoints.Body<JsonElement>(context, ct);
            // Nome repetido é recusado: o adaptador ficaria com o último valor, não com o conferido aqui.
            if (body.ValueKind != JsonValueKind.Object || body.EnumerateObject().Any(p => p.Name is not ("conf" or "logical_date" or "dag_run_id" or "expected_version_id" or "expected_content_hash")) || body.EnumerateObject().GroupBy(p => p.Name, StringComparer.Ordinal).Any(g => g.Count() > 1)) DraftValidation.Invalid("Campos de execução inválidos");
            // Par da publicação confirmada exibida ao abrir o pedido: os dois ou nenhum,
            // GUID canônico e 64 hexadecimais. A comparação com a publicação corrente é do
            // adaptador, sob bloqueio, antes de reservar; o par nunca segue ao Airflow.
            var hasVersion = body.TryGetProperty("expected_version_id", out var expectedVersion);
            var hasHash = body.TryGetProperty("expected_content_hash", out var expectedHash);
            if (hasVersion != hasHash || (hasVersion && !(expectedVersion.ValueKind == JsonValueKind.String && CanonicalGuid(expectedVersion.GetString()) && expectedHash.ValueKind == JsonValueKind.String && ContentHash(expectedHash.GetString())))) DraftValidation.Invalid("Publicação esperada incompleta ou inválida");
            using var deadline = CancellationTokenSource.CreateLinkedTokenSource(ct);
            deadline.CancelAfter(TimeSpan.FromSeconds(5));
            try
            {
                using var client = factory.CreateClient("workspace-read");
                using var request = new HttpRequestMessage(HttpMethod.Post, "pipeline-runs?pipeline_name=" + Uri.EscapeDataString(name)) { Content = JsonContent.Create(body) };
                request.Headers.TryAddWithoutValidation("Authorization", context.Request.Headers.Authorization[0]);
                using var response = await client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, deadline.Token);
                // Recusa marcada pelo adaptador: publicação mudou, pendente ou não informada; nada reservado.
                if (response.StatusCode == System.Net.HttpStatusCode.Conflict && response.Headers.TryGetValues("X-Workspace-Conflict", out var conflict) && conflict.Contains("publication")) throw new WorkspaceException(409, "publication_changed", "A publicação confirmada mudou, está pendente ou não foi informada pela tela; recarregue a tela e abra a solicitação novamente para executar a publicação atual");
                if (!response.IsSuccessStatusCode) throw new WorkspaceException((int)response.StatusCode is 401 or 403 or 409 or 422 ? (int)response.StatusCode : 503, "run_rejected", response.StatusCode == System.Net.HttpStatusCode.Conflict ? "Execução recusada; confira publicação, versão e atividade do pipeline" : "Não foi possível solicitar a execução");
                await using var stream = await response.Content.ReadAsStreamAsync(deadline.Token);
                await using var buffer = new MemoryStream();
                var block = new byte[8192]; int read;
                while ((read = await stream.ReadAsync(block, deadline.Token)) > 0) { if (buffer.Length + read > 128 * 1024) throw new WorkspaceException(503, "run_unavailable", "Resposta da operação excede o limite"); await buffer.WriteAsync(block.AsMemory(0, read), deadline.Token); }
                using var json = JsonDocument.Parse(buffer.GetBuffer().AsMemory(0, (int)buffer.Length));
                // Só identidade/estado, nunca conf/parâmetros retornados pelo Airflow.
                var root = json.RootElement;
                return Results.Json(new { runId = root.GetProperty("dag_run_id").GetString(), state = root.GetProperty("state").GetString() }, statusCode: 202);
            }
            catch (OperationCanceledException) when (!ct.IsCancellationRequested) { throw new WorkspaceException(503, "run_unavailable", "Operação indisponível; confira as execuções antes de repetir"); }
            catch (HttpRequestException) { throw new WorkspaceException(503, "run_unavailable", "Operação indisponível; confira as execuções antes de repetir"); }
            catch (JsonException) { throw new WorkspaceException(503, "run_unavailable", "Resposta da operação indisponível"); }
        }).RequireRateLimiting("session");
    }

    // GUID 8-4-4-4-12 sem chaves nem espaços; hash com exatamente 64 hexadecimais.
    private static bool CanonicalGuid(string? value) => value is { Length: 36 } && value.Select((c, i) => i is 8 or 13 or 18 or 23 ? c == '-' : Uri.IsHexDigit(c)).All(ok => ok);
    private static bool ContentHash(string? value) => value is { Length: 64 } && value.All(Uri.IsHexDigit);
}
