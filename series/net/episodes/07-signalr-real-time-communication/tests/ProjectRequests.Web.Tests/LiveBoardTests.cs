using Microsoft.AspNetCore.Components;
using Microsoft.Extensions.DependencyInjection;
using ProjectRequests.Feed;
using ProjectRequests.Web.Client.Pages;

namespace ProjectRequests.Web.Tests;

/// <summary>Episode 7: the live board, with the test playing the SignalR server.</summary>
public sealed class LiveBoardTests : BunitContext
{
    private readonly FakeRequestsApi _api = new();
    private readonly FakeRequestsFeed _feed = new();

    public LiveBoardTests()
    {
        Services.AddSingleton<IRequestsApi>(_api);
        Services.AddSingleton<IRequestsFeedFactory>(_feed);
        SetRendererInfo(new RendererInfo("WebAssembly", isInteractive: true));
        _api.Requests.Add(FakeRequestsApi.Sample(1, 12_000m));
    }

    [Fact]
    public void Connects_then_loads_the_current_list()
    {
        var cut = Render<LiveBoard>();

        cut.WaitForAssertion(() => Assert.Contains("connected · watching all departments", cut.Find("#connection").TextContent));
        Assert.Single(cut.FindAll("#board tbody tr"));
        Assert.Equal([null], _feed.Watched);
    }

    [Fact]
    public void A_pushed_request_appears_without_reloading()
    {
        var cut = Render<LiveBoard>();
        cut.WaitForAssertion(() => Assert.Single(cut.FindAll("#board tbody tr")));

        _feed.PushCreated(FakeRequestsApi.Sample(2, 80_000m) with { Title = "Data platform", Department = "IT" });

        cut.WaitForAssertion(() => Assert.Equal(2, cut.FindAll("#board tbody tr").Count));
        Assert.Contains("Data platform", cut.Find("#board tbody tr.live").TextContent);   // newest first, highlighted
        Assert.Contains("#2 created · IT · High · Submitted", cut.Find("#events").TextContent);
    }

    [Fact]
    public void A_pushed_decision_updates_the_row()
    {
        var cut = Render<LiveBoard>();
        cut.WaitForAssertion(() => Assert.Single(cut.FindAll("#board tbody tr")));

        _feed.PushUpdated(FakeRequestsApi.Sample(1, 12_000m, RequestStatus.Approved) with
        {
            DecidedBy = "sam.demo@contoso.com", DecidedAtUtc = new DateTime(2026, 11, 21, 10, 0, 0, DateTimeKind.Utc),
        });

        cut.WaitForAssertion(() => Assert.Equal("Approved", cut.Find("#board td.status").TextContent));
    }

    [Fact]
    public void Choosing_a_department_rewatches_and_filters()
    {
        _api.Requests.Add(FakeRequestsApi.Sample(2) with { Department = "IT" });
        var cut = Render<LiveBoard>();
        cut.WaitForAssertion(() => Assert.Equal(2, cut.FindAll("#board tbody tr").Count));

        cut.Find("#department").Change("IT");

        cut.WaitForAssertion(() => Assert.Single(cut.FindAll("#board tbody tr")));
        Assert.Equal([null, "IT"], _feed.Watched);

        _feed.PushCreated(FakeRequestsApi.Sample(3) with { Department = "FIN" });     // late event from the old group
        Assert.Single(cut.FindAll("#board tbody tr"));
    }

    [Fact]
    public void Shows_reconnecting_and_reloads_after_the_reconnect()
    {
        var cut = Render<LiveBoard>();
        cut.WaitForAssertion(() => Assert.Single(cut.FindAll("#board tbody tr")));

        _feed.SetState(FeedState.Reconnecting);
        cut.WaitForAssertion(() => Assert.Contains("reconnecting", cut.Find("#connection").TextContent));

        _api.Requests.Add(FakeRequestsApi.Sample(2));                                   // created while we were away
        _feed.Reconnect();

        cut.WaitForAssertion(() => Assert.Equal(2, cut.FindAll("#board tbody tr").Count));
        Assert.Contains("reconnected: reloading the list", cut.Find("#events").TextContent);
    }

    [Fact]
    public void Says_so_when_the_hub_cannot_be_reached()
    {
        _feed.StartFailure = new HttpRequestException("TypeError: Failed to fetch");

        var cut = Render<LiveBoard>();

        cut.WaitForAssertion(() => Assert.Contains("Live updates unavailable: TypeError: Failed to fetch", cut.Find("#feed-error").TextContent));
    }

    [Fact]
    public async Task Leaving_the_page_closes_the_connection()
    {
        var cut = Render<LiveBoard>();
        cut.WaitForAssertion(() => Assert.Single(cut.FindAll("#board tbody tr")));

        await DisposeComponentsAsync();

        Assert.True(_feed.Disposed);
    }
}
