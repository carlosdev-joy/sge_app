using System.Text.Json;
using Orquestra.Application.Drafts;
using Orquestra.Domain.Flows;
using Xunit;

namespace Orquestra.Tests;
public sealed class DraftValidationTests
{
    [Theory]
    [InlineData("{\"password\":\"private-fixture\"}")]
    [InlineData("{\"nested\":[{\"Authorization\":\"short-secret\"}]}")]
    [InlineData("{\"future_json\":\"  {\\\"headers\\\":{\\\"Authorization\\\":\\\"short-secret\\\"}}\"}")]
    [InlineData("{\"param_type\":\"ENCRYPTED\",\"param_value\":\"cipher-fixture\"}")]
    [InlineData("{\"future\":\"gAAAAcipher-fixture\"}")]
    public void SecretsAreRejectedInDefinitionAndLayoutExtensions(string source)
    {
        var element = JsonDocument.Parse(source).RootElement;
        var definition = new PipelineDefinition { Identity = new("Teste"), Metadata = element };
        var layout = new FlowLayout(1,new Dictionary<string,NodePosition>());
        Assert.Equal(422, Assert.Throws<WorkspaceException>(() => DraftValidation.Validate(definition,layout)).StatusCode);
        definition = definition with { Metadata = default };
        layout = layout with { Extensions = element.EnumerateObject().ToDictionary(p=>p.Name,p=>p.Value.Clone()) };
        Assert.Equal(422, Assert.Throws<WorkspaceException>(() => DraftValidation.Validate(definition,layout)).StatusCode);
    }
    [Fact]
    public void PositionExtensionsAreScannedAndNullCollectionsFailWith422()
    {
        var definition = new PipelineDefinition { Identity = new("Teste"),Nodes=[new(){Id="Nó",Type="sql",Configuration=JsonDocument.Parse("{}").RootElement}] };
        var layout = new FlowLayout(1,new Dictionary<string,NodePosition>{["Nó"]=new(1,2){Extensions=new(){["password"]=JsonSerializer.SerializeToElement("fixture")}}});
        Assert.Throws<WorkspaceException>(()=>DraftValidation.Validate(definition,layout));
        Assert.Throws<WorkspaceException>(()=>DraftValidation.Validate(definition with {Nodes=null!},new(1,new Dictionary<string,NodePosition>())));
    }
    [Fact]
    public void ConnectionIdentifiersMaskedParametersAndUnknownFieldsRemainValid()
    {
        var definition = new PipelineDefinition { Identity = new("Teste Ω "),Metadata=JsonDocument.Parse("{\"ssh_conn_id\":\"conn-1\",\"params\":[{\"param_type\":\"encrypted\",\"param_value\":\"***\",\"secretReference\":{\"parameterName\":\"SECRET\"}}],\"future\":null}").RootElement };
        DraftValidation.Validate(definition,new(1,new Dictionary<string,NodePosition>()));
        Assert.Equal("Teste Ω ",definition.Identity.PipelineName);
    }
}
