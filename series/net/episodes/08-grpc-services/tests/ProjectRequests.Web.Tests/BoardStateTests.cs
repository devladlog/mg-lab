using ProjectRequests.Web.Client.Services;

namespace ProjectRequests.Web.Tests;

/// <summary>The merge rules: events and the initial list can arrive in either order.</summary>
public sealed class BoardStateTests
{
    private static readonly DateTime Ten = new(2026, 11, 21, 10, 0, 0, DateTimeKind.Utc);

    [Fact]
    public void An_older_submitted_copy_from_the_list_does_not_undo_a_pushed_decision()
    {
        var board = new BoardState();
        board.Apply(FakeRequestsApi.Sample(1, status: RequestStatus.Approved) with { DecidedAtUtc = Ten });

        board.Load([FakeRequestsApi.Sample(1)]);                    // the list was read before the decision

        Assert.Equal(RequestStatus.Approved, Assert.Single(board.Requests).Status);
    }

    [Fact]
    public void A_budget_change_replaces_the_submitted_copy()
    {
        var board = new BoardState();
        board.Load([FakeRequestsApi.Sample(1, 12_000m)]);

        Assert.True(board.Apply(FakeRequestsApi.Sample(1, 60_000m)));

        Assert.Equal(Priority.High, Assert.Single(board.Requests).Priority);
        Assert.Contains(1, board.Highlighted);
    }

    [Fact]
    public void Newest_request_first_and_loading_does_not_highlight()
    {
        var board = new BoardState();
        board.Load([FakeRequestsApi.Sample(1), FakeRequestsApi.Sample(3), FakeRequestsApi.Sample(2)]);

        Assert.Equal([3, 2, 1], board.Requests.Select(r => r.Id));
        Assert.Empty(board.Highlighted);
    }
}
