namespace Contoso.Portfolio.Tests;

public class ImportTests
{
    private static readonly IReadOnlySet<string> Known = SampleData.Departments.Select(d => d.Code).ToHashSet();

    [Fact]
    public void A_valid_line_becomes_a_draft_request()
    {
        var result = Import.ParseLine("PR-2026-0201,Data warehouse tuning,IT,48000,2026-10-02", 1, Known);

        Assert.True(result.IsOk);
        Assert.Equal(new ProjectRequest(1, "PR-2026-0201", "Data warehouse tuning", "IT", 48_000m,
            RequestStatus.Draft, new DateOnly(2026, 10, 2)), result.Value);
    }

    [Theory]
    [InlineData("PR-1,Forklift lease,Operations,abc,2026-10-06", "budget 'abc' is not a positive number")]
    [InlineData("PR-1,Contract archive,Finance,30000,2026-10-08", "unknown department 'Finance'")]
    [InlineData("PR-1,Edge routers,IT,61000,2026-13-01", "date '2026-13-01' is not yyyy-MM-dd")]
    [InlineData("PR-1,Field sales tablets,Sales,54000", "expected 5 fields, found 4")]
    [InlineData("PR-1,Negative,IT,-5,2026-10-01", "budget '-5' is not a positive number")]
    public void Each_problem_has_a_readable_error(string line, string expected)
    {
        var result = Import.ParseLine(line, 1, Known);
        Assert.False(result.IsOk);
        Assert.Equal(expected, result.Error);
    }

    [Fact]
    public void Query_syntax_stops_at_the_first_error()
    {
        // Bad budget AND unknown department AND bad date: only the first failing step is reported.
        var result = Import.ParseLine("PR-1,Everything wrong,Finance,abc,never", 1, Known);
        Assert.Equal("budget 'abc' is not a positive number", result.Error);
    }

    [Fact]
    public void Reading_the_value_of_a_failure_throws()
    {
        var result = Result.Fail<int>("nope");
        Assert.Throws<InvalidOperationException>(() => result.Value);
    }

    [Fact]
    public void The_sample_file_has_4_good_and_4_bad_lines_with_line_numbers()
    {
        var path = Path.Combine(AppContext.BaseDirectory, "samples", "requests.csv");
        var result = Import.FromCsv(File.ReadLines(path), Known);

        Assert.Equal(["PR-2026-0201", "PR-2026-0202", "PR-2026-0204", "PR-2026-0208"], result.Accepted.Select(r => r.Code));
        Assert.Equal([4, 6, 7, 8], result.Rejected.Select(r => r.LineNumber));
    }

    [Fact]
    public void Select_maps_values_and_passes_errors_through()
    {
        Assert.Equal(Result.Ok(4), Result.Ok(2).Select(x => x * 2));
        Assert.Equal("bad", Result.Fail<int>("bad").Select(x => x * 2).Error);
    }
}
