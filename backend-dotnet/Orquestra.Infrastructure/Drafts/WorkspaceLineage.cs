using System.Text.Json;
using System.Text.Json.Nodes;
using Orquestra.Application.Drafts;
using Orquestra.Domain.Flows;
namespace Orquestra.Infrastructure.Drafts;

// Captura conhecida e vazia difere de snapshot histórico sem captura.
internal static class WorkspaceLineage
{
    internal const string Marker = "workspaceLineageVersion";
    internal const string Table = "etl_job_lineage";
    internal static bool Captured(PipelineDefinition definition) => definition.Metadata.ValueKind == JsonValueKind.Object && definition.Metadata.TryGetProperty(Marker, out var value) && value.ValueKind == JsonValueKind.Number && value.TryGetInt32(out var version) && version == 1;
    internal static PipelineDefinition Initialize(PipelineDefinition definition)
    {
        var metadata = definition.Metadata.ValueKind == JsonValueKind.Object ? JsonNode.Parse(definition.Metadata.GetRawText())!.AsObject() : new JsonObject();
        if (metadata.ContainsKey(Marker) && !Captured(definition)) DraftValidation.Invalid("Contrato de lineage inválido");
        metadata[Marker] = 1;
        var nodes = definition.Nodes.Select(node => {
            var configuration = JsonNode.Parse(node.Configuration.GetRawText())!.AsObject();
            if (!configuration.ContainsKey(Table)) configuration[Table] = new JsonArray();
            return node with { Configuration = JsonSerializer.SerializeToElement(configuration, DraftValidation.Json) };
        }).ToArray();
        var result = definition with { Metadata = JsonSerializer.SerializeToElement(metadata, DraftValidation.Json), Nodes = nodes };
        Validate(result, result);
        return result;
    }
    internal static void Validate(PipelineDefinition before, PipelineDefinition after)
    {
        bool HasMarker(PipelineDefinition d) => d.Metadata.ValueKind == JsonValueKind.Object && d.Metadata.TryGetProperty(Marker, out _);
        if (Captured(before) != Captured(after) || HasMarker(before) != HasMarker(after) || HasMarker(after) && !Captured(after)) DraftValidation.Invalid("Contrato de lineage não pode ser alterado; conclua ou descarte e reimporte o rascunho");
        var captured = Captured(after);
        if (captured && after.Nodes.Any(node => node.Configuration.ValueKind != JsonValueKind.Object || !node.Configuration.TryGetProperty(Table, out var rows) || rows.ValueKind != JsonValueKind.Array || rows.GetArrayLength() > 5000 || rows.EnumerateArray().Any(row => row.ValueKind != JsonValueKind.Object))) DraftValidation.Invalid("Cada etapa exige uma lista de lineage válida");
        // Apenas as posições versionadas são aceitas; JSON avançado não muda a autoridade.
        Walk(JsonSerializer.SerializeToElement(after, DraftValidation.Json), "");
        void Walk(JsonElement value, string path)
        {
            if (value.ValueKind == JsonValueKind.Object) foreach (var property in value.EnumerateObject())
            {
                if (property.Name.Equals(Marker, StringComparison.OrdinalIgnoreCase) && !(property.Name == Marker && path == "/metadata")) DraftValidation.Invalid("Marca de lineage fora do contrato");
                if (property.Name.Equals(Table, StringComparison.OrdinalIgnoreCase) && !(captured && property.Name == Table && path == "/nodes/*/configuration")) DraftValidation.Invalid("Lineage fora do contrato de captura");
                Walk(property.Value, path + "/" + property.Name);
            }
            else if (value.ValueKind == JsonValueKind.Array) foreach (var child in value.EnumerateArray()) Walk(child, path + "/*");
        }
    }
}
