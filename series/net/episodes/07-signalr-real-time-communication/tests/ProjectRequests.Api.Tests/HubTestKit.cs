using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading.Channels;
using Microsoft.AspNetCore.Http.Connections.Client;
using Microsoft.AspNetCore.SignalR.Client;
using Microsoft.AspNetCore.TestHost;

namespace ProjectRequests.Api.Tests;

/// <summary>
/// Real SignalR clients against the in-memory app: negotiate goes through TestServer's handler, the WebSocket
/// through TestServer's WebSocket client. Same hub, same protocol, same groups as on Kestrel.
/// </summary>
internal static class HubTestKit
{
    public static readonly TimeSpan Wait = TimeSpan.FromSeconds(10);

    /// <summary>The server is looked up on every (re)connect, so a test can swap it to simulate a restart.</summary>
    public static Action<HttpConnectionOptions> Through(Func<TestServer> server) => o =>
    {
        o.HttpMessageHandlerFactory = _ => server().CreateHandler();
        o.WebSocketFactory = async (context, ct) => await server().CreateWebSocketClient().ConnectAsync(context.Uri, ct);
    };

    public static Uri BaseAddress(RequestsApiFactory factory) => factory.Server.BaseAddress;

    /// <summary>A plain HubConnection (no RequestsFeed), default protocol settings unless told otherwise.</summary>
    public static HubConnection RawConnection(RequestsApiFactory factory, bool reconnect = false) =>
        RawConnection(() => factory.Server, reconnect);

    public static HubConnection RawConnection(Func<TestServer> server, bool reconnect = false)
    {
        var builder = new HubConnectionBuilder().WithUrl(new Uri(server().BaseAddress, RequestsHubContract.Path), Through(server));
        if (reconnect)
            builder.WithAutomaticReconnect(new FastRetry());
        return builder.Build();
    }

    public static async Task<RequestDto> CreateAsync(RequestsApiFactory factory, string department = "FIN", decimal budget = 12_000m,
        string title = "Laptop refresh")
    {
        var response = await factory.CreateClient().PostAsJsonAsync("/api/requests", new
        {
            title, budget, requestedBy = "alex.demo@contoso.com", departmentCode = department,
        }, Ct);
        response.EnsureSuccessStatusCode();
        return (await response.Content.ReadFromJsonAsync<RequestDto>(RestJson, Ct))!;
    }

    public static readonly JsonSerializerOptions RestJson = new(JsonSerializerDefaults.Web)
    {
        Converters = { new JsonStringEnumConverter() },
    };

    /// <summary>Reconnect quickly in tests: every 100 ms, for up to 10 s.</summary>
    public sealed class FastRetry : IRetryPolicy
    {
        public TimeSpan? NextRetryDelay(RetryContext retryContext) =>
            retryContext.ElapsedTime < TimeSpan.FromSeconds(10) ? TimeSpan.FromMilliseconds(100) : null;
    }
}

/// <summary>Collects pushed items; NextAsync waits for the next one (or fails the test after a timeout).</summary>
internal sealed class Inbox<T>
{
    private readonly Channel<T> _items = Channel.CreateUnbounded<T>();

    public void Add(T item) => _items.Writer.TryWrite(item);

    public async Task<T> NextAsync()
    {
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(Ct);
        timeout.CancelAfter(HubTestKit.Wait);
        return await _items.Reader.ReadAsync(timeout.Token);
    }

    public bool IsEmpty => !_items.Reader.TryPeek(out _);
}
