namespace Contoso.Portfolio.Tests;

public class ReportsTests
{
    private static readonly IReadOnlyList<ProjectRequest> Requests = SampleData.Requests;

    [Fact]
    public void Totals_by_department_with_AggregateBy()
    {
        var totals = Reports.TotalsByDepartment(Requests);

        Assert.Equal(["IT", "SAL", "OPS", "MKT"], totals.Select(t => t.DepartmentCode));
        Assert.Equal(new DepartmentTotal("IT", 4, 354_500m), totals[0]);
        Assert.Equal(Requests.Sum(r => r.Budget), totals.Sum(t => t.Total));
    }

    [Fact]
    public void Method_syntax_and_query_syntax_give_the_same_report() =>
        Assert.Equal(Reports.TotalsByDepartment(Requests), Reports.TotalsByDepartmentQuerySyntax(Requests));

    [Fact]
    public void CountBy_status()
    {
        var counts = Reports.CountByStatus(Requests);
        Assert.Equal(5, counts[RequestStatus.Approved]);
        Assert.Equal(4, counts[RequestStatus.Submitted]);
        Assert.Equal(2, counts[RequestStatus.Draft]);
        Assert.Equal(1, counts[RequestStatus.Rejected]);
    }

    [Fact]
    public void Top_uses_Index_for_the_rank()
    {
        var top = Reports.Top(Requests, 3);
        Assert.Equal([1, 2, 3], top.Select(t => t.Rank));
        Assert.Equal(["PR-2026-0103", "PR-2026-0107", "PR-2026-0102"], top.Select(t => t.Code));
    }

    [Fact]
    public void LeftJoin_keeps_departments_without_requests()
    {
        var lines = Reports.AllDepartments(SampleData.Departments, Requests);

        Assert.Equal(5, lines.Count);
        Assert.Equal(new DepartmentLine("Legal", 0, 0m), lines[^1]);
    }

    [Fact]
    public void An_inner_Join_silently_drops_them()
    {
        var joined = SampleData.Departments.Join(Reports.TotalsByDepartment(Requests),
            d => d.Code, t => t.DepartmentCode, (d, t) => d.Name);
        Assert.DoesNotContain("Legal", joined);
    }

    [Fact]
    public void Rules_are_just_functions_passed_in()
    {
        Func<ProjectRequest, bool> high = r => Policy.PriorityFor(r.Budget) == Priority.High;
        Func<ProjectRequest, bool> it = r => r.DepartmentCode == "IT";

        Assert.Equal(["PR-2026-0102", "PR-2026-0103", "PR-2026-0108"], Requests.Needing(high).Select(r => r.Code));
        Assert.Equal(["PR-2026-0103", "PR-2026-0110"], Requests.Needing(it).Select(r => r.Code));
    }

    [Fact]
    public void Pure_functions_do_not_touch_their_input_and_repeat_exactly()
    {
        var before = Requests.ToList();
        var first = Reports.AllDepartments(SampleData.Departments, Requests);
        var second = Reports.AllDepartments(SampleData.Departments, Requests);

        Assert.Equal(first, second);
        Assert.Equal(before, Requests);
    }

    [Fact]
    public void Records_change_with_with_and_the_original_stays()
    {
        var original = Requests[0];
        var approved = original with { Status = RequestStatus.Rejected };

        Assert.Equal(RequestStatus.Approved, original.Status);
        Assert.NotEqual(original, approved);
    }
}
