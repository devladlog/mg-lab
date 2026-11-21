using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Contoso.Orders.Api;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Options;
using Microsoft.Extensions.Time.Testing;
using Xunit;

namespace Contoso.Orders.Api.Tests;

public class ApiTests : IClassFixture<ApiTests.Factory>
{
    public sealed class Factory : WebApplicationFactory<Program>
    {
        protected override void ConfigureWebHost(IWebHostBuilder builder) =>
            builder.UseSetting("Lifecycle:WarmupSeconds", "0").UseSetting("Lifecycle:DrainSeconds", "0");
    }

    private readonly HttpClient _http;
    public ApiTests(Factory f) => _http = f.CreateClient();

    [Fact]
    public async Task Root_reports_version_and_platform_and_sets_the_header()
    {
        var res = await _http.GetAsync("/");
        var body = JsonDocument.Parse(await res.Content.ReadAsStringAsync()).RootElement;
        Assert.Equal("1.0.0", body.GetProperty("version").GetString());
        Assert.Equal("local", body.GetProperty("platform").GetString());
        Assert.Equal("1.0.0", res.Headers.GetValues("X-App-Version").Single());
    }

    [Fact]
    public async Task Probes_answer_on_their_own_paths()
    {
        Assert.Equal(HttpStatusCode.OK, (await _http.GetAsync("/healthz/live")).StatusCode);
        Assert.Equal(HttpStatusCode.OK, (await _http.GetAsync("/healthz/ready")).StatusCode);
    }

    [Fact]
    public async Task Quote_applies_the_discount_from_500_eur()
    {
        var q = await (await _http.PostAsJsonAsync("/quotes", new { lines = new[] { new { sku = "MON-270", quantity = 2 }, new { sku = "DOC-100", quantity = 1 } } }))
            .Content.ReadFromJsonAsync<Quote>();
        Assert.Equal(568.98m, q!.Subtotal);
        Assert.Equal(28.45m, q.Discount);
        Assert.Equal(540.53m, q.Total);
    }

    [Theory]
    [InlineData("{\"lines\":[]}", 400)]
    [InlineData("{\"lines\":[{\"sku\":\"mon-270\",\"quantity\":1}]}", 400)]
    [InlineData("{\"lines\":[{\"sku\":\"XYZ-999\",\"quantity\":1}]}", 422)]
    public async Task Bad_quotes_are_rejected(string json, int status)
    {
        var res = await _http.PostAsync("/quotes", new StringContent(json, System.Text.Encoding.UTF8, "application/json"));
        Assert.Equal(status, (int)res.StatusCode);
    }
}

public class ReadinessTests
{
    private static Readiness New(FakeTimeProvider t, int warmup = 3) =>
        new(t, Options.Create(new LifecycleOptions { WarmupSeconds = warmup }));

    [Fact]
    public void Not_ready_during_warmup_then_ready()
    {
        var t = new FakeTimeProvider();
        var r = New(t);
        Assert.Equal(ReadyState.WarmingUp, r.State);
        t.Advance(TimeSpan.FromSeconds(3));
        Assert.Equal(ReadyState.Ready, r.State);
    }

    [Fact]
    public void Draining_wins_over_everything()
    {
        var t = new FakeTimeProvider();
        var r = New(t, warmup: 0);
        r.BeginDrain();
        Assert.Equal(ReadyState.Draining, r.State);
    }

    [Fact]
    public async Task Sigterm_flips_readiness_to_503_and_keeps_serving_for_the_drain_period()
    {
        await using var f = new WebApplicationFactory<Program>().WithWebHostBuilder(b =>
            b.UseSetting("Lifecycle:WarmupSeconds", "0").UseSetting("Lifecycle:DrainSeconds", "2"));
        var http = f.CreateClient();
        Assert.Equal(HttpStatusCode.OK, (await http.GetAsync("/healthz/ready")).StatusCode);

        // What the host does on SIGTERM: StopAsync, which runs StoppingAsync first
        var lifetime = f.Services.GetRequiredService<Microsoft.Extensions.Hosting.IHostApplicationLifetime>();
        var stopping = Task.Run(lifetime.StopApplication);
        await Task.Delay(300);

        var ready = await http.GetAsync("/healthz/ready");
        Assert.Equal(HttpStatusCode.ServiceUnavailable, ready.StatusCode);
        Assert.Contains("Draining", await ready.Content.ReadAsStringAsync());
        Assert.Equal(HttpStatusCode.OK, (await http.GetAsync("/healthz/live")).StatusCode); // still answering
        await stopping;
    }
}
