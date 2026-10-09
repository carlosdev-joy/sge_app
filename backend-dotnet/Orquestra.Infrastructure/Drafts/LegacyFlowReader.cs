using System.Data;
using System.Globalization;
using System.Text.Json;
using Microsoft.Data.SqlClient;
using Orquestra.Application.Drafts;
using Orquestra.Domain.Flows;

namespace Orquestra.Infrastructure.Drafts;

// Somente configuração: nunca conexões, credenciais, snapshots ou histórico de execução.
internal static class LegacyFlowReader
{
    internal static readonly string[] OptionalTables = ["etl_pipeline_param", "etl_pipeline_job_param", "etl_valida_arquivo_no", "etl_valida_arquivo_config", "etl_pipeline_dependencia", "etl_pipeline_owner"];
    public static async Task<(PipelineDefinition Definition, FlowLayout Layout, string[] Reasons)> ReadAsync(SqlConnection connection, SqlTransaction transaction, string name, CancellationToken ct)
    {
        var pipeline = (await Rows("etl_pipeline", false)).SingleOrDefault() ?? throw new WorkspaceException(404, "pipeline_not_found", "Pipeline não encontrado");
        var canonical = Convert.ToString(pipeline["pipeline_name"], CultureInfo.InvariantCulture)!;
        var jobs = await Rows("etl_pipeline_job", false);
        var related = new Dictionary<string, List<Dictionary<string, object?>>>(StringComparer.Ordinal);
        foreach (var table in OptionalTables) related[table] = await Rows(table, true);
        var reasons = new HashSet<string>(StringComparer.Ordinal);
        var metadata = new Dictionary<string, object?> { ["legacyPipeline"] = Sanitize(pipeline, false), ["legacyTables"] = related.Where(p => p.Key != "etl_pipeline_job_param" && !p.Key.StartsWith("etl_valida_arquivo", StringComparison.Ordinal)).ToDictionary(p => p.Key, p => p.Value.Select(r => Sanitize(r, p.Key == "etl_pipeline_param")).ToArray()) };
        foreach (var table in related.Where(p => p.Key == "etl_pipeline_job_param" || p.Key.StartsWith("etl_valida_arquivo", StringComparison.Ordinal)))
            if (table.Value.Any(r => r.GetValueOrDefault("__workspace_job_name") is null)) { reasons.Add("Configuração legada referencia nó ausente"); metadata[table.Key + "Unassociated"] = table.Value.Where(r => r.GetValueOrDefault("__workspace_job_name") is null).Select(r => Sanitize(r, table.Key == "etl_pipeline_job_param")).ToArray(); }
        var positions = new Dictionary<string, NodePosition>(StringComparer.Ordinal);
        var nodes = new List<FlowNode>();
        var edges = new List<FlowEdge>();
        foreach (var job in jobs.OrderBy(j => Convert.ToInt32(j.GetValueOrDefault("execution_order") ?? 0)).ThenBy(j => Convert.ToString(j["job_name"]), StringComparer.Ordinal))
        {
            var id = Convert.ToString(job["job_name"], CultureInfo.InvariantCulture)!;
            var type = Convert.ToString(job.GetValueOrDefault("job_type") ?? "datastage", CultureInfo.InvariantCulture)!;
            var config = new Dictionary<string, object?> { ["legacyJob"] = Sanitize(job, false) };
            foreach (var table in new[] { "etl_pipeline_job_param", "etl_valida_arquivo_no", "etl_valida_arquivo_config" })
                config[table] = related[table].Where(r => string.Equals(Convert.ToString(r.GetValueOrDefault("__workspace_job_name")), id, StringComparison.Ordinal)).Select(r => Sanitize(r, table == "etl_pipeline_job_param")).ToArray();
            nodes.Add(new() { Id = id, Type = type, Configuration = JsonSerializer.SerializeToElement(config, DraftValidation.Json) });
            if (!FlowNode.KnownTypes.Contains(type)) reasons.Add($"Tipo de nó não suportado: {type}");
            if (job.GetValueOrDefault("layout_x") is { } x && job.GetValueOrDefault("layout_y") is { } y)
            {
                var dx = Convert.ToDouble(x, CultureInfo.InvariantCulture); var dy = Convert.ToDouble(y, CultureInfo.InvariantCulture);
                if (double.IsFinite(dx) && double.IsFinite(dy)) positions[id] = new(dx, dy);
                else reasons.Add("Layout legado contém posição não finita");
            }
            foreach (var dependency in (Convert.ToString(job.GetValueOrDefault("depends_on_jobs")) ?? "").Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
                edges.Add(new(dependency, id)); // Texto original e condições permanecem em legacyJob.
        }
        if (edges.Any(e => nodes.All(n => n.Id != e.Source))) reasons.Add("Dependência legada referencia nó ausente");
        var definition = new PipelineDefinition { Identity = new(canonical), Metadata = JsonSerializer.SerializeToElement(metadata, DraftValidation.Json), Nodes = nodes, Edges = edges };
        return (definition, new(1, positions), reasons.Order(StringComparer.Ordinal).ToArray());

        async Task<List<Dictionary<string, object?>>> Rows(string table, bool optional)
        {
            // Identificador somente da lista constante interna acima; nome do pipeline parametrizado.
            var jobColumn = table == "etl_pipeline_job_param" ? "job_name" : table.StartsWith("etl_valida_arquivo", StringComparison.Ordinal) ? "task_id" : null;
            var sql = jobColumn is null ? $"SELECT * FROM dbo.[{table}] WHERE pipeline_name=@name" : $"SELECT s.*,j.job_name AS __workspace_job_name FROM dbo.[{table}] s LEFT JOIN dbo.etl_pipeline_job j ON j.pipeline_name=s.pipeline_name AND j.job_name=s.[{jobColumn}] WHERE s.pipeline_name=@name";
            await using var command = new SqlCommand(sql, connection, transaction);
            command.Parameters.Add("@name", SqlDbType.NVarChar, 200).Value = name;
            var result = new List<Dictionary<string, object?>>();
            try
            {
                await using var reader = await command.ExecuteReaderAsync(ct);
                while (await reader.ReadAsync(ct))
                {
                    var row = new Dictionary<string, object?>(StringComparer.Ordinal);
                    for (var i = 0; i < reader.FieldCount; i++) row[reader.GetName(i)] = reader.IsDBNull(i) ? null : reader.GetValue(i);
                    result.Add(row);
                }
            }
            catch (SqlException e) when (optional && e.Number == 208) { }
            return result;
        }
        object? Sanitize(Dictionary<string, object?> row, bool parameters)
        {
            var element = JsonSerializer.SerializeToElement(row.Where(p => p.Key != "__workspace_job_name").ToDictionary(p => p.Key, p => p.Value), DraftValidation.Json);
            return Redact(element, parameters);
        }
        object? Redact(JsonElement element, bool parameters)
        {
            if (element.ValueKind == JsonValueKind.Object)
            {
                var encrypted = element.EnumerateObject().Any(p => p.Name.Equals("param_type", StringComparison.OrdinalIgnoreCase) && p.Value.ValueKind == JsonValueKind.String && p.Value.GetString()!.Equals("encrypted", StringComparison.OrdinalIgnoreCase));
                var result = new Dictionary<string, object?>();
                foreach (var p in element.EnumerateObject())
                {
                    var maskedParam = parameters && encrypted && p.Name.Equals("param_value", StringComparison.OrdinalIgnoreCase);
                    if ((maskedParam || DraftValidation.SecretKey(p.Name)) && p.Value.ValueKind != JsonValueKind.Null)
                    {
                        result[p.Name] = "***";
                        if (maskedParam)
                        {
                            result["tem_valor"] = p.Value.ValueKind != JsonValueKind.String || !string.IsNullOrEmpty(p.Value.GetString());
                            result["secretReference"] = new { pipelineName = canonical, jobName = rowJob(element), parameterName = element.TryGetProperty("param_name", out var param) ? param.GetString() : null };
                        }
                        else reasons.Add("Configuração contém credencial redigida; edição indisponível");
                    }
                    else result[p.Name] = Redact(p.Value, false);
                }
                return result;
            }
            if (element.ValueKind == JsonValueKind.Array) return element.EnumerateArray().Select(v => Redact(v, false)).ToArray();
            if (element.ValueKind == JsonValueKind.String)
            {
                var value = element.GetString()!;
                if (value.TrimStart().StartsWith('{') || value.TrimStart().StartsWith('['))
                {
                    try
                    {
                        using var document = JsonDocument.Parse(value);
                        if (DraftValidation.ContainsSecret(document.RootElement)) return JsonSerializer.Serialize(Redact(document.RootElement, false), DraftValidation.Json);
                    }
                    catch (JsonException) { }
                }
                if (DraftValidation.SecretValue(value)) { reasons.Add("Configuração contém credencial redigida; edição indisponível"); return "***"; }
            }
            return element.Clone();
        }
        static string? rowJob(JsonElement element) => element.TryGetProperty("job_name", out var job) ? job.GetString() : null;
    }
}
