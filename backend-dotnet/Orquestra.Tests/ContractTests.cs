using System.Text.Json;
using Orquestra.Domain.Flows;
using Xunit;

namespace Orquestra.Tests;

public sealed class ContractTests
{
    private static readonly JsonSerializerOptions Options = new(JsonSerializerDefaults.Web);

    [Fact]
    public void EveryLegacyTypeIsRepresentedAndUnknownNodesAreReadOnly()
    {
        foreach (var type in FlowNode.KnownTypes.Append("future_node"))
        {
            var json = $$$"""{"schemaVersion":1,"identity":{"pipelineName":"MiXeD_á"},"metadata":{},"schedule":{},"parameters":[],"nodes":[{"id":"Etapa_Única","type":"{{{type}}}","configuration":{"legacy":null},"unknownField":{"keep":true}}],"edges":[],"futureField":"preservar"}""";
            var definition = JsonSerializer.Deserialize<PipelineDefinition>(json, Options)!;
            Assert.Equal(type == "future_node", definition.IsReadOnly);
            var again = JsonDocument.Parse(JsonSerializer.Serialize(definition, Options));
            Assert.Equal("preservar", again.RootElement.GetProperty("futureField").GetString());
            Assert.True(again.RootElement.GetProperty("nodes")[0].GetProperty("unknownField").GetProperty("keep").GetBoolean());
            Assert.Equal("MiXeD_á", definition.Identity.PipelineName);
        }
    }

    [Theory]
    [InlineData("sql.json")][InlineData("python.json")][InlineData("datastage.json")]
    public void SyntheticFixtureRoundTripsWithoutLosingNullsOrLegacyFields(string file)
    {
        var original = JsonNode(file);
        var definition = JsonSerializer.Deserialize<PipelineDefinition>(original.GetRawText(), Options)!;
        var serialized = System.Text.Json.Nodes.JsonNode.Parse(JsonSerializer.Serialize(definition, Options));
        Assert.True(System.Text.Json.Nodes.JsonNode.DeepEquals(System.Text.Json.Nodes.JsonNode.Parse(original.GetRawText()), serialized));
        Assert.False(definition.IsReadOnly);
    }

    [Fact]
    public void FutureSchemaIsReadOnlyAndLayoutIsSeparate()
    {
        var definition = JsonSerializer.Deserialize<PipelineDefinition>(JsonNode("sql.json"), Options)!;
        Assert.True((definition with { SchemaVersion = 2 }).IsReadOnly);
        Assert.DoesNotContain("layout", JsonSerializer.Serialize(definition, Options));
        Assert.Equal(200, new string('á', 200).Length); // .NET mede UTF-16 como nvarchar.
        Assert.Equal(200, string.Concat(Enumerable.Repeat("😀", 100)).Length);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void OptionalFieldsRetainOmissionAndExplicitNull(bool explicitNull)
    {
        var optionalIdentity = explicitNull ? ",\"displayName\":null" : "";
        var optionalDefinition = explicitNull ? ",\"metadata\":null,\"schedule\":null,\"parameters\":null" : "";
        var optionalEdge = explicitNull ? ",\"branch\":null" : "";
        var json = "{\"schemaVersion\":1,\"identity\":{\"pipelineName\":\"A%2FB_😀\",\"futureIdentity\":null" + optionalIdentity + "}" + optionalDefinition + ",\"nodes\":[],\"edges\":[{\"source\":\"A\",\"target\":\"B\",\"condition\":{\"value\":null}" + optionalEdge + "}]}";
        var definition = JsonSerializer.Deserialize<PipelineDefinition>(json, Options)!;
        Assert.True(System.Text.Json.Nodes.JsonNode.DeepEquals(
            System.Text.Json.Nodes.JsonNode.Parse(json),
            System.Text.Json.Nodes.JsonNode.Parse(JsonSerializer.Serialize(definition, Options))));
        Assert.Equal("A%2FB_😀", definition.Identity.PipelineName);
    }

    [Fact]
    public void LayoutPreservesUnknownFieldsAtBothLevels()
    {
        const string json = """{"schemaVersion":1,"nodes":{"Etapa_😀":{"x":-1.5,"y":20,"futurePosition":{"zoom":null}}},"futureLayout":[1,null]}""";
        var layout = JsonSerializer.Deserialize<FlowLayout>(json, Options)!;
        Assert.True(System.Text.Json.Nodes.JsonNode.DeepEquals(
            System.Text.Json.Nodes.JsonNode.Parse(json),
            System.Text.Json.Nodes.JsonNode.Parse(JsonSerializer.Serialize(layout, Options))));
    }

    private static JsonElement JsonNode(string file) => JsonDocument.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Fixtures", file))).RootElement.Clone();
}
