using Contoso.Requests;

namespace Contoso.Requests.Tests;

public class PatternTests
{
    [Theory]
    [InlineData(49_999, Priority.Standard)]
    [InlineData(50_000, Priority.High)]
    public void Priority_is_High_from_exactly_50000(int budget, Priority expected) =>
        Assert.Equal(expected, Rules.PriorityFor(new Euros(budget)));

    [Theory]
    [InlineData(18_000, null, Route.TeamLead)]
    [InlineData(18_000, "Needed for the audit", Route.Finance)]
    [InlineData(50_000, null, Route.Finance)]
    [InlineData(249_999, null, Route.Finance)]
    [InlineData(250_000, "Board level investment", Route.Board)]
    public void Route_follows_the_policy(int budget, string? justification, Route expected) =>
        Assert.Equal(expected, Rules.RouteFor(TestData.Request(budget, justification)));

    private static Approval A(string role) => new("x@contoso.com", role, TestData.Now);

    [Theory]
    [InlineData(18_000, new string[0], false)]
    [InlineData(18_000, new[] { "TeamLead" }, true)]
    [InlineData(75_000, new[] { "TeamLead" }, false)]
    [InlineData(75_000, new[] { "TeamLead", "Finance" }, true)]
    [InlineData(300_000, new[] { "Finance" }, false)]
    [InlineData(300_000, new[] { "Board", "Finance" }, false)]
    [InlineData(300_000, new[] { "Finance", "Board" }, true)]
    [InlineData(300_000, new[] { "Finance", "Legal", "Board" }, true)]
    public void List_patterns_decide_when_a_request_is_fully_approved(int budget, string[] roles, bool expected)
    {
        var justification = budget >= 250_000 ? "Board level investment" : null;
        var request = TestData.Request(budget, justification) with { Approvals = [.. roles.Select(A)] };
        Assert.Equal(expected, Rules.IsFullyApproved(request));
    }

    [Fact]
    public void Describe_covers_every_state()
    {
        Assert.Equal("Draft", Rules.Describe(new RequestState.Draft()));
        Assert.Equal("Waiting for approval since 2026-11-21", Rules.Describe(new RequestState.Submitted(TestData.Now)));
        Assert.Equal("Approved by sam", Rules.Describe(new RequestState.Approved("sam", TestData.Now)));
        Assert.Equal("Rejected by sam: No budget", Rules.Describe(new RequestState.Rejected("sam", "No budget")));
    }
}
