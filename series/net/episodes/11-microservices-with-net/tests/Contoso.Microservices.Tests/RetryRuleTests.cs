using System.Net;
using Contoso.ServiceDefaults;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;

namespace Contoso.Microservices.Tests;

/// <summary>The one rule ServiceDefaults adds to the standard resilience handler: retry writes only with an Idempotency-Key.</summary>
public class RetryRuleTests
{
    private sealed class AlwaysFails : HttpMessageHandler
    {
        public int Attempts;
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            Interlocked.Increment(ref Attempts);
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.ServiceUnavailable));
        }
    }

    private static (HttpClient Client, AlwaysFails Server) Build()
    {
        var server = new AlwaysFails();
        var builder = Host.CreateApplicationBuilder();
        builder.AddServiceDefaults(o => o.Retry.Delay = TimeSpan.FromMilliseconds(1));
        builder.Services.AddHttpClient("probe").ConfigurePrimaryHttpMessageHandler(() => server);
        var host = builder.Build();
        return (host.Services.GetRequiredService<IHttpClientFactory>().CreateClient("probe"), server);
    }

    [Fact]
    public async Task A_get_is_retried_three_times()
    {
        var (client, server) = Build();
        var response = await client.GetAsync("http://probe.test/x");
        Assert.Equal(HttpStatusCode.ServiceUnavailable, response.StatusCode);
        Assert.Equal(4, server.Attempts);
    }

    [Fact]
    public async Task A_post_without_a_key_is_tried_once()
    {
        var (client, server) = Build();
        await client.PostAsync("http://probe.test/x", new StringContent("{}"));
        Assert.Equal(1, server.Attempts);
    }

    [Fact]
    public async Task A_post_with_an_idempotency_key_is_retried()
    {
        var (client, server) = Build();
        var request = new HttpRequestMessage(HttpMethod.Post, "http://probe.test/x") { Content = new StringContent("{}") };
        request.Headers.Add(Idempotency.Header, Guid.NewGuid().ToString());
        await client.SendAsync(request);
        Assert.Equal(4, server.Attempts);
    }
}
