using System.Diagnostics;
using Contoso.Orders.Api.Orders;
using Contoso.Orders.Api.Telemetry;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Options;

namespace Contoso.Orders.Api.Tests;

public class ExpectedClientErrorProcessorTests
{
    private static Activity Span(ActivityKind kind, int status, ActivityStatusCode initial = ActivityStatusCode.Unset)
    {
        var a = new Activity("test");
        a.SetIdFormat(ActivityIdFormat.W3C);
        a.Start();
        a.Stop();
        typeof(Activity).GetProperty(nameof(Activity.Kind))!.SetValue(a, kind);
        a.SetTag("http.response.status_code", status);
        if (initial != ActivityStatusCode.Unset) a.SetStatus(initial);
        return a;
    }

    [Theory]
    [InlineData(400)]
    [InlineData(404)]
    [InlineData(422)]
    public void Expected_client_errors_become_successful(int status)
    {
        var span = Span(ActivityKind.Server, status);
        new ExpectedClientErrorProcessor().OnEnd(span);
        Assert.Equal(ActivityStatusCode.Ok, span.Status);
    }

    [Theory]
    [InlineData(401)]
    [InlineData(403)]
    [InlineData(409)]
    [InlineData(429)]
    [InlineData(500)]
    public void Other_codes_are_left_alone(int status)
    {
        var span = Span(ActivityKind.Server, status);
        new ExpectedClientErrorProcessor().OnEnd(span);
        Assert.Equal(ActivityStatusCode.Unset, span.Status);
    }

    [Fact]
    public void Outgoing_calls_and_explicit_errors_are_not_touched()
    {
        var client = Span(ActivityKind.Client, 404);           // a 404 from storage stays a failed dependency
        var explicitError = Span(ActivityKind.Server, 400, ActivityStatusCode.Error);
        var processor = new ExpectedClientErrorProcessor();
        processor.OnEnd(client);
        processor.OnEnd(explicitError);
        Assert.Equal(ActivityStatusCode.Unset, client.Status);
        Assert.Equal(ActivityStatusCode.Error, explicitError.Status);
    }
}

public class SamplingSettingsTests
{
    private static SamplingSettings Read(params (string Key, string Value)[] values) =>
        new ConfigurationBuilder()
            .AddInMemoryCollection(values.Select(v => new KeyValuePair<string, string?>($"Telemetry:{v.Key}", v.Value)))
            .Build().GetSection("Telemetry").Get<SamplingSettings>() ?? new SamplingSettings();

    [Fact]
    public void Rate_limited_or_fixed_ratio_are_valid()
    {
        Read(("TracesPerSecond", "1.5")).Validate();
        Read(("SamplingRatio", "0.1")).Validate();
        Read().Validate(); // nothing set: the distro default (5 traces per second)
    }

    [Theory]
    [InlineData("SamplingRatio", "1.5")]
    [InlineData("SamplingRatio", "-0.1")]
    [InlineData("TracesPerSecond", "-1")]
    public void Out_of_range_values_fail_at_startup(string key, string value) =>
        Assert.Throws<InvalidOperationException>(() => Read((key, value)).Validate());

    [Fact]
    public void Both_strategies_at_once_is_rejected() =>
        Assert.Throws<InvalidOperationException>(() =>
            Read(("TracesPerSecond", "5"), ("SamplingRatio", "0.5")).Validate());
}

public class ChaosOrderStoreTests
{
    private sealed class Dice(int roll) : IFaultDice { public int Roll() => roll; }

    private static StoredOrder AnOrder() => new("o1", "c1", "web", [], 0m, DateTimeOffset.UnixEpoch);

    private static ChaosOrderStore Store(int percent, int roll, InMemoryOrderStore inner) =>
        new(inner, new StaticOptions(new ChaosOptions { FailurePercent = percent }), new Dice(roll));

    [Fact]
    public async Task Roll_below_the_percentage_fails_and_nothing_is_saved()
    {
        var inner = new InMemoryOrderStore();
        await Assert.ThrowsAsync<InjectedFaultException>(() => Store(20, 19, inner).SaveAsync(AnOrder(), default));
        Assert.Null(await inner.FindAsync("o1", default));
    }

    [Theory]
    [InlineData(20, 20)]
    [InlineData(0, 0)]
    public async Task Otherwise_the_order_is_saved(int percent, int roll)
    {
        var inner = new InMemoryOrderStore();
        await Store(percent, roll, inner).SaveAsync(AnOrder(), default);
        Assert.NotNull(await inner.FindAsync("o1", default));
    }

    private sealed class StaticOptions(ChaosOptions value) : IOptionsMonitor<ChaosOptions>
    {
        public ChaosOptions CurrentValue => value;
        public ChaosOptions Get(string? name) => value;
        public IDisposable? OnChange(Action<ChaosOptions, string?> listener) => null;
    }
}
