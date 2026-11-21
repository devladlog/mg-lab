using Kusto.Language;

namespace Contoso.Orders.Api.Tests;

/// <summary>
/// Every query in queries/ is parsed and semantically checked against the workspace schema:
/// unknown tables, misspelled columns, type errors and syntax errors fail the build, not the
/// 3 a.m. alert. (No query is executed here; the recorder runs them in Log Analytics.)
/// </summary>
public class KqlTests
{
    private static string QueriesDir => Path.Combine(AppContext.BaseDirectory, "queries");

    public static TheoryData<string> QueryFiles()
    {
        var data = new TheoryData<string>();
        foreach (var f in Directory.GetFiles(Path.Combine(AppContext.BaseDirectory, "queries"), "*.kql").Order())
            data.Add(Path.GetFileName(f));
        return data;
    }

    private static IReadOnlyList<string> Errors(string query) =>
        KustoCode.ParseAndAnalyze(query, WorkspaceSchema.Globals).GetDiagnostics()
            .Where(d => d.Severity == "Error")
            .Select(d => $"{d.Code} {d.Message} at {d.Start}")
            .ToList();

    [Theory]
    [MemberData(nameof(QueryFiles))]
    public void Query_is_valid_against_the_workspace_schema(string file)
    {
        var errors = Errors(File.ReadAllText(Path.Combine(QueriesDir, file)));
        Assert.True(errors.Count == 0, $"{file}:\n" + string.Join("\n", errors));
    }

    [Fact]
    public void There_are_six_queries() => Assert.Equal(6, Directory.GetFiles(QueriesDir, "*.kql").Length);

    [Theory]
    [InlineData("AppRequests | summarize count() by OperationNmae")]             // typo in a column
    [InlineData("AppRequest | take 1")]                                            // typo in a table
    [InlineData("AppRequests | extend x = DurationMs + Name")]                     // real + string
    [InlineData("requests | summarize sum(itemCount)")]                            // classic name, wrong place
    public void The_checker_really_catches_mistakes(string broken) =>
        Assert.NotEmpty(Errors(broken));

    [Fact]
    public void Counting_queries_respect_sampling()
    {
        // count() on sampled tables undercounts; every query that counts requests uses sum(ItemCount)
        foreach (var file in Directory.GetFiles(QueriesDir, "*.kql"))
        {
            var text = string.Join("\n", File.ReadLines(file).Where(l => !l.TrimStart().StartsWith("//")));
            if (text.Contains("AppRequests") && text.Contains("summarize"))
                Assert.DoesNotContain("count()", text);
        }
    }
}
