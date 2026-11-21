using System.Text.RegularExpressions;
using Newtonsoft.Json.Linq;
using Xunit;

namespace ContosoHolidays.Tests;

/// <summary>
/// The OpenAPI definition and API properties checked against what Learn requires (OpenAPI 2.0, under 1 MB) and
/// recommends (custom connector coding standards, OpenAPI extensions), and against what the script really returns.
/// </summary>
public class DefinitionTests
{
    private static readonly JObject Swagger = Files.Swagger();

    private static IEnumerable<(string Path, string Method, JObject Op)> Operations() =>
        ((JObject)Swagger["paths"]!).Properties().SelectMany(p => ((JObject)p.Value).Properties().Select(m => (p.Name, m.Name, (JObject)m.Value)));

    [Fact]
    public void It_is_a_valid_OpenAPI_2_0_document()
    {
        var doc = Files.OpenApi(out var diagnostic);

        Assert.Empty(diagnostic.Errors);
        Assert.Equal(Microsoft.OpenApi.OpenApiSpecVersion.OpenApi2_0, diagnostic.SpecificationVersion);
        Assert.Equal(3, doc.Paths.Count);
    }

    [Fact]
    public void Definition_and_script_are_under_the_1_MB_limits()
    {
        Assert.True(new FileInfo(Files.Connector("apiDefinition.swagger.json")).Length < 1024 * 1024);
        Assert.True(new FileInfo(Files.Connector("script.csx.txt")).Length < 1024 * 1024);
    }

    [Fact]
    public void Https_only_and_no_authentication_because_the_source_is_public()
    {
        Assert.Equal(new[] { "https" }, Swagger["schemes"]!.Select(s => (string)s!));
        Assert.Equal("date.nager.at", (string)Swagger["host"]!);
        Assert.Empty((JObject)Swagger["securityDefinitions"]!);
        Assert.Empty((JObject)Files.ApiProperties()["properties"]!["connectionParameters"]!); // pac connector init --connection-template NoAuth
    }

    [Fact]
    public void Operation_ids_are_PascalCase_and_unique()
    {
        var ids = Operations().Select(o => (string)o.Op["operationId"]!).ToList();
        Assert.All(ids, id => Assert.Matches("^[A-Z][a-zA-Z0-9]+$", id));
        Assert.Equal(ids.Count, ids.Distinct().Count());
    }

    [Fact]
    public void Every_operation_has_a_summary_and_a_different_description_ending_with_a_period()
    {
        Assert.All(Operations(), o =>
        {
            var summary = (string)o.Op["summary"]!;
            var description = (string)o.Op["description"]!;
            Assert.False(string.IsNullOrWhiteSpace(summary));
            Assert.NotEqual(summary, description);
            Assert.EndsWith(".", description);
            Assert.Matches("^[A-Z][a-z]+( [a-z]+)*$", summary); // sentence case, e.g. "Get days off"
        });
    }

    [Fact]
    public void Every_operation_defines_a_200_response_with_a_schema()
    {
        Assert.All(Operations(), o => Assert.NotNull(o.Op["responses"]!["200"]!["schema"]));
    }

    [Fact]
    public void Every_parameter_has_a_title_and_a_hint()
    {
        Assert.All(Operations().SelectMany(o => o.Op["parameters"]!.Cast<JObject>()), p =>
        {
            Assert.False(string.IsNullOrWhiteSpace((string?)p["x-ms-summary"]), (string)p["name"]!);
            Assert.EndsWith(".", (string)p["description"]!);
        });
    }

    [Fact]
    public void Visibility_values_are_valid_and_internal_required_parameters_have_defaults()
    {
        var all = Swagger.Descendants().OfType<JProperty>().Where(p => p.Name == "x-ms-visibility").ToList();
        Assert.NotEmpty(all);
        Assert.All(all, p => Assert.Contains((string)p.Value!, new[] { "important", "advanced", "internal" }));

        // Learn: "For parameters that are internal and required, you must provide default values."
        var internalRequired = Operations().SelectMany(o => o.Op["parameters"]!.Cast<JObject>())
            .Where(p => (string?)p["x-ms-visibility"] == "internal" && (bool?)p["required"] == true);
        Assert.All(internalRequired, p => Assert.NotNull(p["default"]));
    }

