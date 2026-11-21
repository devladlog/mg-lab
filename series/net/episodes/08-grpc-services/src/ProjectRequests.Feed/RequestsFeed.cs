using System.Text.Json.Serialization;
using Microsoft.AspNetCore.Http.Connections.Client;
using Microsoft.AspNetCore.SignalR.Client;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using ProjectRequests.Contracts;

namespace ProjectRequests.Feed;

public enum FeedState { Disconnected, Connecting, Connected, Reconnecting }

/// <summary>Live request events, as the UI and the watcher see them.</summary>
public interface IRequestsFeed : IAsyncDisposable
{
    FeedState State { get; }

    /// <summary>The department being watched (null = all), re-sent to the server after every reconnect.</summary>
    string? Department { get; }

    event Action<RequestDto>? Created;
    event Action<RequestDto>? Updated;
    event Action<FeedState>? StateChanged;

    /// <summary>
    /// Raised after an automatic reconnect, once the group was joined again. Events sent while we were away are
    /// lost (SignalR doesn't queue them for us): reload what you show.
    /// </summary>
    event Action? Resubscribed;

    Task StartAsync(string? department, CancellationToken ct = default);
    Task WatchAsync(string? department, CancellationToken ct = default);
}

/// <summary>
/// One HubConnection to the API's hub, with automatic reconnect (0, 2, 10, 30 s by default) and the part
/// WithAutomaticReconnect does NOT do: a reconnect is a NEW connection (new connection ID), and group membership
/// isn't preserved, so we call Watch again in the Reconnected handler.
/// </summary>
public sealed class RequestsFeed : IRequestsFeed
{
    private readonly HubConnection _connection;

    public RequestsFeed(
        Uri apiBaseAddress,
        ILoggerFactory? loggerFactory = null,
        Action<HttpConnectionOptions>? configureHttp = null,
        IRetryPolicy? retryPolicy = null)
    {
        var builder = new HubConnectionBuilder()
            .WithUrl(new Uri(apiBaseAddress, RequestsHubContract.Path), o => configureHttp?.Invoke(o))
            // The server sends enums as strings (AddJsonProtocol on the API): the client must agree.
            .AddJsonProtocol(o => o.PayloadSerializerOptions.Converters.Add(new JsonStringEnumConverter()));
        builder = retryPolicy is null ? builder.WithAutomaticReconnect() : builder.WithAutomaticReconnect(retryPolicy);
        if (loggerFactory is not null)
            builder.Services.AddSingleton(loggerFactory);
        _connection = builder.Build();

        // Register handlers BEFORE StartAsync, or the first messages have nobody to go to.
        _connection.On<RequestDto>(nameof(IRequestsClient.RequestCreated), r => Created?.Invoke(r));
        _connection.On<RequestDto>(nameof(IRequestsClient.RequestUpdated), r => Updated?.Invoke(r));

        _connection.Reconnecting += _ => SetState(FeedState.Reconnecting);
        _connection.Reconnected += async _ =>
        {
            await _connection.InvokeAsync<string>(RequestsHubContract.Watch, Department);   // join the group again
            await SetState(FeedState.Connected);
            Resubscribed?.Invoke();
        };
        _connection.Closed += _ => SetState(FeedState.Disconnected);   // after the last retry, or StopAsync
    }

    public FeedState State { get; private set; }
    public string? Department { get; private set; }
    public string? ConnectionId => _connection.ConnectionId;

    public event Action<RequestDto>? Created;
    public event Action<RequestDto>? Updated;
    public event Action<FeedState>? StateChanged;
    public event Action? Resubscribed;

    /// <summary>
    /// WithAutomaticReconnect doesn't retry a failed FIRST start: the caller decides (the watcher retries,
    /// the board shows the error).
    /// </summary>
    public async Task StartAsync(string? department, CancellationToken ct = default)
    {
        await SetState(FeedState.Connecting);
        try
        {
            await _connection.StartAsync(ct);
            await WatchAsync(department, ct);
            await SetState(FeedState.Connected);
        }
        catch
        {
            await SetState(FeedState.Disconnected);
            throw;
        }
    }

    public async Task WatchAsync(string? department, CancellationToken ct = default)
    {
        var normalized = string.IsNullOrWhiteSpace(department) ? null : department.Trim().ToUpperInvariant();
        await _connection.InvokeAsync<string>(RequestsHubContract.Watch, normalized, ct);   // HubException if unknown
        Department = normalized;
    }

    private Task SetState(FeedState state)
    {
        State = state;
        StateChanged?.Invoke(state);
        return Task.CompletedTask;
    }

    public ValueTask DisposeAsync() => _connection.DisposeAsync();
}

/// <summary>
/// Pages create their own feed when they become interactive and dispose it when they go away, so the DI container
/// hands out a factory, not a connection.
/// </summary>
public interface IRequestsFeedFactory
{
    IRequestsFeed Create();
}

public sealed class RequestsFeedFactory(Uri apiBaseAddress, ILoggerFactory? loggerFactory = null) : IRequestsFeedFactory
{
    public IRequestsFeed Create() => new RequestsFeed(apiBaseAddress, loggerFactory);
}
