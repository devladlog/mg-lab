using Microsoft.AspNetCore.Components;
using Microsoft.Extensions.DependencyInjection;
using ProjectRequests.Web.Components.Pages;

namespace ProjectRequests.Web.Tests;

/// <summary>The Interactive Server page: the buttons' handlers run on the server, against IRequestsApi.</summary>
public sealed class RequestDetailTests : BunitContext
{
    private readonly FakeRequestsApi _api = new();

    public RequestDetailTests()
    {
        Services.AddSingleton<IRequestsApi>(_api);
        SetRendererInfo(new RendererInfo("Server", isInteractive: true));
        _api.Requests.Add(FakeRequestsApi.Sample(id: 1, budget: 80_000m));
    }

    [Fact]
    public void Approve_sends_the_version_that_was_shown_and_updates_the_status()
    {
        var cut = Render<RequestDetail>(p => p.Add(c => c.Id, 1));

        cut.Find("#approve").Click();

        var (id, decision) = Assert.Single(_api.Decisions);
        Assert.Equal(1, id);
        Assert.Equal(Guid.Parse("00000000-0000-0000-0000-000000000001"), decision.Version);
        Assert.Equal("sam.approver@contoso.com", decision.DecidedBy);
        cut.WaitForAssertion(() => Assert.Equal("Approved", cut.Find("#status").TextContent));
        Assert.Empty(cut.FindAll("#approve"));                                // decided: no more buttons
    }

    [Fact]
    public void A_409_from_the_API_is_shown_and_nothing_changes()
    {
        _api.NextFailure = new ApiResult<RequestDto>(null, "Request already decided. Request 1 is Approved.",
            new Dictionary<string, string[]>());
        var cut = Render<RequestDetail>(p => p.Add(c => c.Id, 1));

        cut.Find("#reject").Click();

        cut.WaitForAssertion(() => Assert.Contains("Request already decided.", cut.Find("#problem").TextContent));
        Assert.Equal("Submitted", cut.Find("#status").TextContent);
    }

    [Fact]
    public void Unknown_id_says_not_found()
    {
        var cut = Render<RequestDetail>(p => p.Add(c => c.Id, 42));

        Assert.Contains("Request 42 was not found.", cut.Markup);
    }
}
