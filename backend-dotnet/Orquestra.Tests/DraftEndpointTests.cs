using System.Net;
using System.Net.Http.Json;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Orquestra.Application.Drafts;
using Orquestra.Application.Security;
using Xunit;

namespace Orquestra.Tests;
public sealed class DraftEndpointTests
{
    [Theory]
    [InlineData(null,"tela_pipelines,tela_jobs,acao_editar",401)]
    [InlineData("Bearer synthetic","tela_jobs,acao_editar",403)]
    [InlineData("Bearer synthetic","tela_pipelines,acao_editar",403)]
    [InlineData("Bearer synthetic","tela_pipelines,tela_jobs",403)]
    [InlineData("Basic VVNFUjpzeW50aGV0aWM=","tela_pipelines,tela_jobs,acao_editar",401)]
    public async Task MutationsDenyMissingSessionAndPermissionsBeforeRepository(string? header,string permissions,int expected)
    {
        using var app = new DraftTestApp(permissions,true); using var client = app.CreateClient();
        if (header is not null) client.DefaultRequestHeaders.Add("Authorization",header);
        var response=await client.PostAsJsonAsync("/workspace/pipelines",new{});
        Assert.Equal(expected,(int)response.StatusCode); Assert.Equal(0,app.Repository.Calls);
    }
    [Fact]
    public async Task FlagSchemaAndBearerControlCapabilitiesWhilePublicationRemainsDisabled()
    {
        using var app=new DraftTestApp("tela_pipelines,tela_jobs,acao_editar,acao_admin",true); using var client=app.CreateClient();
        client.DefaultRequestHeaders.Add("Authorization","Bearer synthetic");
        var capabilities=await client.GetFromJsonAsync<System.Text.Json.JsonElement>("/workspace/capabilities");
        Assert.True(capabilities.GetProperty("actions").GetProperty("editDraft").GetBoolean()); Assert.False(capabilities.GetProperty("actions").GetProperty("publish").GetBoolean());
        app.Repository.Available=false;
        capabilities=await client.GetFromJsonAsync<System.Text.Json.JsonElement>("/workspace/capabilities"); Assert.False(capabilities.GetProperty("actions").GetProperty("editDraft").GetBoolean());
        Assert.Equal(HttpStatusCode.ServiceUnavailable,(await client.GetAsync("/workspace/health/ready")).StatusCode);
        client.DefaultRequestHeaders.Remove("Authorization"); client.DefaultRequestHeaders.Add("Authorization","Basic VVNFUjpzeW50aGV0aWM="); app.Repository.Available=true;
        capabilities=await client.GetFromJsonAsync<System.Text.Json.JsonElement>("/workspace/capabilities"); Assert.False(capabilities.GetProperty("actions").GetProperty("editDraft").GetBoolean());
    }
    [Fact]
    public async Task InvalidAndOversizedBodiesNeverReachPersistenceAndErrorsArePortuguese()
    {
        using var app=new DraftTestApp("tela_pipelines,tela_jobs,acao_editar",true); using var client=app.CreateClient();client.DefaultRequestHeaders.Add("Authorization","Bearer synthetic");
        foreach(var body in new[]{"{",new string('x',1024*1024+1)})
        {
            var response=await client.PostAsync("/workspace/pipelines",new StringContent(body,System.Text.Encoding.UTF8,"application/json"));
            Assert.Equal(422,(int)response.StatusCode);Assert.Contains("Corpo",await response.Content.ReadAsStringAsync());
        }
        Assert.Equal(0,app.Repository.Calls);
    }
    [Fact]
    public async Task DisabledDraftWritesReturnExplicit503AndDoNotAffectReads()
    {
        using var app=new DraftTestApp("tela_pipelines,tela_jobs,acao_editar",false);using var client=app.CreateClient();client.DefaultRequestHeaders.Add("Authorization","Bearer synthetic");
        Assert.Equal(HttpStatusCode.ServiceUnavailable,(await client.PostAsJsonAsync("/workspace/pipelines",new{})).StatusCode);
        Assert.Equal(HttpStatusCode.OK,(await client.GetAsync("/workspace/capabilities")).StatusCode);Assert.Equal(0,app.Repository.Calls);
    }
}
internal sealed class DraftTestApp(string permissions,bool enabled):WebApplicationFactory<Program>
{
    public StubDrafts Repository {get;}=new();
    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        builder.ConfigureAppConfiguration((_,c)=>c.AddInMemoryCollection(new Dictionary<string,string?>{["Workspace:Enabled"]="true",["Workspace:DraftsEnabled"]=enabled.ToString()}));
        builder.ConfigureServices(s=>{s.RemoveAll<ISessionRepository>();s.AddSingleton<ISessionRepository>(new FakeSessions{Principal=SecurityTests.Principal(permissions.Split(','))});s.RemoveAll<IBasicIdentityClient>();s.AddSingleton<IBasicIdentityClient>(new FakeBasic());s.RemoveAll<IDraftRepository>();s.AddSingleton<IDraftRepository>(Repository);});
    }
}
internal sealed class StubDrafts:IDraftRepository
{
    public bool Available {get;set;}=true;public int Calls {get;private set;}
    public Task<bool> SchemaAvailableAsync(CancellationToken ct)=>Task.FromResult(Available);
    private Task<T> Called<T>(){Calls++;throw new WorkspaceException(503,"synthetic","Bancada sintética");}
    public Task<PipelineContext> ContextAsync(string n,WorkspacePrincipal a,bool stages,CancellationToken ct)=>Called<PipelineContext>();
    public Task<Draft> GetAsync(Guid id,WorkspacePrincipal a,CancellationToken ct)=>Called<Draft>();
    public Task<Draft> CreateAsync(CreateDraft r,WorkspacePrincipal a,CancellationToken ct)=>Called<Draft>();
    public Task<Draft> ImportAsync(string n,WorkspacePrincipal a,CancellationToken ct)=>Called<Draft>();
    public Task<Draft> SaveAsync(Guid id,SaveDraft r,WorkspacePrincipal a,CancellationToken ct)=>Called<Draft>();
    public Task<LeaseInfo> LeaseAsync(Guid id,LeaseRequest r,WorkspacePrincipal a,CancellationToken ct)=>Called<LeaseInfo>();
    public Task ReleaseAsync(Guid id,RevisionFence r,WorkspacePrincipal a,CancellationToken ct)=>Called<bool>();
    public Task<LeaseInfo> TransferAsync(Guid id,RevisionFence r,WorkspacePrincipal a,CancellationToken ct)=>Called<LeaseInfo>();
    public Task DiscardAsync(Guid id,RevisionFence r,WorkspacePrincipal a,CancellationToken ct)=>Called<bool>();
}
