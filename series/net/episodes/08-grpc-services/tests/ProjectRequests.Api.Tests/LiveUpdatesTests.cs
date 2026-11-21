using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.AspNetCore.SignalR;
using Microsoft.AspNetCore.SignalR.Client;
using Microsoft.AspNetCore.TestHost;
using ProjectRequests.Feed;
using static ProjectRequests.Api.Tests.HubTestKit;

namespace ProjectRequests.Api.Tests;

/// <summary>
/// Episode 7: the hub, the groups and the client library, end to end. REST call in, SignalR message out.
/// </summary>
[Trait("Category", "Integration")]
public sealed class LiveUpdatesTests : IAsyncDisposable
{
    private readonly RequestsApiFactory _factory = new();
    private readonly List<IAsyncDisposable> _clients = [];

    public async ValueTask DisposeAsync()
    {
        foreach (var client in _clients)
            await client.DisposeAsync();
        _factory.Dispose();
        _factory.DeleteDatabase();
    }

    private async Task<(RequestsFeed Feed, Inbox<RequestDto> Created, Inbox<RequestDto> Updated)> WatchAsync(
        string? department, Func<TestServer>? server = null)
    {
        server ??= () => _factory.Server;
        var feed = new RequestsFeed(server().BaseAddress, configureHttp: Through(server), retryPolicy: new FastRetry());
        _clients.Add(feed);
        var created = new Inbox<RequestDto>();
        var updated = new Inbox<RequestDto>();
        feed.Created += created.Add;
        feed.Updated += updated.Add;
        await feed.StartAsync(department, Ct);
        return (feed, created, updated);
    }

    [Fact]
    public async Task A_new_request_is_pushed_to_a_client_watching_all_departments()
    {
        var (feed, created, _) = await WatchAsync(department: null);

        var sent = await CreateAsync(_factory, "IT", 80_000m, "Data platform");

        var pushed = await created.NextAsync();
        Assert.Equal(sent, pushed);                                         // same DTO as the REST response
        Assert.Equal(Priority.High, pushed.Priority);
        Assert.Equal(FeedState.Connected, feed.State);
    }

    /// <summary>
    /// Messages to one connection arrive in order. We create IT first, then FIN: if the FIN watcher had received
    /// the IT event, it would be the first one in its inbox.
    /// </summary>
    [Fact]
    public async Task A_department_watcher_gets_only_its_department()
    {
        var (_, finCreated, _) = await WatchAsync("fin");                  // normalized to FIN
        var (_, allCreated, _) = await WatchAsync(null);

        var it = await CreateAsync(_factory, "IT");
        var fin = await CreateAsync(_factory, "FIN");

        Assert.Equal(fin.Id, (await finCreated.NextAsync()).Id);
        Assert.Equal(it.Id, (await allCreated.NextAsync()).Id);
        Assert.Equal(fin.Id, (await allCreated.NextAsync()).Id);
    }

    [Fact]
    public async Task Switching_department_leaves_the_previous_group()
    {
        var (feed, created, _) = await WatchAsync("FIN");
        await feed.WatchAsync("OPS", Ct);

        await CreateAsync(_factory, "FIN");
        var ops = await CreateAsync(_factory, "OPS");

        Assert.Equal(ops.Id, (await created.NextAsync()).Id);
        Assert.Equal("OPS", feed.Department);
    }

    [Fact]
    public async Task A_decision_is_pushed_as_an_update()
    {
        var (_, _, updated) = await WatchAsync("FIN");
        var request = await CreateAsync(_factory, "FIN");

        var response = await _factory.CreateClient().PostAsJsonAsync($"/api/requests/{request.Id}/decision", new
        {
            approve = true, decidedBy = "sam.demo@contoso.com", version = request.Version,
        }, Ct);
        response.EnsureSuccessStatusCode();

        var pushed = await updated.NextAsync();
        Assert.Equal(RequestStatus.Approved, pushed.Status);
        Assert.Equal("sam.demo@contoso.com", pushed.DecidedBy);
        Assert.NotEqual(request.Version, pushed.Version);
    }

    [Fact]
    public async Task A_rejected_write_pushes_nothing()
    {
        var (_, _, updated) = await WatchAsync(null);
        var request = await CreateAsync(_factory, "FIN");

        var stale = await _factory.CreateClient().PostAsJsonAsync($"/api/requests/{request.Id}/decision", new
        {
            approve = true, decidedBy = "sam.demo@contoso.com", version = Guid.Empty,   // not the version we read
        }, Ct);
        Assert.Equal(System.Net.HttpStatusCode.Conflict, stale.StatusCode);
        var ok = await _factory.CreateClient().PostAsJsonAsync($"/api/requests/{request.Id}/decision", new
        {
            approve = false, decidedBy = "sam.demo@contoso.com", version = request.Version,
        }, Ct);
        ok.EnsureSuccessStatusCode();

        Assert.Equal(RequestStatus.Rejected, (await updated.NextAsync()).Status);   // the first update is the real one
    }

    /// <summary>Only a HubException's message reaches the client; any other exception becomes a generic error.</summary>
    [Fact]
    public async Task An_unknown_department_is_refused_with_the_HubException_message()
    {
        var feed = new RequestsFeed(BaseAddress(_factory), configureHttp: Through(() => _factory.Server));
        _clients.Add(feed);

        var ex = await Assert.ThrowsAsync<HubException>(() => feed.StartAsync("XYZ", Ct));

        Assert.Contains("Unknown department 'XYZ'.", ex.Message);
    }

