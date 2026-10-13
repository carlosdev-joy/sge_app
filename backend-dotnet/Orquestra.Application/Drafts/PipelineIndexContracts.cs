namespace Orquestra.Application.Drafts;

// F2: índice de descoberta. Somente resumo; nunca definição, layout, SQL, segredos ou fence/sessão da posse.
public sealed record PipelineIndexQuery(string? Search, string? Project, string? Domain, string State, int Limit, int Offset);
// Campos que a fonte não informa são null. Edição em andamento (editor*) só com posse válida calculada no servidor;
// é resumo autorizado com tela_pipelines, inclusive sem tela_jobs (SPEC §Descoberta).
public sealed record PipelineIndexItem(
    string PipelineName, string? DisplayName, string? Project, string? Domain, string? Responsible,
    bool HasDraft, long? DraftRevision, bool HasPublished, int? PublishedVersionNumber, bool? IsActive, bool Managed,
    DateTime? UpdatedAt, string? UpdatedSource, string? EditorUser, string? EditorName, DateTime? LeaseExpiresAt);
public sealed record PipelineIndexPage(int Total, int Limit, int Offset, IReadOnlyList<PipelineIndexItem> Items);

public interface IPipelineIndex
{
    // Mesmo resumo para todo leitor autorizado: nenhum campo depende de tela_jobs.
    Task<PipelineIndexPage> ReadAsync(PipelineIndexQuery query, CancellationToken ct);
}

public static class PipelineIndexRules
{
    public const int DefaultLimit = 50, MaxLimit = 100, MaxOffset = 1_000_000;
    public static readonly IReadOnlySet<string> States = new HashSet<string>(StringComparer.Ordinal) { "all", "draft", "published", "editing", "inactive" };

    // Validação antes do banco: 422 em português, sem ecoar a entrada.
    public static PipelineIndexQuery Parse(string? search, string? project, string? domain, string? state, string? limit, string? offset)
    {
        var parsedState = string.IsNullOrEmpty(state) ? "all" : state;
        if (!States.Contains(parsedState)) Invalid("Filtro de estado inválido");
        var parsedLimit = DefaultLimit;
        if (limit is not null && (!int.TryParse(limit, System.Globalization.NumberStyles.None, System.Globalization.CultureInfo.InvariantCulture, out parsedLimit) || parsedLimit is < 1 or > MaxLimit)) Invalid($"Limite deve estar entre 1 e {MaxLimit}");
        var parsedOffset = 0;
        if (offset is not null && (!int.TryParse(offset, System.Globalization.NumberStyles.None, System.Globalization.CultureInfo.InvariantCulture, out parsedOffset) || parsedOffset > MaxOffset)) Invalid("Deslocamento deve ser um número não negativo");
        return new(Text(search, "Busca"), Text(project, "Projeto"), Text(domain, "Domínio"), parsedState, parsedLimit, parsedOffset);
    }

    // LIKE do SQL Server: curingas da entrada viram literais; a comparação segue a collation da coluna.
    public static string LikePattern(string search) => "%" + search.Replace("[", "[[]", StringComparison.Ordinal).Replace("%", "[%]", StringComparison.Ordinal).Replace("_", "[_]", StringComparison.Ordinal) + "%";

    // Valor com aparência de credencial nunca sai no resumo.
    public static string? Summary(string? value) => value is null ? null : DraftValidation.SecretValue(value) ? "[conteúdo protegido]" : value;

    private static string? Text(string? value, string label)
    {
        var trimmed = value?.Trim();
        if (string.IsNullOrEmpty(trimmed)) return null;
        if (trimmed.Length > 200 || trimmed.Any(char.IsControl)) Invalid($"{label}: máximo 200 caracteres UTF-16, sem caracteres de controle");
        return trimmed;
    }
    [System.Diagnostics.CodeAnalysis.DoesNotReturn]
    private static void Invalid(string detail) => throw new WorkspaceException(422, "index_invalid", detail);
}
