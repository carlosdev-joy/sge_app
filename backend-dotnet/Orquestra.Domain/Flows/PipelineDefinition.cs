using System.Text.Json;
using System.Text.Json.Serialization;

namespace Orquestra.Domain.Flows;

// Contrato de transporte. Validação de publicação e persistência pertencem às fases futuras.
public sealed record PipelineDefinition
{
    public int SchemaVersion { get; init; } = 1;
    public required PipelineIdentity Identity { get; init; }
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)]
    public JsonElement Metadata { get; init; }
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)]
    public JsonElement Schedule { get; init; }
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)]
    public JsonElement Parameters { get; init; }
    public IReadOnlyList<FlowNode> Nodes { get; init; } = [];
    public IReadOnlyList<FlowEdge> Edges { get; init; } = [];
    [JsonExtensionData] public Dictionary<string, JsonElement>? Extensions { get; init; }

    [JsonIgnore]
    public bool IsReadOnly => SchemaVersion != 1 || Nodes.Any(n => !FlowNode.KnownTypes.Contains(n.Type));
}

public sealed record PipelineIdentity(string PipelineName)
{
    // Undefined preserva omissão; Null preserva null explícito na fonte.
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)]
    public JsonElement DisplayName { get; init; }
    [JsonExtensionData] public Dictionary<string, JsonElement>? Extensions { get; init; }
}

public sealed record FlowNode
{
    public static readonly IReadOnlySet<string> KnownTypes = new HashSet<string>(StringComparer.Ordinal)
    {
        "datastage", "shell", "python", "storedproc", "http", "decisao", "notificacao", "sql", "aguarde",
        "email", "valida_arquivo"
    };
    public required string Id { get; init; }
    public required string Type { get; init; }
    public required JsonElement Configuration { get; init; }
    [JsonExtensionData] public Dictionary<string, JsonElement>? Extensions { get; init; }
}

public sealed record FlowEdge(string Source, string Target)
{
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)]
    public JsonElement Branch { get; init; }
    [JsonExtensionData] public Dictionary<string, JsonElement>? Extensions { get; init; }
}

public sealed record FlowLayout(int SchemaVersion, IReadOnlyDictionary<string, NodePosition> Nodes)
{
    [JsonExtensionData] public Dictionary<string, JsonElement>? Extensions { get; init; }
}
public sealed record NodePosition(double X, double Y)
{
    [JsonExtensionData] public Dictionary<string, JsonElement>? Extensions { get; init; }
}

// Nulo significa que a fonte não forneceu o dado. Não estimar capacidade ou timestamps.
public sealed record ExecutionContext(
    string CorrelationId, string? PublishedVersionId, string? Engine, string? Pool, string? Queue,
    string? Executor, string? AttemptId, DateTimeOffset? ExpectedAt, DateTimeOffset? DependenciesReleasedAt,
    DateTimeOffset? QueuedAt, DateTimeOffset? StartedAt, DateTimeOffset? CompletedAt,
    IReadOnlyDictionary<string, string> Sources);
