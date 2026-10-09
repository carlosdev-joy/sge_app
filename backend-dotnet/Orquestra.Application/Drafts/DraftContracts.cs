using System.Text.Json;
using Orquestra.Application.Security;
using Orquestra.Domain.Flows;

namespace Orquestra.Application.Drafts;

public sealed record Draft(Guid DraftId, string PipelineName, Guid? BaseVersionId, PipelineDefinition Definition,
    FlowLayout Layout, long Revision, string State, string CreatedBy, string Responsible, DateTime CreatedAt,
    DateTime UpdatedAt, IReadOnlyList<string> ReadOnlyReasons, LeaseInfo? Lease);
public sealed record LeaseInfo(string HolderUser, long Fence, DateTime ExpiresAt, bool HeldBySession);
public sealed record CreateDraft(PipelineDefinition Definition, FlowLayout Layout);
public sealed record SaveDraft(long ExpectedRevision, long Fence, PipelineDefinition Definition, FlowLayout Layout);
public sealed record LeaseRequest(long? Fence = null);
public sealed record RevisionFence(long ExpectedRevision, long Fence);
public sealed record PipelineContext(string PipelineName, bool DraftsAvailable, JsonElement? Published, Draft? Draft);
public sealed class WorkspaceException(int statusCode, string code, string detail) : Exception(detail)
{
    public int StatusCode { get; } = statusCode;
    public string Code { get; } = code;
}
public interface IDraftRepository
{
    Task<bool> SchemaAvailableAsync(CancellationToken ct);
    Task<PipelineContext> ContextAsync(string name, WorkspacePrincipal actor, bool stages, CancellationToken ct);
    Task<Draft> GetAsync(Guid id, WorkspacePrincipal actor, CancellationToken ct);
    Task<Draft> CreateAsync(CreateDraft request, WorkspacePrincipal actor, CancellationToken ct);
    Task<Draft> ImportAsync(string name, WorkspacePrincipal actor, CancellationToken ct);
    Task<Draft> SaveAsync(Guid id, SaveDraft request, WorkspacePrincipal actor, CancellationToken ct);
    Task<LeaseInfo> LeaseAsync(Guid id, LeaseRequest request, WorkspacePrincipal actor, CancellationToken ct);
    Task ReleaseAsync(Guid id, RevisionFence request, WorkspacePrincipal actor, CancellationToken ct);
    Task<LeaseInfo> TransferAsync(Guid id, RevisionFence request, WorkspacePrincipal actor, CancellationToken ct);
    Task DiscardAsync(Guid id, RevisionFence request, WorkspacePrincipal actor, CancellationToken ct);
}
