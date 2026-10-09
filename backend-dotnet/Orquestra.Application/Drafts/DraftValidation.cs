using System.Text.Json;
using System.Text.RegularExpressions;
using Orquestra.Domain.Flows;

namespace Orquestra.Application.Drafts;

public static partial class DraftValidation
{
    public static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);
    public static void Name(string? name)
    {
        if (string.IsNullOrWhiteSpace(name) || name.Length > 200 || name.Any(char.IsControl)) Invalid("Identificador inválido (máximo 200 caracteres UTF-16)");
    }
    public static void Validate(PipelineDefinition? definition, FlowLayout? layout)
    {
        if (definition?.Identity is null || layout is null) Invalid("Definição e layout são obrigatórios");
        Name(definition!.Identity.PipelineName);
        if (definition.SchemaVersion != 1 || layout!.SchemaVersion != 1 || definition.Nodes is null || definition.Edges is null || layout.Nodes is null)
            Invalid("Contrato de rascunho inválido");
        if (definition.Nodes!.Count > 1000 || definition.Edges!.Count > 10000) Invalid("Limite de nós ou arestas excedido");
        var ids = new HashSet<string>(StringComparer.Ordinal);
        foreach (var node in definition.Nodes)
        {
            if (node is null) Invalid("Nó inválido");
            Name(node!.Id);
            if (!ids.Add(node.Id) || string.IsNullOrEmpty(node.Type) || node.Type.Length > 100 || node.Configuration.ValueKind != JsonValueKind.Object)
                Invalid("Identificador, tipo ou configuração de nó inválido");
        }
        foreach (var edge in definition.Edges)
            if (edge is null || !ids.Contains(edge.Source) || !ids.Contains(edge.Target)) Invalid("Aresta referencia nó inexistente");
        foreach (var pair in layout.Nodes!)
            if (!ids.Contains(pair.Key) || pair.Value is null || !double.IsFinite(pair.Value.X) || !double.IsFinite(pair.Value.Y)) Invalid("Posição de nó inválida");
        if (ContainsSecret(JsonSerializer.SerializeToElement(definition, Json)) || ContainsSecret(JsonSerializer.SerializeToElement(layout, Json))) Invalid("Segredos não podem ser gravados no rascunho; use referências a conexões");
    }
    public static bool SecretKey(string key) => SensitiveKey().IsMatch(key);
    public static bool SecretValue(string value) => value.StartsWith("gAAAA", StringComparison.Ordinal) || Credential().IsMatch(value);
    public static bool ContainsSecret(JsonElement value)
    {
        if (value.ValueKind == JsonValueKind.Object)
        {
            var encrypted = value.EnumerateObject().Any(p => p.Name.Equals("param_type", StringComparison.OrdinalIgnoreCase) && p.Value.ValueKind == JsonValueKind.String && p.Value.GetString()!.Equals("encrypted", StringComparison.OrdinalIgnoreCase));
            foreach (var p in value.EnumerateObject())
            {
                if ((SecretKey(p.Name) || encrypted && p.Name.Equals("param_value", StringComparison.OrdinalIgnoreCase)) && p.Value.ValueKind != JsonValueKind.Null && !(p.Value.ValueKind == JsonValueKind.String && p.Value.GetString() is "" or "***")) return true;
                if (ContainsSecret(p.Value)) return true;
            }
        }
        else if (value.ValueKind == JsonValueKind.Array) return value.EnumerateArray().Any(ContainsSecret);
        else if (value.ValueKind == JsonValueKind.String)
        {
            var text = value.GetString()!;
            if (SecretValue(text)) return true;
            if (text.TrimStart().StartsWith('{') || text.TrimStart().StartsWith('['))
                try { using var document = JsonDocument.Parse(text); return ContainsSecret(document.RootElement); } catch (JsonException) { }
        }
        return false;
    }
    [System.Diagnostics.CodeAnalysis.DoesNotReturn]
    public static void Invalid(string detail) => throw new WorkspaceException(422, "draft_invalid", detail);
    [GeneratedRegex(@"(?i)^(password|passwd|pwd|senha|secret|client_secret|access_token|refresh_token|token|authorization|api_key|apikey|connection_string|connectionstring)$")]
    private static partial Regex SensitiveKey();
    [GeneratedRegex(@"(?i)(\b(password|passwd|pwd|senha|token|secret)\s*[=:]\s*[^\s;]+|\b(Bearer|Basic)\s+[A-Za-z0-9+/=_-]{8,})")]
    private static partial Regex Credential();
}
