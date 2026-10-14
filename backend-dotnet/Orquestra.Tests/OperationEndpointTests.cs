using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
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
    const string Version="0f8fad5b-d9cb-469f-a165-70867728950e";
    static readonly string Hash=new string('a',32)+new string('F',32);
    // Par completo segue ao adaptador no topo do corpo, com os valores recebidos, fora de conf; conf não muda.
    [Fact]
    public async Task CompleteExpectedPairIsForwardedOutsideConf()
    {
        using var app=new OperationApp("tela_pipelines,tela_jobs,tela_logs,acao_executar");app.Handler.Body="{\"dag_run_id\":\"manual\",\"state\":\"queued\"}";
        using var client=app.CreateClient();client.DefaultRequestHeaders.Add("Authorization","Bearer synthetic");
        var response=await client.PostAsJsonAsync("/workspace/runs?name=test",new{conf=new{mode="full"},dag_run_id="manual",expected_version_id=Version,expected_content_hash=Hash});
        Assert.Equal(202,(int)response.StatusCode);Assert.Equal(1,app.Handler.Calls);
        using var forwarded=JsonDocument.Parse(Assert.Single(app.Forwarded)!);var root=forwarded.RootElement;
        Assert.Equal(new[]{"conf","dag_run_id","expected_version_id","expected_content_hash"},root.EnumerateObject().Select(p=>p.Name));
        Assert.Equal(Version,root.GetProperty("expected_version_id").GetString());Assert.Equal(Hash,root.GetProperty("expected_content_hash").GetString());
        Assert.Equal("{\"mode\":\"full\"}",root.GetProperty("conf").GetRawText());
    }
    // Par dentro de conf não é o par conferido: não é validado aqui nem promovido ao topo do corpo encaminhado.
    [Fact]
    public async Task PairInsideConfIsNotPromotedToExpectedPublication()
    {
        using var app=new OperationApp("tela_pipelines,tela_jobs,tela_logs,acao_executar");app.Handler.Body="{\"dag_run_id\":\"manual\",\"state\":\"queued\"}";
        using var client=app.CreateClient();client.DefaultRequestHeaders.Add("Authorization","Bearer synthetic");
        var response=await client.PostAsJsonAsync("/workspace/runs?name=test",new{conf=new{expected_version_id=Version,expected_content_hash=Hash},dag_run_id="manual"});
        Assert.Equal(202,(int)response.StatusCode);Assert.Equal(1,app.Handler.Calls);
        using var forwarded=JsonDocument.Parse(Assert.Single(app.Forwarded)!);
        Assert.False(forwarded.RootElement.TryGetProperty("expected_version_id",out _));Assert.False(forwarded.RootElement.TryGetProperty("expected_content_hash",out _));
    }
    // Par incompleto ou malformado, ou nome repetido: 422 sem nenhum envio ao adaptador.
    [Theory]
    [InlineData("{\"expected_version_id\":\"$V\"}")]
    [InlineData("{\"expected_content_hash\":\"$H\"}")]
    [InlineData("{\"conf\":{},\"expected_version_id\":\"$V\",\"expected_content_hash\":null}")]
    [InlineData("{\"expected_version_id\":null,\"expected_content_hash\":\"$H\"}")]
    [InlineData("{\"expected_version_id\":null,\"expected_content_hash\":null}")]
    [InlineData("{\"expected_version_id\":\"{$V}\",\"expected_content_hash\":\"$H\"}")]
    [InlineData("{\"expected_version_id\":\"0f8fad5bd9cb469fa16570867728950e\",\"expected_content_hash\":\"$H\"}")]
    [InlineData("{\"expected_version_id\":\"0f8fad5bd-9cb-469f-a165-70867728950e\",\"expected_content_hash\":\"$H\"}")]
    [InlineData("{\"expected_version_id\":123,\"expected_content_hash\":\"$H\"}")]
    [InlineData("{\"expected_version_id\":\"$V\",\"expected_content_hash\":\"$H0\"}")]
    [InlineData("{\"expected_version_id\":\"$V\",\"expected_content_hash\":\"g$H\"}")]
    [InlineData("{\"expected_version_id\":\"$V\",\"expected_content_hash\":\"$S\"}")]
    [InlineData("{\"expected_version_id\":\"$V\",\"expected_content_hash\":\"$G\"}")]
    [InlineData("{\"expected_version_id\":\"$V\",\"expected_content_hash\":[\"$H\"]}")]
    [InlineData("{\"expected_version_id\":\"$V\",\"expected_version_id\":\"$V\",\"expected_content_hash\":\"$H\"}")]
    public async Task IncompleteOrMalformedPairNeverDispatches(string template)
    {
        using var app=new OperationApp("tela_pipelines,tela_jobs,tela_logs,acao_executar");using var client=app.CreateClient();client.DefaultRequestHeaders.Add("Authorization","Bearer synthetic");
        // $H0: 65 caracteres; g$H: 65 com prefixo; $S: 63; $G: 64 com um não hexadecimal.
        var body=template.Replace("$V",Version).Replace("$H",Hash).Replace("$S",Hash[1..]).Replace("$G","g"+Hash[1..]);
        var response=await client.PostAsync("/workspace/runs?name=test",new StringContent(body,Encoding.UTF8,"application/json"));
        Assert.Equal(422,(int)response.StatusCode);Assert.Equal(0,app.Handler.Calls);Assert.Empty(app.Forwarded);
    }
}
internal sealed class OperationApp(string permissions,bool operations=true,string users="") : ExecutionApp(permissions)
{
    // Corpos exatamente como o endpoint os encaminha ao adaptador.
    public List<string?> Forwarded { get; } = new();
    protected override void ConfigureWebHost(IWebHostBuilder b)
    {
        base.ConfigureWebHost(b);
        b.ConfigureAppConfiguration((_,c)=>c.AddInMemoryCollection(new Dictionary<string,string?> { ["Workspace:OperationsEnabled"] = operations.ToString(), ["Workspace:NavigationPilotUsers"] = users }));
        // Envolve a fábrica já registrada (inclusive a do ExecutionApp), sem trocar o handler sintético.
        b.ConfigureTestServices(s=>{var registered=s.Last(d=>d.ServiceType==typeof(IHttpClientFactory));s.AddSingleton<IHttpClientFactory>(sp=>new ForwardCaptureFactory((IHttpClientFactory)(registered.ImplementationInstance??registered.ImplementationFactory?.Invoke(sp)??ActivatorUtilities.CreateInstance(sp,registered.ImplementationType!)),Forwarded));});
    }
}
// Relé de teste: guarda o corpo encaminhado e repassa uma cópia ao cliente original, cujo handler
// sintético continua contando chamadas, registrando a URI e devolvendo a resposta configurada.
internal sealed class ForwardCaptureFactory(IHttpClientFactory inner,List<string?> bodies) : IHttpClientFactory
{
    public HttpClient CreateClient(string name){var client=inner.CreateClient(name);return new HttpClient(new Relay(client,bodies)){BaseAddress=client.BaseAddress,Timeout=client.Timeout};}
    private sealed class Relay(HttpClient client,List<string?> bodies) : HttpMessageHandler
    {
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken ct)
        {
            var text=request.Content is null?null:await request.Content.ReadAsStringAsync(ct);bodies.Add(text);
            var copy=new HttpRequestMessage(request.Method,request.RequestUri);
            foreach(var header in request.Headers)copy.Headers.TryAddWithoutValidation(header.Key,header.Value);
            if(text is not null)copy.Content=new StringContent(text,Encoding.UTF8,"application/json");
            return await client.SendAsync(copy,HttpCompletionOption.ResponseHeadersRead,ct);
        }
    }
}
