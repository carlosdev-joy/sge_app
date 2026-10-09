using Orquestra.Application.Security;

namespace Orquestra.Application.Capabilities;

public sealed record WorkspaceCapabilities(int SchemaVersion, bool Enabled, WorkspaceActions Actions, IReadOnlyList<string> KnownNodeTypes);
public sealed record WorkspaceActions(
    bool ConsultDefinition, bool ConsultStages, bool ConsultLogs,
    bool EditDraft = false, bool Publish = false, bool Execute = false,
    bool Cancel = false, bool Reprocess = false, bool Administer = false);

public static class WorkspaceAuthorization
{
    // Experiência não concede permissão; lista vazia é negativa, sem bypass por nome do perfil.
    public static WorkspaceCapabilities Capabilities(WorkspacePrincipal principal, bool enabled)
    {
        bool Has(string resource) => enabled && principal.Permissions.Contains(resource);
        var context = Has("tela_pipelines");
        return new(1, enabled, new(context, context && Has("tela_jobs"), context && Has("tela_logs")),
            Orquestra.Domain.Flows.FlowNode.KnownTypes.Order(StringComparer.Ordinal).ToArray());
    }
}
