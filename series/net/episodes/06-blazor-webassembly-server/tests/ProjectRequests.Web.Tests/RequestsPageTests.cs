using Microsoft.AspNetCore.Components;
using Microsoft.Extensions.DependencyInjection;
using ProjectRequests.Web.Components.Pages;

namespace ProjectRequests.Web.Tests;

public sealed class RequestsPageTests : BunitContext
{
    [Fact]
    public void Lists_every_request_with_a_link_to_its_page()
    {
        var api = new FakeRequestsApi();
        api.Requests.Add(FakeRequestsApi.Sample(1, 12_000m));
        api.Requests.Add(FakeRequestsApi.Sample(2, 80_000m, RequestStatus.Approved));
        Services.AddSingleton<IRequestsApi>(api);
        SetRendererInfo(new RendererInfo("Static", isInteractive: false));

        var cut = Render<Requests>();

        var rows = cut.FindAll("tbody tr");
        Assert.Equal(2, rows.Count);
        Assert.Equal("requests/2", rows[1].QuerySelector("a")!.GetAttribute("href"));
        Assert.Contains("High", rows[1].TextContent);
        Assert.Contains("Approved", rows[1].TextContent);
    }
}
