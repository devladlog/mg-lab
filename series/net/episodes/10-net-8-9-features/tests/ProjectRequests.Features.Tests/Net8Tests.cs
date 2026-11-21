using System.Runtime.InteropServices;
using System.Text.Json;

namespace ProjectRequests.Features.Tests;

public class Net8Tests
{
    [Fact]
    public void FrozenDictionary_looks_up_by_the_comparer_it_was_built_with()
    {
        Assert.Equal("Finance", Departments.ByCode["fin"].Name);
        Assert.True(Departments.ByCode.TryGetValue("It", out var it));
        Assert.Equal("Information Technology", it!.Name);
        Assert.False(Departments.ByCode.ContainsKey("HR"));
    }

    [Fact]
    public void FrozenDictionary_cannot_be_changed_after_it_is_created()
    {
        var asMutable = (IDictionary<string, Department>)Departments.ByCode;
        Assert.Throws<NotSupportedException>(() => asMutable.Add("HR", new Department("HR", "People")));
    }

    [Fact]
    public void Json_snake_case_and_generic_enum_converter()
    {
        var json = JsonSerializer.Serialize(new FeedItem { RequestId = 7, Title = "Backup storage", Priority = Priority.High }, Feed.SnakeCase);

        Assert.Equal("""{"request_id":7,"title":"Backup storage","priority":"High","tags":["imported"]}""", json);
        var back = JsonSerializer.Deserialize<FeedItem>(json, Feed.SnakeCase)!;
        Assert.Equal(7, back.RequestId);
        Assert.Equal(Priority.High, back.Priority);
    }

    [Fact]
    public void Read_only_collection_is_ignored_by_default_and_filled_when_populate_is_chosen()
    {
        const string input = """{"request_id":1,"tags":["urgent","finance"]}""";

        var ignored = JsonSerializer.Deserialize<FeedItem>(input, Feed.SnakeCase)!;
        var populated = JsonSerializer.Deserialize<FeedItem>(input, Feed.SnakeCasePopulate)!;

        Assert.Equal(["imported"], ignored.Tags);
        Assert.Equal(["imported", "urgent", "finance"], populated.Tags);   // populated into the existing list: it appends
    }

    [Theory]
    [InlineData("Audit tooling", true)]
    [InlineData("<script>alert(1)</script>", false)]
    [InlineData("R&D budget", false)]
    [InlineData("", true)]
    public void SearchValues_rejects_forbidden_characters(string title, bool clean) =>
        Assert.Equal(clean, SmallThings.IsCleanTitle(title));

    [Fact]
    public void CompositeFormat_formats_with_a_format_parsed_once()
    {
        Assert.Equal("Request 7 (76,000.00) was Approved", SmallThings.Describe(SampleData.Requests[6]));
    }

    [Fact]
    public void Random_GetItems_and_Shuffle_keep_to_the_pool()
    {
        var pool = SampleData.Requests.ToArray();

        var sample = SmallThings.Sample(pool, 20, new Random(1));          // more than the pool: items repeat
        Assert.Equal(20, sample.Length);
        Assert.All(sample, r => Assert.Contains(r, pool));

        var shuffled = pool.ToArray();
        SmallThings.ShuffleInPlace(shuffled, new Random(1));
        Assert.Equal(pool.OrderBy(r => r.Id), shuffled.OrderBy(r => r.Id));   // same items
        Assert.NotEqual(pool, shuffled);                                    // different order (seed 1: deterministic)
    }

    [Fact]
    public void The_GroupBy_versions_are_what_net9_CountBy_and_AggregateBy_replace()
    {
        var counts = LinqBefore.CountPerDepartment(SampleData.Requests);
        Assert.Equal(new Dictionary<string, int> { ["IT"] = 3, ["FIN"] = 3, ["OPS"] = 2 }, counts);
        Assert.Equal(101_500m, LinqBefore.BudgetPerDepartment(SampleData.Requests)["FIN"]);        // 58,000 + 12,500 + 31,000
    }

    [Fact]
    public void The_double_overload_of_TimeSpan_FromSeconds_is_one_tick_short_on_every_runtime()
    {
        // the reason .NET 9 added integer overloads (see Net9Tests): 101.832 s is not exactly representable as a double
        Assert.Equal(1_018_319_999L, TimeSpan.FromSeconds(101.832).Ticks);
    }

    [Fact]
    public void The_test_app_runs_on_the_runtime_the_library_was_compiled_for()
    {
        var framework = RuntimeInformation.FrameworkDescription;
        var expected = FeatureMatrix.CompiledFor switch
        {
            "net8.0" => ".NET 8.",
            "net9.0" => ".NET 9.",
            _ => ".NET 10.",
        };
        Assert.Contains(expected, framework);
        Assert.Equal(FeatureMatrix.CompiledFor != "net8.0", FeatureMatrix.Net9FeaturesCompiledIn);
    }
}
