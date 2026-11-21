using System.Net;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using Contoso.FinanceReview;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;

namespace FinanceReview.Tests;

/// <summary>The real ASP.NET Core pipeline, in memory, called the way the Dapr sidecar calls it.</summary>
public class EndpointTests : IClassFixture<WebApplicationFactory<Program>>
{
    private readonly FakeSink _sink = new();
    private readonly HttpClient _client;

    public EndpointTests(WebApplicationFactory<Program> factory)
    {
        _client = factory.WithWebHostBuilder(b => b.ConfigureTestServices(s =>
            s.Replace(ServiceDescriptor.Singleton<IFinanceReviewSink>(_sink)))).CreateClient();
    }

    private static StringContent CloudEvent(string body)
    {
        var json = JsonSerializer.Serialize(new { specversion = "1.0", data_base64 = Convert.ToBase64String(Encoding.UTF8.GetBytes(body)) });
        // This is the content type the sidecar really uses; binding a JsonElement parameter would answer 415 here.
        return new StringContent(json, Encoding.UTF8, "application/cloudevents+json");
    }

    [Fact]
    public async Task Subscribe_declares_the_topic_the_route_and_raw_payload()
    {
        var subs = await _client.GetFromJsonAsync<JsonElement>("/dapr/subscribe");
        var s = Assert.Single(subs.EnumerateArray());
        Assert.Equal("purchase-pubsub", s.GetProperty("pubsubname").GetString());
        Assert.Equal("purchase-events", s.GetProperty("topic").GetString());
        Assert.Equal("/finance-review", s.GetProperty("routes").GetProperty("default").GetString());
        Assert.Equal("true", s.GetProperty("metadata").GetProperty("rawPayload").GetString());
    }

    [Fact]
    public async Task Health_is_ok()
    {
        var r = await _client.GetAsync("/healthz");
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
    }

    [Fact]
    public async Task A_cloudevents_json_post_returns_200_and_status_success()
    {
        var r = await _client.PostAsync("/finance-review", CloudEvent("""{"eventType":"approved","purchaseRequestId":"PR-3001","requestedBy":"sam.demo@contoso.example","total":12000,"currency":"EUR"}"""));
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        var body = await r.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("SUCCESS", body.GetProperty("status").GetString());
        Assert.False(body.TryGetProperty("reason", out _)); // null reasons are not written
        Assert.Equal("PR-3001", Assert.Single(_sink.Opened).PurchaseRequestId);
    }

    [Fact]
    public async Task A_poison_message_gets_200_and_DROP_so_the_sidecar_does_not_redeliver_it_forever()
    {
        var r = await _client.PostAsync("/finance-review", CloudEvent("""{"eventType":"approved"}"""));
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        var body = await r.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("DROP", body.GetProperty("status").GetString());
        Assert.Empty(_sink.Opened);
    }

    [Fact]
    public async Task A_body_that_is_not_json_is_dropped()
    {
        var r = await _client.PostAsync("/finance-review", new StringContent("<xml/>", Encoding.UTF8, "text/plain"));
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.Equal("DROP", (await r.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("status").GetString());
    }
}
