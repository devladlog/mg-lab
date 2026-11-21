using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Options;
using Microsoft.Extensions.Time.Testing;
using ProjectRequests.Api.Notifications;

namespace ProjectRequests.Api.Tests;

/// <summary>Replaces the "log" channel in tests: records digests, can fail on purpose.</summary>
public sealed class RecordingChannel(int failFirst = 0) : INotificationChannel
{
    private int _calls;
    private readonly SemaphoreSlim _received = new(0);
    public List<PendingDigest> Digests { get; } = [];
    public int Attempts => Volatile.Read(ref _calls);
    public string Name => "log";

    public Task SendAsync(PendingDigest digest, CancellationToken ct)
    {
        if (Interlocked.Increment(ref _calls) <= failFirst)
            throw new HttpRequestException("Webhook returned 503 (simulated).");
        lock (Digests) Digests.Add(digest);
        _received.Release();
        return Task.CompletedTask;
    }

    public async Task WaitForDigestAsync()
    {
        if (!await _received.WaitAsync(TimeSpan.FromSeconds(10)))
            throw new TimeoutException("No digest arrived within 10 s.");
    }
}

public sealed class CapturingHandler : HttpMessageHandler
{
    public List<(HttpMethod Method, Uri Uri, string Body)> Requests { get; } = [];

    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
    {
        Requests.Add((request.Method, request.RequestUri!, await request.Content!.ReadAsStringAsync(ct)));
        return new HttpResponseMessage(HttpStatusCode.Accepted);
    }
}

public sealed class NotificationTests
{
    private const string WebhookUrl = "https://hooks.contoso.example/digest";

    private static object NewRequest(string department, decimal budget) => new
    {
        title = "Laptop refresh", budget, requestedBy = "alex.demo@contoso.com", departmentCode = department,
    };

    [Fact]
    public void Webhook_channel_without_a_url_stops_the_app_at_startup()
    {
        using var factory = new RequestsApiFactory(settings: new() { ["Notifications:Channel"] = "webhook" });

        var ex = Assert.ThrowsAny<Exception>(() => factory.CreateClient());

        var validation = Assert.IsType<OptionsValidationException>(ex is AggregateException a ? a.InnerExceptions.Single() : ex);
        Assert.Contains("WebhookUrl must be an absolute https URL", validation.Message);
        factory.DeleteDatabase();
    }

    [Fact]
    public void Unknown_channel_stops_the_app_at_startup()
    {
        using var factory = new RequestsApiFactory(settings: new() { ["Notifications:Channel"] = "teams" });

        var ex = Assert.ThrowsAny<Exception>(() => factory.CreateClient());

        Assert.Contains("Channel", ex.ToString());
        Assert.Contains("OptionsValidationException", ex.ToString());
        factory.DeleteDatabase();
    }

    [Theory]
    [InlineData("log", typeof(LogNotificationChannel))]
    [InlineData("webhook", typeof(WebhookNotificationChannel))]
    public void The_configured_key_picks_the_channel(string key, Type expected)
    {
        using var factory = new RequestsApiFactory(settings: new()
        {
            ["Notifications:Channel"] = key, ["Notifications:WebhookUrl"] = WebhookUrl,
        });
        factory.CreateClient();

        using var scope = factory.Services.CreateScope();
        Assert.IsType(expected, scope.ServiceProvider.GetRequiredService<INotificationChannel>());
        Assert.IsType(expected, scope.ServiceProvider.GetRequiredKeyedService<INotificationChannel>(key));
        factory.DeleteDatabase();
    }

