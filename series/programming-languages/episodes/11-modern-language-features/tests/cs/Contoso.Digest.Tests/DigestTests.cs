using System.Text.Json;
using Contoso.Digest;

namespace Contoso.Digest.Tests;

public class DigestTests
{
    private static RawRequest Raw(string code = "PR-1", decimal budget = 1000m, string department = "IT") =>
        new(code, "t", department, budget, "alex.demo@contoso.com");

    private static string Sample => File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "samples", "requests.json"));

    [Theory]
    [InlineData(1, Route.TeamLead)]
    [InlineData(4_999_999, Route.TeamLead)]
    [InlineData(5_000_000, Route.Finance)]
    [InlineData(24_999_999, Route.Finance)]
    [InlineData(25_000_000, Route.Board)]
    public void Route_boundaries_are_inclusive(long cents, Route expected) =>
        Assert.Equal(expected, DigestBuilder.RouteFor(cents));

    [Fact]
    public void Decimal_budgets_convert_to_exact_cents()
    {
        Assert.Equal(4_999_999, DigestBuilder.ToCents(49999.99m));
        Assert.Equal(5_000_001, DigestBuilder.ToCents(50000.01m));
        Assert.Equal(29, DigestBuilder.ToCents(0.29m));
    }

    [Fact]
    public void Zero_and_negative_budgets_are_rejected_with_the_shared_message()
    {
        var result = DigestBuilder.Build([Raw("PR-9", 0m), Raw("PR-8", -5m), Raw("PR-7", 10m)]);
        Assert.Equal(["PR-9", "PR-8"], result.Rejected.Select(r => r.Code));
        Assert.All(result.Rejected, r => Assert.Equal("budget must be greater than zero", r.Reason));
        Assert.Single(result.Accepted);
    }

    [Fact]
    public void Department_is_trimmed_and_upper_cased() =>
        Assert.Equal("HR", DigestBuilder.Build([Raw(department: " hr ")]).Accepted[0].Department);

    [Fact]
    public void Routes_always_list_all_three_routes_even_when_empty()
    {
        var result = DigestBuilder.Build([Raw(budget: 10m)]);
        Assert.Equal(3, result.Routes.Count);
        Assert.Equal(0, result.Routes[Route.Board]);
    }

    [Fact]
    public void Batches_chunk_in_order_and_the_last_one_is_short()
    {
        var raws = Enumerable.Range(1, 9).Select(i => Raw($"PR-{i}")).ToList();
        var batches = DigestBuilder.Build(raws).Batches;
        Assert.Equal([4, 4, 1], batches.Select(b => b.Length));
        Assert.Equal(["PR-1", "PR-2", "PR-3", "PR-4"], batches[0]);
    }

    [Fact]
    public void Money_formats_with_invariant_culture() =>
        Assert.Equal("1,320,370.75", DigestBuilder.Money(132_037_075));

    [Fact]
    public void Sample_digest_matches_the_shared_golden_file()
    {
        var expected = File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "expected", "digest.txt"))
            .ReplaceLineEndings("\n");
        var actual = DigestBuilder.Render(DigestBuilder.Build(DigestBuilder.Parse(Sample)));
        Assert.Equal(expected, actual);
    }

    [Fact]
    public void Parse_refuses_a_missing_required_property()
    {
        var json = """[{ "code": "PR-1", "title": "t", "department": "IT", "requestedBy": "a@contoso.com" }]""";
        Assert.Throws<JsonException>(() => DigestBuilder.Parse(json));
    }

    [Fact]
    public void Parse_refuses_a_null_for_a_non_nullable_string()
    {
        var json = """[{ "code": null, "title": "t", "department": "IT", "budget": 1, "requestedBy": "a@contoso.com" }]""";
        Assert.Throws<JsonException>(() => DigestBuilder.Parse(json));
    }

    [Fact]
    public void Parse_refuses_duplicate_properties()
    {
        var json = """[{ "code": "A", "code": "B", "title": "t", "department": "IT", "budget": 1, "requestedBy": "a@contoso.com" }]""";
        Assert.Throws<JsonException>(() => DigestBuilder.Parse(json));
    }

    [Fact]
    public void Parse_reads_camel_case_names_and_exact_decimals()
    {
        var raws = DigestBuilder.Parse(Sample);
        Assert.Equal(13, raws.Count);
        Assert.Equal(49999.99m, raws[1].Budget);
    }
}
