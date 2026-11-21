using Xunit;

namespace MGLab.D365.Plugins.Tests;

public class ProjectRiskTests
{
    private static readonly DateTime Today = new(2027, 1, 15);

    [Fact]
    public void Quiet_request_is_low_with_no_reasons()
    {
        var r = ProjectRisk.Assess(new RiskInput
        {
            Budget = 42000m, DueDate = Today.AddDays(90), HasJustification = false, HasCustomerAccount = true,
            OtherOpenRequests = 1,
        }, Today);
        Assert.Equal((0, "Low"), (r.Score, r.Level));
        Assert.Equal("No risk factors", r.ReasonsText);
    }

    [Fact]
    public void Large_budget_without_justification_due_soon_is_high()
    {
        var r = ProjectRisk.Assess(new RiskInput
        {
            Budget = 75000m, DueDate = Today.AddDays(10), HasJustification = false, HasCustomerAccount = true,
        }, Today);
        Assert.Equal((75, "High"), (r.Score, r.Level));
        Assert.Equal(new[] { "Budget 75,000 is at or over 50,000", "No business justification for a large budget",
                             "Due in 10 day(s)" }, r.Reasons);
    }

    [Fact]
    public void Justification_removes_its_points_but_not_the_budget_ones()
    {
        var r = ProjectRisk.Assess(new RiskInput
        {
            Budget = 75000m, DueDate = Today.AddDays(10), HasJustification = true, HasCustomerAccount = true,
        }, Today);
        Assert.Equal((50, "Medium"), (r.Score, r.Level));
    }

    [Theory]
    [InlineData(-3, 30, "Due date passed 3 day(s) ago")]
    [InlineData(0, 20, "Due in 0 day(s)")]
    [InlineData(30, 20, "Due in 30 day(s)")]
    [InlineData(31, 0, null)]
    public void Due_date_boundaries(int days, int expected, string reason)
    {
        var r = ProjectRisk.Assess(new RiskInput { DueDate = Today.AddDays(days), HasCustomerAccount = true }, Today);
        Assert.Equal(expected, r.Score);
        if (reason != null) Assert.Contains(reason, r.Reasons);
        else Assert.Empty(r.Reasons);
    }

    [Fact]
    public void Time_of_day_does_not_change_the_day_count()
    {
        var r = ProjectRisk.Assess(new RiskInput { DueDate = Today.AddDays(1), HasCustomerAccount = true },
                                   Today.AddHours(23).AddMinutes(59));
        Assert.Contains("Due in 1 day(s)", r.Reasons);
    }

    [Fact]
    public void Budget_threshold_is_inclusive()
    {
        var at = ProjectRisk.Assess(new RiskInput { Budget = 50000m, HasJustification = true, DueDate = Today.AddDays(60), HasCustomerAccount = true }, Today);
        var under = ProjectRisk.Assess(new RiskInput { Budget = 49999.99m, DueDate = Today.AddDays(60), HasCustomerAccount = true }, Today);
        Assert.Equal(30, at.Score);
        Assert.Equal(0, under.Score);
    }

    [Fact]
    public void Missing_account_scores_instead_of_crowded_account()
    {
        var none = ProjectRisk.Assess(new RiskInput { DueDate = Today.AddDays(60), HasCustomerAccount = false, OtherOpenRequests = 5 }, Today);
        var crowded = ProjectRisk.Assess(new RiskInput { DueDate = Today.AddDays(60), HasCustomerAccount = true, OtherOpenRequests = 2 }, Today);
        Assert.Equal(new[] { "No customer account" }, none.Reasons);
        Assert.Equal(new[] { "Account has 2 other open requests" }, crowded.Reasons);
        Assert.Equal(15, crowded.Score);
    }

    [Fact]
    public void Every_factor_at_once_is_exactly_100()
    {
        var r = ProjectRisk.Assess(new RiskInput { Budget = 1_000_000m, DueDate = Today.AddDays(-1), HasCustomerAccount = true, OtherOpenRequests = 9 }, Today);
        Assert.Equal(100, r.Score);   // 30 + 25 + 30 + 15: the Math.Min cap is only a guard for future rules
        Assert.Equal("High", r.Level);
    }

    [Theory]
    [InlineData(39, "Low")]
    [InlineData(40, "Medium")]
    [InlineData(69, "Medium")]
    [InlineData(70, "High")]
    public void Level_boundaries(int score, string level) => Assert.Equal(level, ProjectRisk.LevelFor(score));
}
