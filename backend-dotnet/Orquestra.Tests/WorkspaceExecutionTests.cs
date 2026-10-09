using System.Net;
using System.Net.Http.Json;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Orquestra.Application.Security;
using Xunit;
namespace Orquestra.Tests;
public sealed class WorkspaceExecutionTests
{
 [Theory]
 [InlineData("tela_pipelines,tela_jobs",403)]
 [InlineData("tela_pipelines,tela_logs",403)]
 [InlineData("tela_jobs,tela_logs",403)]
 [InlineData("tela_pipelines,tela_jobs,tela_logs",200)]
 public async Task ExecutionRequiresAllThreeReadPermissions(string permissions,int status)
 {
  using var app=new ExecutionApp(permissions);using var client=app.CreateClient();client.DefaultRequestHeaders.Add("Authorization","Bearer synthetic");
  Assert.Equal(status,(int)(await client.GetAsync("/workspace/executions?name=A%2FB%25%C3%A7&date=2026-10-09")).StatusCode);
  Assert.Equal(status==200?1:0,app.Handler.Calls);
  if(status==200){Assert.Equal(HttpMethod.Get,app.Handler.Method);Assert.Equal("/pipeline-execution?pipeline_name=A%2FB%25%C3%A7&data_referencia=2026-10-09",app.Handler.Uri!.PathAndQuery);}
 }
 [Theory]
 [InlineData(401,401)] [InlineData(403,403)] [InlineData(500,503)]
 public async Task UpstreamErrorsAreSanitized(int upstream,int expected)
 {
  using var app=new ExecutionApp("tela_pipelines,tela_jobs,tela_logs");app.Handler.Status=upstream;using var client=app.CreateClient();client.DefaultRequestHeaders.Add("Authorization","Bearer synthetic");
  var response=await client.GetAsync("/workspace/executions?name=teste");Assert.Equal(expected,(int)response.StatusCode);Assert.DoesNotContain("synthetic-private-upstream",await response.Content.ReadAsStringAsync());
 }
 [Theory] [InlineData("2026-99-20")] [InlineData("hoje")]
 public async Task InvalidDateNeverCallsUpstream(string date)
 {
  using var app=new ExecutionApp("tela_pipelines,tela_jobs,tela_logs");using var client=app.CreateClient();client.DefaultRequestHeaders.Add("Authorization","Bearer synthetic");
  Assert.Equal(422,(int)(await client.GetAsync("/workspace/executions?name=teste&date="+date)).StatusCode);Assert.Equal(0,app.Handler.Calls);
 }
 [Fact]
 public async Task InvalidOrOversizedResponseDegradesWithoutExposingPayload()
 {
  foreach(var body in new[]{"synthetic-private-upstream",new string('x',2*1024*1024+1)}){
   using var app=new ExecutionApp("tela_pipelines,tela_jobs,tela_logs");app.Handler.Body=body;using var client=app.CreateClient();client.DefaultRequestHeaders.Add("Authorization","Bearer synthetic");
   var response=await client.GetAsync("/workspace/executions?name=teste");Assert.Equal(503,(int)response.StatusCode);Assert.DoesNotContain("synthetic-private-upstream",await response.Content.ReadAsStringAsync());
  }
 }
}
internal class ExecutionApp(string permissions):WebApplicationFactory<Program>
{
 public ExecutionHandler Handler {get;}=new();
 protected override void ConfigureWebHost(IWebHostBuilder b){b.ConfigureAppConfiguration((_,c)=>c.AddInMemoryCollection(new Dictionary<string,string?>{["Workspace:Enabled"]="true",["Workspace:LegacyApiBaseUrl"]="http://localhost/"}));b.ConfigureServices(s=>{s.RemoveAll<ISessionRepository>();s.AddSingleton<ISessionRepository>(new FakeSessions{Principal=SecurityTests.Principal(permissions.Split(','))});s.AddHttpClient("workspace-read",c=>c.BaseAddress=new Uri("http://localhost/")).ConfigurePrimaryHttpMessageHandler(()=>Handler);});}
}
internal sealed class ExecutionHandler:HttpMessageHandler
{
 public int Calls;public int Status=200;public string Body="{}";public Uri? Uri;public HttpMethod? Method;
 protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage r,CancellationToken ct){Calls++;Uri=r.RequestUri;Method=r.Method;return Task.FromResult(new HttpResponseMessage((HttpStatusCode)Status){Content=new StringContent(Status==200?Body:"synthetic-private-upstream")});}
}
