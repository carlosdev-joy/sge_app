using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.AspNetCore.Hosting;
using Microsoft.Extensions.Configuration;
using Xunit;
namespace Orquestra.Tests;
public sealed class OperationEndpointTests
{
    [Theory]
    [InlineData("tela_pipelines,tela_jobs,tela_logs",403)]
    [InlineData("tela_pipelines,tela_jobs,acao_executar",403)]
    [InlineData("tela_pipelines,tela_logs,acao_executar",403)]
    [InlineData("tela_jobs,tela_logs,acao_executar",403)]
    [InlineData("tela_pipelines,tela_jobs,tela_logs,acao_executar",202)]
    public async Task ExecuteDoesNotRequireEditingButRequiresAllOperationalPermissions(string permissions, int status)
    {
        using var app = new OperationApp(permissions); app.Handler.Body = "{\"dag_run_id\":\"manual\",\"state\":\"queued\",\"conf\":{\"secret\":\"synthetic-private\"}}";
        using var client = app.CreateClient(); client.DefaultRequestHeaders.Add("Authorization", "Bearer synthetic");
        var response = await client.PostAsJsonAsync("/workspace/runs?name=A%2FB%25%C3%A7",new { conf = new { mode = "full" }, dag_run_id = "manual" });
        Assert.Equal(status,(int)response.StatusCode); Assert.Equal(status == 202 ? 1 : 0,app.Handler.Calls);
        Assert.DoesNotContain("synthetic-private",await response.Content.ReadAsStringAsync());
        if(status == 202) Assert.Equal("/pipeline-runs?pipeline_name=A%2FB%25%C3%A7", app.Handler.Uri!.PathAndQuery);
    }
    [Theory]
    [InlineData(false,"SYNTHETIC",false,false)]
    [InlineData(true,"",true,false)]
    [InlineData(true,"ANOTHER",true,false)]
    [InlineData(true,"synthetic",true,true)]
    public async Task OperationsFlagAndExplicitPilotListControlCapabilities(bool enabled,string users,bool execute,bool navigation)
    {
        using var app=new OperationApp("tela_pipelines,tela_jobs,tela_logs,acao_executar",enabled,users);using var client=app.CreateClient();client.DefaultRequestHeaders.Add("Authorization","Bearer synthetic");
        var response=await client.GetAsync("/workspace/capabilities");using var json=JsonDocument.Parse(await response.Content.ReadAsStringAsync());var actions=json.RootElement.GetProperty("actions");
        Assert.Equal(execute,actions.GetProperty("execute").GetBoolean());Assert.Equal(execute,actions.GetProperty("reprocess").GetBoolean());Assert.Equal(navigation,actions.GetProperty("contextualNavigation").GetBoolean());Assert.False(actions.GetProperty("cancel").GetBoolean());
    }
    [Fact]
    public async Task DisabledOperationsNeverDispatch()
    {
        using var app=new OperationApp("tela_pipelines,tela_jobs,tela_logs,acao_executar",false);using var client=app.CreateClient();client.DefaultRequestHeaders.Add("Authorization","Bearer synthetic");
        Assert.Equal(404,(int)(await client.PostAsJsonAsync("/workspace/runs?name=test",new{})).StatusCode);Assert.Equal(0,app.Handler.Calls);
    }
    [Fact]
    public async Task UnknownPayloadFieldNeverDispatches()
    {
        using var app=new OperationApp("tela_pipelines,tela_jobs,tela_logs,acao_executar");using var client=app.CreateClient();client.DefaultRequestHeaders.Add("Authorization","Bearer synthetic");
        Assert.Equal(422,(int)(await client.PostAsJsonAsync("/workspace/runs?name=test",new {url="http://external"})).StatusCode);Assert.Equal(0,app.Handler.Calls);
    }
    [Fact]
    public async Task ExecutionSelectionUsesEncodedRunIdInsteadOfAmbiguousDate()
    {
        using var app=new OperationApp("tela_pipelines,tela_jobs,tela_logs");using var client=app.CreateClient();client.DefaultRequestHeaders.Add("Authorization","Bearer synthetic");
        Assert.Equal(200,(int)(await client.GetAsync("/workspace/executions?name=A&date=2026-10-09&runId=manual__a%2Fb%25")).StatusCode);
        Assert.Equal("/pipeline-execution?pipeline_name=A&run_id=manual__a%2Fb%25",app.Handler.Uri!.PathAndQuery);
    }
}
internal sealed class OperationApp(string permissions,bool operations=true,string users="") : ExecutionApp(permissions)
{
    protected override void ConfigureWebHost(IWebHostBuilder b)
    {
        base.ConfigureWebHost(b);
        b.ConfigureAppConfiguration((_,c)=>c.AddInMemoryCollection(new Dictionary<string,string?> { ["Workspace:OperationsEnabled"] = operations.ToString(), ["Workspace:NavigationPilotUsers"] = users }));
    }
}
