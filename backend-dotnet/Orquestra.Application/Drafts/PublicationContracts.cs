using System.Text.Json;
using Orquestra.Application.Security;
using Orquestra.Domain.Flows;
namespace Orquestra.Application.Drafts;
public sealed record PublicationCommand(Guid OperationId,long ExpectedRevision,long Fence);
public sealed record ValidationDiagnostic(string? NodeId,string Field,string Code,string Message);
public sealed record PublicationValidation(long Revision,bool Valid,IReadOnlyList<ValidationDiagnostic> Diagnostics);
public sealed record Publication(Guid OperationId,Guid DraftId,Guid VersionId,string PipelineName,long Revision,string State,int Attempts,string? Error,DateTime CreatedAt,DateTime UpdatedAt,bool Projected);
public sealed record PublishedVersion(Guid VersionId,int Number,string Origin,string ContentHash,PipelineDefinition Definition,FlowLayout Layout,string CreatedBy,DateTime CreatedAt,string State);
public sealed record RestoreVersion(Guid VersionId);
public interface IPublicationRepository
{
 Task<bool> PublicationSchemaAsync(CancellationToken ct);
 Task<Publication> PublishAsync(Guid id,PublicationCommand command,WorkspacePrincipal actor,CancellationToken ct);
 Task<Publication> RetryAsync(Guid operation,PublicationCommand command,WorkspacePrincipal actor,CancellationToken ct);
 Task<IReadOnlyList<Publication>> PublicationsAsync(Guid draft,CancellationToken ct);
 Task<Publication> PublicationAsync(Guid id,CancellationToken ct);
 Task<IReadOnlyList<PublishedVersion>> VersionsAsync(string name,CancellationToken ct);
 Task<Draft> RestoreAsync(string name,Guid version,WorkspacePrincipal actor,CancellationToken ct);
}
public static class PublicationValidationRules
{
 public static PublicationValidation Validate(Draft draft)
 {
  var errors=new List<ValidationDiagnostic>();void Error(string? node,string field,string code,string message)=>errors.Add(new(node,field,code,message));
  try{DraftValidation.Validate(draft.Definition,draft.Layout);}catch(WorkspaceException e){Error(null,"definition",e.Code,e.Message);}
  foreach(var reason in draft.ReadOnlyReasons)Error(null,"definition","read_only",reason);
  if(!System.Text.RegularExpressions.Regex.IsMatch(draft.PipelineName,@"\A[A-Za-z0-9_.-]+\z"))Error(null,"identity.pipelineName","engine_identity","Identificador não é compatível com Airflow; não será renomeado automaticamente");
  if(draft.Definition.Nodes.Count==0)Error(null,"nodes","empty_flow","Adicione pelo menos uma etapa antes de publicar");
  var names=draft.Definition.Nodes.Select(n=>n.Id).ToArray();if(names.Select(n=>n.ToUpperInvariant()).Distinct().Count()!=names.Length)Error(null,"nodes","duplicate_node","Identificadores de etapas devem ser distintos também por maiúsculas/minúsculas");
  foreach(var node in draft.Definition.Nodes){if(!FlowNode.KnownTypes.Contains(node.Type))Error(node.Id,"type","unsupported_type","Tipo de etapa não suportado");if(!System.Text.RegularExpressions.Regex.IsMatch(node.Id,@"\A[A-Za-z0-9_.-]+\z"))Error(node.Id,"id","engine_identity","Identificador de etapa incompatível com Airflow");if(!node.Configuration.TryGetProperty("legacyJob",out var job)||job.ValueKind!=JsonValueKind.Object)Error(node.Id,"configuration","missing_projection","Configuração de etapa não possui projeção legada");}
  var remaining=names.ToHashSet(StringComparer.Ordinal);while(remaining.Count>0){var free=remaining.Where(id=>!draft.Definition.Edges.Any(e=>e.Target==id&&remaining.Contains(e.Source))).ToArray();if(free.Length==0){Error(null,"edges","cycle","Dependências contêm ciclo");break;}remaining.ExceptWith(free);}
  return new(draft.Revision,errors.Count==0,errors);
 }
}
