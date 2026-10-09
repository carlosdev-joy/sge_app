using System.Net.Http.Json;
using System.Text.Json;
using Orquestra.Application.Drafts;
internal sealed class LegacyPublicationValidationClient(IHttpClientFactory factory)
{
 public async Task<PublicationValidation> ValidateAsync(Guid id,long revision,string authorization,CancellationToken ct)
 {
  using var client=factory.CreateClient("workspace-read");using var request=new HttpRequestMessage(HttpMethod.Post,$"workspace-adapter/validate/{id}"){Content=JsonContent.Create(new{expectedRevision=revision})};request.Headers.TryAddWithoutValidation("Authorization",authorization);
  using var deadline=CancellationTokenSource.CreateLinkedTokenSource(ct);deadline.CancelAfter(TimeSpan.FromSeconds(5));
  try{using var response=await client.SendAsync(request,HttpCompletionOption.ResponseHeadersRead,deadline.Token);if(!response.IsSuccessStatusCode)throw new WorkspaceException((int)response.StatusCode is 401 or 403 or 409?(int)response.StatusCode:503,"validation_unavailable","Validação do adaptador indisponível");if(response.Content.Headers.ContentLength>1024*1024)throw new WorkspaceException(503,"validation_unavailable","Validação excedeu limite");await using var stream=await response.Content.ReadAsStreamAsync(deadline.Token);await using var buffer=new MemoryStream();var block=new byte[8192];int size;while((size=await stream.ReadAsync(block,deadline.Token))>0){if(buffer.Length+size>1024*1024)throw new WorkspaceException(503,"validation_unavailable","Validação excedeu limite");await buffer.WriteAsync(block.AsMemory(0,size),deadline.Token);}var result=JsonSerializer.Deserialize<PublicationValidation>(buffer.GetBuffer().AsSpan(0,(int)buffer.Length),new JsonSerializerOptions(JsonSerializerDefaults.Web));return result??throw new WorkspaceException(503,"validation_unavailable","Validação indisponível");}catch(JsonException){throw new WorkspaceException(503,"validation_unavailable","Resposta de validação inválida");}catch(HttpRequestException){throw new WorkspaceException(503,"validation_unavailable","Dependência de validação indisponível");}catch(OperationCanceledException)when(!ct.IsCancellationRequested){throw new WorkspaceException(503,"validation_unavailable","Validação indisponível");}
 }
}