    [Fact]
    public async Task Send_now_posts_the_digest_to_the_webhook_through_IHttpClientFactory()
    {
        var clock = new FakeTimeProvider(DateTimeOffset.UtcNow);
        var handler = new CapturingHandler();
        await using var factory = new RequestsApiFactory(
            settings: new()
            {
                ["Notifications:Channel"] = "webhook", ["Notifications:WebhookUrl"] = WebhookUrl,
                ["Notifications:DigestEnabled"] = "false",
            },
            services: s =>
            {
                s.AddSingleton<TimeProvider>(clock);
                s.AddHttpClient<WebhookNotificationChannel>().ConfigurePrimaryHttpMessageHandler(() => handler);
            });
        var client = factory.CreateClient();
        try
        {
            await client.PostAsJsonAsync("/api/requests", NewRequest("FIN", 10_000m));
            await client.PostAsJsonAsync("/api/requests", NewRequest("FIN", 20_000m));
            clock.Advance(TimeSpan.FromDays(4));                         // default StaleAfterDays is 3
            await client.PostAsJsonAsync("/api/requests", NewRequest("IT", 5_000m));   // fresh: not in the digest

            var response = await client.PostAsync("/api/digest/send", null);

            Assert.Equal(HttpStatusCode.OK, response.StatusCode);
            var (method, uri, body) = Assert.Single(handler.Requests);
            Assert.Equal(HttpMethod.Post, method);
            Assert.Equal(WebhookUrl, uri.ToString());
            var line = Assert.Single(JsonDocument.Parse(body).RootElement.GetProperty("lines").EnumerateArray());
            Assert.Equal("FIN", line.GetProperty("department").GetString());
            Assert.Equal(2, line.GetProperty("requests").GetInt32());
            Assert.Equal(30_000m, line.GetProperty("totalBudget").GetDecimal());
        }
        finally { factory.DeleteDatabase(); }
    }

    [Fact]
    public async Task Worker_sends_the_digest_when_its_timer_fires()
    {
        var clock = new FakeTimeProvider(DateTimeOffset.UtcNow);
        var channel = new RecordingChannel();
        await using var factory = new RequestsApiFactory(services: s =>
        {
            s.AddSingleton<TimeProvider>(clock);
            s.AddKeyedSingleton<INotificationChannel>("log", channel);   // last keyed registration wins
        });
        var client = factory.CreateClient();
        try
        {
            await client.PostAsJsonAsync("/api/requests", NewRequest("OPS", 12_000m));

            clock.Advance(TimeSpan.FromDays(4));                         // exactly one tick of the 4-day timer
            await channel.WaitForDigestAsync();

            var line = Assert.Single(Assert.Single(channel.Digests).Lines);
            Assert.Equal(("OPS", 1), (line.Department, line.Requests));
        }
        finally { factory.DeleteDatabase(); }
    }

    [Fact]
    public async Task Worker_survives_a_failed_send_and_tries_again_next_tick()
    {
        var clock = new FakeTimeProvider(DateTimeOffset.UtcNow);
        var channel = new RecordingChannel(failFirst: 1);
        await using var factory = new RequestsApiFactory(services: s =>
        {
            s.AddSingleton<TimeProvider>(clock);
            s.AddKeyedSingleton<INotificationChannel>("log", channel);
        });
        var client = factory.CreateClient();
        try
        {
            await client.PostAsJsonAsync("/api/requests", NewRequest("FIN", 1_000m));

            clock.Advance(TimeSpan.FromDays(4));                         // tick 1: the channel throws
            for (var i = 0; i < 100 && channel.Attempts < 1; i++) await Task.Delay(50);
            Assert.Equal(1, channel.Attempts);
            Assert.Empty(channel.Digests);
            Assert.Equal(HttpStatusCode.OK, (await client.GetAsync("/healthz")).StatusCode);   // host still up

            clock.Advance(TimeSpan.FromDays(4));                         // tick 2: works
            await channel.WaitForDigestAsync();
            Assert.Single(channel.Digests);
        }
        finally { factory.DeleteDatabase(); }
    }

    [Fact]
    public async Task The_hosted_service_is_the_registered_singleton_and_runs_on_demand()
    {
        await using var factory = new RequestsApiFactory(settings: new() { ["Notifications:DigestEnabled"] = "false" });
        factory.CreateClient();
        try
        {
            var worker = factory.Services.GetRequiredService<DigestWorker>();
            Assert.Same(worker, factory.Services.GetServices<Microsoft.Extensions.Hosting.IHostedService>()
                .OfType<DigestWorker>().Single());                     // the hosted service IS the singleton

            var first = await worker.RunOnceAsync(CancellationToken.None);
            var second = await worker.RunOnceAsync(CancellationToken.None);
            Assert.Empty(first.Lines);                                   // nothing pending, nothing sent
            Assert.NotSame(first, second);
        }
        finally { factory.DeleteDatabase(); }
    }
}
