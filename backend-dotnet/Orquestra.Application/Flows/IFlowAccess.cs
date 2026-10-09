using Orquestra.Domain.Flows;

namespace Orquestra.Application.Flows;

public sealed record FlowReadResult(PipelineDefinition Definition, FlowLayout Layout, IReadOnlyList<string> ReadOnlyReasons);

// F1 especifica acesso; não conecta o editor nem habilita escrita na configuração ativa.
public interface IFlowAccess
{
    Task<FlowReadResult> ReadPublishedAsync(PipelineIdentity identity, CancellationToken cancellationToken);
}