    [Fact]
    public void Script_operations_exist_in_the_definition()
    {
        var ids = Operations().Select(o => (string)o.Op["operationId"]!).ToHashSet();
        var scriptOps = Files.ApiProperties()["properties"]!["scriptOperations"]!.Select(t => (string)t!).ToList();

        Assert.Equal(new[] { "GetDaysOff" }, scriptOps); // the passthrough operations don't pay for the script
        Assert.All(scriptOps, id => Assert.Contains(id, ids));
    }

    [Fact]
    public void The_country_drop_down_points_at_an_operation_that_returns_an_array_of_code_and_name()
    {
        var country = Operations().Single(o => (string)o.Op["operationId"]! == "GetDaysOff").Op["parameters"]!.Cast<JObject>().Single(p => (string)p["name"]! == "CountryCode");
        var dyn = (JObject)country["x-ms-dynamic-values"]!;
        var source = Operations().Single(o => (string)o.Op["operationId"]! == (string)dyn["operationId"]!).Op;

        // Learn: "If value-collection isn't specified, the response is evaluated as an array."
        Assert.Null(dyn["value-collection"]);
        Assert.Equal("array", (string)source["responses"]!["200"]!["schema"]!["type"]!);
        var item = Resolve((JObject)source["responses"]!["200"]!["schema"]!["items"]!);
        Assert.NotNull(item["properties"]![(string)dyn["value-path"]!]);
        Assert.NotNull(item["properties"]![(string)dyn["value-title"]!]);
        Assert.Equal("internal", (string)source["x-ms-visibility"]!); // a helper for the drop-down, not an action for makers
    }

    [Fact]
    public void The_recorded_source_matches_the_PublicHoliday_and_Country_schemas()
    {
        AssertMatches(Resolve(JObject.Parse("""{"$ref":"#/definitions/PublicHoliday"}""")), FakeHolidaySource.Holidays("PublicHolidays-2026-PT.json").First(), allowExtra: true);
        AssertMatches(Resolve(JObject.Parse("""{"$ref":"#/definitions/Country"}""")), (JObject)JArray.Parse(File.ReadAllText(Files.Fixture("AvailableCountries.json")))[0], allowExtra: false);
    }

    [Fact]
    public async Task What_the_script_returns_is_exactly_what_the_DaysOff_schema_declares()
    {
        var (_, body) = await ScriptRunner.DaysOff(new FakeHolidaySource(), "fromYear=2026&subdivision=PT-30");
        var schema = Resolve((JObject)Operations().Single(o => (string)o.Op["operationId"]! == "GetDaysOff").Op["responses"]!["200"]!["schema"]!);

        AssertMatches(schema, body!, allowExtra: false);
    }

    private static JObject Resolve(JObject schema) =>
        schema["$ref"] is { } r ? (JObject)Swagger["definitions"]![((string)r!).Split('/').Last()]! : schema;

    /// <summary>Every field in the JSON is declared with a matching type (and, unless allowExtra, nothing undeclared).</summary>
    private static void AssertMatches(JObject schema, JObject value, bool allowExtra)
    {
        var props = (JObject)schema["properties"]!;
        foreach (var field in value.Properties())
        {
            if (props[field.Name] is not JObject p) { Assert.True(allowExtra, $"'{field.Name}' is returned but not declared"); continue; }
            p = Resolve(p);
            var type = (string)p["type"]!;
            switch (field.Value.Type)
            {
                case JTokenType.Null: break;
                case JTokenType.String:
                    Assert.Equal("string", type);
                    if ((string?)p["format"] == "date") Assert.Matches(new Regex(@"^\d{4}-\d{2}-\d{2}$"), (string)field.Value!);
                    break;
                case JTokenType.Integer: Assert.Equal("integer", type); break;
                case JTokenType.Boolean: Assert.Equal("boolean", type); break;
                case JTokenType.Array:
                    Assert.Equal("array", type);
                    var items = Resolve((JObject)p["items"]!);
                    foreach (var element in field.Value)
                        if (element is JObject o) AssertMatches(items, o, allowExtra); else Assert.Equal("string", (string)items["type"]!);
                    break;
                case JTokenType.Object: AssertMatches(p, (JObject)field.Value, allowExtra); break;
                default: Assert.Fail($"unexpected {field.Value.Type} in '{field.Name}'"); break;
            }
        }
    }
}
