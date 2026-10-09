using System.Text.Json;
using Orquestra.Application.Drafts;

// Leitura somente após RBAC do grupo workspace. Sem caminho/comando escolhido pelo cliente.
internal sealed class PublishedExecutionClient(IHttpClientFactory factory)
{
 public async Task<JsonElement> ReadAsync(string name, string? date, string authorization, CancellationToken ct)
 {
  DraftValidation.Name(name);
  if (date is not null && !DateOnly.TryParseExact(date,"yyyy-MM-dd",out _)) DraftValidation.Invalid("Data operacional inválida");
  using var deadline=CancellationTokenSource.CreateLinkedTokenSource(ct);deadline.CancelAfter(TimeSpan.FromSeconds(5));
  try
  {
   using var client=factory.CreateClient("workspace-read");
   using var request=new HttpRequestMessage(HttpMethod.Get,"pipeline-execution?pipeline_name="+Uri.EscapeDataString(name)+(date is null?"":"&data_referencia="+Uri.EscapeDataString(date)));
   request.Headers.TryAddWithoutValidation("Authorization",authorization);
   using var response=await client.SendAsync(request,HttpCompletionOption.ResponseHeadersRead,deadline.Token);
   if (!response.IsSuccessStatusCode) throw new WorkspaceException((int)response.StatusCode is 401 or 403 ? (int)response.StatusCode : 503,"execution_unavailable","Consulta de execução indisponível");
   const int limit=2*1024*1024;
   if(response.Content.Headers.ContentLength>limit) throw new WorkspaceException(503,"execution_unavailable","Consulta de execução excede o limite");
   await using var stream=await response.Content.ReadAsStreamAsync(deadline.Token);await using var buffer=new MemoryStream();var block=new byte[8192];int size;
   while((size=await stream.ReadAsync(block,deadline.Token))>0){if(buffer.Length+size>limit)throw new WorkspaceException(503,"execution_unavailable","Consulta de execução excede o limite");await buffer.WriteAsync(block.AsMemory(0,size),deadline.Token);}
   using var json=JsonDocument.Parse(buffer.GetBuffer().AsMemory(0,(int)buffer.Length));return json.RootElement.Clone();
  }
  catch(OperationCanceledException) when(!ct.IsCancellationRequested){throw new WorkspaceException(503,"execution_unavailable","Consulta de execução indisponível");}
  catch(HttpRequestException){throw new WorkspaceException(503,"execution_unavailable","Consulta de execução indisponível");}
  catch(JsonException){throw new WorkspaceException(503,"execution_unavailable","Consulta de execução indisponível");}
 }
}
