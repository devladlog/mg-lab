using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Contoso.Budget.Service;
using Contoso.Requests.Service.Requests;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;
using Yarp.ReverseProxy.Forwarder;

namespace Contoso.Microservices.Tests;

public class GatewayTests : IDisposable
{
    private readonly Lab _lab = new();
    private readonly PortRouter _router = new();
    private readonly WebApplicationFactory<GatewayMarker> _gateway;
    private readonly HttpClient _http;

    public GatewayTests()
    {
        // The gateway config says "http://requests/" and "http://budget/"; service discovery turns them into localhost:5312 / :5313
        // (appsettings.json), and the router below stands in for the network behind those two ports.
        _router.Add(5312, _lab.Requests.Server.CreateHandler()).Add(5313, _lab.Budget.Server.CreateHandler());
        _gateway = new WebApplicationFactory<GatewayMarker>().WithWebHostBuilder(b => b.ConfigureTestServices(s =>
        {
            s.AddSingleton<IForwarderHttpClientFactory>(new InMemoryForwarderClients(_router));
            s.AddHttpClient("downstream").ConfigurePrimaryHttpMessageHandler(() => _router);
        }));
        _http = _gateway.CreateClient();
    }

    public void Dispose() { _http.Dispose(); _gateway.Dispose(); _lab.Dispose(); }

    [Fact]
    public async Task Requests_and_budgets_are_routed_to_their_services()
    {
        var created = await _http.PostAsJsonAsync("/api/requests", Lab.NewRequest());
        Assert.Equal(HttpStatusCode.Created, created.StatusCode);
        var id = (await created.Content.ReadFromJsonAsync<RequestDto>())!.Id;

        // The request is in the Requests service's own database...
        Assert.Equal(HttpStatusCode.OK, (await _lab.RequestsHttp.GetAsync($"/api/requests/{id}")).StatusCode);
        // ...and the gateway also serves the Budget route.
        var fin = await _http.GetFromJsonAsync<BudgetStatus>("/api/budgets/FIN");
        Assert.Equal(12_000m, fin!.Reserved);
    }

    [Fact]
    public async Task The_list_route_without_a_trailing_path_matches_too()
    {
        Assert.Equal(HttpStatusCode.OK, (await _http.GetAsync("/api/requests")).StatusCode);
        Assert.Equal(HttpStatusCode.OK, (await _http.GetAsync("/api/budgets")).StatusCode);
    }

    [Fact]
    public async Task Unknown_paths_are_404_at_the_gateway()
    {
        Assert.Equal(HttpStatusCode.NotFound, (await _http.GetAsync("/api/payroll")).StatusCode);
    }

    [Fact]
    public async Task A_service_that_is_down_gives_502_on_its_route_and_the_other_route_keeps_working()
    {
        _router.Down.Add(5312);
        Assert.Equal(HttpStatusCode.BadGateway, (await _http.GetAsync("/api/requests")).StatusCode);
        Assert.Equal(HttpStatusCode.OK, (await _http.GetAsync("/api/budgets/FIN")).StatusCode);
    }

    [Fact]
    public async Task The_services_health_page_is_healthy_when_both_answer_and_degraded_when_one_does_not()
    {
        var healthy = await _http.GetAsync("/health/services");
        Assert.Equal(HttpStatusCode.OK, healthy.StatusCode);
        Assert.Equal("Healthy", JsonDocument.Parse(await healthy.Content.ReadAsStringAsync()).RootElement.GetProperty("status").GetString());

        _router.Down.Add(5313);
        var degraded = await _http.GetAsync("/health/services");
        Assert.Equal(HttpStatusCode.OK, degraded.StatusCode);   // Degraded is still 200: the gateway itself works
        var json = JsonDocument.Parse(await degraded.Content.ReadAsStringAsync()).RootElement;
        Assert.Equal("Degraded", json.GetProperty("status").GetString());
        Assert.Equal("Degraded", json.GetProperty("services").GetProperty("budget").GetProperty("status").GetString());
        Assert.Equal("Healthy", json.GetProperty("services").GetProperty("requests").GetProperty("status").GetString());
        Assert.Equal("Healthy", await _http.GetStringAsync("/alive"));
    }
}