    /// <summary>
    /// The REST API's ConfigureHttpJsonOptions doesn't apply to SignalR. AddJsonProtocol does: the payload on the
    /// wire says "High" and "Submitted", like the REST API.
    /// </summary>
    [Fact]
    public async Task Enums_travel_as_strings_on_the_wire()
    {
        var raw = RawConnection(_factory);
        _clients.Add(raw);
        var payloads = new Inbox<JsonElement>();
        raw.On<JsonElement>(nameof(IRequestsClient.RequestCreated), payloads.Add);
        await raw.StartAsync(Ct);
        await raw.InvokeAsync<string>(RequestsHubContract.Watch, null, Ct);

        await CreateAsync(_factory, "IT", 80_000m);

        var json = await payloads.NextAsync();
        Assert.Equal("High", json.GetProperty("priority").GetString());
        Assert.Equal("Submitted", json.GetProperty("status").GetString());
        Assert.Equal("IT", json.GetProperty("department").GetString());     // camelCase names, like REST
    }

    /// <summary>
    /// The gotcha, pinned: a client that binds RequestDto WITHOUT the string-enum converter can't read the message.
    /// The SignalR client logs the binding failure and drops the message; the handler never runs, the connection
    /// stays up. Nothing is thrown at the caller.
    /// </summary>
    [Fact]
    public async Task A_client_without_the_enum_converter_silently_drops_the_message()
    {
        var raw = RawConnection(_factory);                                  // default JSON protocol settings
        _clients.Add(raw);
        var typed = new Inbox<RequestDto>();
        raw.On<RequestDto>(nameof(IRequestsClient.RequestCreated), typed.Add);
        var (_, control, _) = await WatchAsync(null);                      // a correctly configured client
        await raw.StartAsync(Ct);
        await raw.InvokeAsync<string>(RequestsHubContract.Watch, null, Ct);

        var sent = await CreateAsync(_factory, "FIN");

        Assert.Equal(sent.Id, (await control.NextAsync()).Id);
        await Task.Delay(500, Ct);                                          // give the raw client the same chance
        Assert.True(typed.IsEmpty);
        Assert.Equal(HubConnectionState.Connected, raw.State);
    }

    /// <summary>
    /// Scale-out, the honest version: two instances of the API on the same database. A client connected to
    /// instance A never hears about a write handled by instance B: groups and connections live in each process.
    /// That's what a backplane (Redis) or Azure SignalR Service fixes.
    /// </summary>
    [Fact]
    public async Task A_write_handled_by_another_instance_is_not_pushed()
    {
        using var instanceB = RequestsApiFactory.ForExistingDatabase(_factory.DatabasePath);
        var (_, created, _) = await WatchAsync(null);                      // connected to instance A

        var viaB = await CreateAsync(instanceB, "FIN", title: "Written on B");
        var viaA = await CreateAsync(_factory, "FIN", title: "Written on A");

        var first = await created.NextAsync();
        Assert.Equal(viaA.Id, first.Id);                                    // B's request never arrived
        Assert.Equal(viaB.Id + 1, viaA.Id);                                 // ...even though it's in the same database
    }

    /// <summary>
    /// Restart the server: the client reconnects with a NEW connection ID, and SignalR doesn't remember its groups.
    /// RequestsFeed calls Watch again in Reconnected; a raw connection with automatic reconnect only, doesn't.
    /// </summary>
    [Fact]
    public async Task After_a_server_restart_the_feed_rejoins_its_group_and_a_raw_connection_does_not()
    {
        var current = _factory;
        RequestsApiFactory? restarted = null;
        TestServer Server() => Volatile.Read(ref current).Server;

        var (feed, feedCreated, _) = await WatchAsync("FIN", Server);
        var resubscribed = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        feed.Resubscribed += () => resubscribed.TrySetResult();
        var firstId = feed.ConnectionId;

        var raw = RawConnection(Server, reconnect: true);
        _clients.Add(raw);
        var rawCreated = new Inbox<RequestDto>();
        raw.On<JsonElement>(nameof(IRequestsClient.RequestCreated), e => rawCreated.Add(e.Deserialize<RequestDto>(RestJson)!));
        var rawReconnected = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        raw.Reconnected += _ => { rawReconnected.TrySetResult(); return Task.CompletedTask; };
        await raw.StartAsync(Ct);
        await raw.InvokeAsync<string>(RequestsHubContract.Watch, "FIN", Ct);

        try
        {
            restarted = RequestsApiFactory.ForExistingDatabase(_factory.DatabasePath);
            _ = restarted.Server;                                           // start the "new process"
            Volatile.Write(ref current, restarted);
            _factory.Dispose();                                             // stop the old one: connections drop

            await resubscribed.Task.WaitAsync(Wait, Ct);
            await rawReconnected.Task.WaitAsync(Wait, Ct);
            Assert.NotEqual(firstId, feed.ConnectionId);

            var sent = await CreateAsync(restarted, "FIN", title: "After restart");

            Assert.Equal(sent.Id, (await feedCreated.NextAsync()).Id);
            await Task.Delay(500, Ct);
            Assert.True(rawCreated.IsEmpty);                                // reconnected, but in no group
        }
        finally
        {
            foreach (var client in _clients)
                await client.DisposeAsync();
            _clients.Clear();
            restarted?.Dispose();
        }
    }
}
