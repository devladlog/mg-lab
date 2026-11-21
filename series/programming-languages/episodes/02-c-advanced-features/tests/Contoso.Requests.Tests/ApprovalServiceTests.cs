using Contoso.Requests;

namespace Contoso.Requests.Tests;

public class ApprovalServiceTests
{
    private readonly InMemoryRequestStore _store = new();
    private readonly ApprovalMetrics _metrics = new();
    private readonly ApprovalService _service;

    public ApprovalServiceTests() => _service = new ApprovalService(new FixedClock(TestData.Now), _store, _metrics);

    private RequestCode Add(ProjectRequest request)
    {
        _store.Save(request);
        return request.Code;
    }

    [Fact]
    public void Finance_request_is_approved_by_finance()
    {
        var code = Add(TestData.Request(75_000m));
        Assert.IsType<DecisionResult.Ok>(_service.Submit(code));

        var result = Assert.IsType<DecisionResult.Ok>(_service.Approve(code, TestData.Sam, "Finance"));
        Assert.Equal(new RequestState.Approved("sam.demo@contoso.com", TestData.Now), result.Request.State);
        Assert.Equal(1, _metrics.Approved);
        Assert.Equal(TestData.Now, _metrics.LastDecisionAt);
    }

    [Fact]
    public void Board_request_needs_finance_then_board()
    {
        var code = Add(TestData.Request(300_000m, "Replaces three legacy warehouses."));
        _service.Submit(code);

        var afterFinance = Assert.IsType<DecisionResult.Ok>(_service.Approve(code, TestData.Sam, "Finance"));
        Assert.IsType<RequestState.Submitted>(afterFinance.Request.State);
        Assert.Equal(0, _metrics.Approved);

        var afterBoard = Assert.IsType<DecisionResult.Ok>(_service.Approve(code, TestData.Kim, "Board"));
        Assert.IsType<RequestState.Approved>(afterBoard.Request.State);
        Assert.Equal(["Finance", "Board"], afterBoard.Request.Approvals.Select(a => a.Role));
    }

    [Fact]
    public void You_cant_approve_your_own_request()
    {
        var code = Add(TestData.Request(75_000m));
        _service.Submit(code);
        Assert.Equal(new DecisionResult.Refused("You can't approve your own request."),
            _service.Approve(code, TestData.Alex, "Finance"));
    }

    [Fact]
    public void Large_budget_without_justification_cant_be_submitted()
    {
        var code = Add(TestData.Request(250_000m));
        Assert.IsType<DecisionResult.Refused>(_service.Submit(code));
    }

    [Fact]
    public void Unknown_code_is_NotFound() =>
        Assert.Equal(new DecisionResult.NotFound(new RequestCode(2026, 99)), _service.Submit(new RequestCode(2026, 99)));

    [Fact]
    public void Rejection_needs_a_reason_and_counts_in_metrics()
    {
        var code = Add(TestData.Request(75_000m));
        _service.Submit(code);
        Assert.IsType<DecisionResult.Refused>(_service.Reject(code, TestData.Sam, "  "));

        var result = Assert.IsType<DecisionResult.Ok>(_service.Reject(code, TestData.Sam, " No budget this year "));
        Assert.Equal(new RequestState.Rejected("sam.demo@contoso.com", "No budget this year"), result.Request.State);
        Assert.Equal(1, _metrics.Rejected);
    }

    [Fact]
    public void Only_drafts_can_be_submitted_and_only_submitted_can_be_decided()
    {
        var code = Add(TestData.Request(75_000m));
        Assert.IsType<DecisionResult.Refused>(_service.Approve(code, TestData.Sam, "Finance"));
        _service.Submit(code);
        Assert.IsType<DecisionResult.Refused>(_service.Submit(code));
    }

    [Fact]
    public void Null_conditional_assignment_skips_missing_metrics()
    {
        var store = new InMemoryRequestStore();
        var service = new ApprovalService(new FixedClock(TestData.Now), store); // no metrics
        var request = TestData.Request(75_000m);
        store.Save(request);
        service.Submit(request.Code);

        Assert.IsType<DecisionResult.Ok>(service.Approve(request.Code, TestData.Sam, "Finance")); // no NullReferenceException
    }
}
