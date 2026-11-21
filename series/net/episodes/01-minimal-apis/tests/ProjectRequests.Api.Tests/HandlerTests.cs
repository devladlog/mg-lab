using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Http.HttpResults;
using ProjectRequests.Api.Requests;

namespace ProjectRequests.Api.Tests;

/// <summary>
/// Unit tests: call the handlers directly. Because they return TypedResults, we can assert on the concrete type
/// without starting a web host.
/// </summary>
public class HandlerTests
{
    private readonly InMemoryRequestStore _store = new(TimeProvider.System);

    private ProjectRequest Seed(decimal budget = 10_000m, string by = "alex.demo@contoso.com") =>
        _store.Add(new CreateProjectRequest { Title = "Laptop refresh", Budget = budget, RequestedBy = by });

    [Theory]
    [InlineData(49_999.99, Priority.Standard)]
    [InlineData(50_000, Priority.High)]      // the threshold itself is High (>=)
    [InlineData(1_000_000, Priority.High)]
    public void Classify_uses_greater_or_equal(decimal budget, Priority expected) =>
        Assert.Equal(expected, PriorityRules.Classify(budget));

    [Fact]
    public void GetById_returns_NotFound_for_unknown_id()
    {
        var result = RequestEndpoints.GetById(42, _store);
        Assert.IsType<NotFound>(result.Result);
    }

    [Fact]
    public void GetById_returns_Ok_with_the_item()
    {
        var seeded = Seed();
        var result = RequestEndpoints.GetById(seeded.Id, _store);
        var ok = Assert.IsType<Ok<ProjectRequest>>(result.Result);
        Assert.Equal(seeded, ok.Value);
    }

    [Fact]
    public void Create_returns_Created_with_location_and_normalised_email()
    {
        var result = RequestEndpoints.Create(
            new CreateProjectRequest { Title = "  CRM rollout ", Budget = 75_000m, RequestedBy = "Alex.Demo@Contoso.com" },
            _store);

        Assert.Equal($"/api/requests/{result.Value!.Id}", result.Location);
        Assert.Equal("CRM rollout", result.Value.Title);
        Assert.Equal("alex.demo@contoso.com", result.Value.RequestedBy);
        Assert.Equal(Priority.High, result.Value.Priority);
        Assert.Equal(RequestStatus.Submitted, result.Value.Status);
    }

    [Fact]
    public void Decide_rejects_deciding_your_own_request()
    {
        var seeded = Seed(by: "alex.demo@contoso.com");
        var result = RequestEndpoints.Decide(seeded.Id,
            new DecisionRequest { Approve = true, DecidedBy = "ALEX.DEMO@contoso.com" }, _store);

        var problem = Assert.IsType<ProblemHttpResult>(result.Result);
        Assert.Equal(StatusCodes.Status409Conflict, problem.StatusCode);
    }

    [Fact]
    public void Decide_approves_once_then_conflicts()
    {
        var seeded = Seed();
        var decision = new DecisionRequest { Approve = true, DecidedBy = "sam.approver@contoso.com" };

        var first = Assert.IsType<Ok<ProjectRequest>>(RequestEndpoints.Decide(seeded.Id, decision, _store).Result);
        Assert.Equal(RequestStatus.Approved, first.Value!.Status);
        Assert.Equal("sam.approver@contoso.com", first.Value.DecidedBy);

        var second = Assert.IsType<ProblemHttpResult>(RequestEndpoints.Decide(seeded.Id, decision, _store).Result);
        Assert.Equal(StatusCodes.Status409Conflict, second.StatusCode);
    }

    [Fact]
    public void Decide_returns_NotFound_for_unknown_id()
    {
        var result = RequestEndpoints.Decide(999,
            new DecisionRequest { Approve = false, DecidedBy = "sam.approver@contoso.com" }, _store);
        Assert.IsType<NotFound>(result.Result);
    }

    [Fact]
    public void List_filters_by_priority()
    {
        Seed(10_000m);
        Seed(80_000m);
        var high = RequestEndpoints.List(_store, Priority.High).Value!;
        Assert.Single(high);
        Assert.Equal(80_000m, high[0].Budget);
        Assert.Equal(2, RequestEndpoints.List(_store, null).Value!.Count);
    }
}
