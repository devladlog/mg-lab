using System.Net.Http.Json;
using Grpc.Core;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using ProjectRequests.Api.Live;
using ProjectRequests.Grpc;
using RequestsClient = ProjectRequests.Grpc.Requests.RequestsClient;
using static ProjectRequests.Api.Tests.GrpcTestKit;

namespace ProjectRequests.Api.Tests;

/// <summary>Episode 8: the gRPC front door, against the real service and the real SQLite database.</summary>
public sealed class GrpcServiceTests : IDisposable
{
    private readonly RequestsApiFactory _factory = new();

    public void Dispose() { _factory.Dispose(); _factory.DeleteDatabase(); }

    // ---------------------------------------------------------------- unary

    [Fact]
    public async Task Unary_call_returns_what_REST_created_with_every_field_mapped()
    {
        var sent = await HubTestKit.CreateAsync(_factory, "IT", 80_000m, "Data platform");   // created through REST
        var (channel, client) = Connect(_factory);
        using var _ = channel;

        var reply = await client.GetRequestAsync(new GetRequestMessage { Id = sent.Id }, cancellationToken: Ct);

        Assert.Equal(sent.Id, reply.Id);
        Assert.Equal("Data platform", reply.Title);
        Assert.Equal("IT", reply.Department);
        Assert.Equal("alex.demo@contoso.com", reply.RequestedBy);
        Assert.Equal(80_000m, (decimal)reply.Budget);
        Assert.Equal(ProjectRequests.Grpc.Priority.High, reply.Priority);
        Assert.Equal(ProjectRequests.Grpc.RequestStatus.Submitted, reply.Status);
        Assert.Equal(sent.CreatedAtUtc, reply.CreatedAt.ToDateTime());
        Assert.Equal(sent.Version.ToString(), reply.Version);
    }

    [Fact]
    public async Task Missing_optional_values_arrive_as_null_not_as_empty_strings()
    {
        var sent = await HubTestKit.CreateAsync(_factory);          // no justification, not decided
        var (channel, client) = Connect(_factory);
        using var _ = channel;

        var reply = await client.GetRequestAsync(new GetRequestMessage { Id = sent.Id }, cancellationToken: Ct);

        Assert.Null(reply.Justification);                            // google.protobuf.StringValue wrapper
        Assert.Null(reply.DecidedBy);
        Assert.Null(reply.DecidedAt);                                // message-typed field: null until set
    }

    [Fact]
    public async Task Unknown_id_is_a_NotFound_status_not_an_HTTP_404()
    {
        var (channel, client) = Connect(_factory);
        using var _ = channel;

        var ex = await Assert.ThrowsAsync<RpcException>(async () =>
            await client.GetRequestAsync(new GetRequestMessage { Id = 999 }, cancellationToken: Ct));

        Assert.Equal(StatusCode.NotFound, ex.StatusCode);
        Assert.Equal("Request 999 not found.", ex.Status.Detail);
    }

    [Fact]
    public async Task Invalid_id_is_InvalidArgument()
    {
        var (channel, client) = Connect(_factory);
        using var _ = channel;

        var ex = await Assert.ThrowsAsync<RpcException>(async () =>
            await client.GetRequestAsync(new GetRequestMessage { Id = 0 }, cancellationToken: Ct));   // 0 is also what an unset int32 reads as

        Assert.Equal(StatusCode.InvalidArgument, ex.StatusCode);
    }

    // ---------------------------------------------------------------- server streaming

    [Fact]
    public async Task Server_streaming_sends_one_message_per_request_in_order()
    {
        await HubTestKit.CreateAsync(_factory, "FIN", title: "First");
        await HubTestKit.CreateAsync(_factory, "IT", title: "Second");
        await HubTestKit.CreateAsync(_factory, "FIN", title: "Third");
        var (channel, client) = Connect(_factory);
        using var _ = channel;

        using var call = client.ListRequests(new ListRequestsMessage(), cancellationToken: Ct);
        var titles = new List<string>();
        await foreach (var reply in call.ResponseStream.ReadAllAsync(Ct))
            titles.Add(reply.Title);

        Assert.Equal(["First", "Second", "Third"], titles);
    }

    [Theory]
    [InlineData("FIN", 2)]
    [InlineData("fin", 2)]          // codes compare case-insensitively, same as the REST filter
    [InlineData("IT", 1)]
    [InlineData("OPS", 0)]
    [InlineData("", 3)]             // an unset string field is "" = all departments
    public async Task Server_streaming_filters_by_department(string department, int expected)
    {
        await HubTestKit.CreateAsync(_factory, "FIN", title: "First");
        await HubTestKit.CreateAsync(_factory, "IT", title: "Second");
        await HubTestKit.CreateAsync(_factory, "FIN", title: "Third");
        var (channel, client) = Connect(_factory);
        using var _ = channel;

        using var call = client.ListRequests(new ListRequestsMessage { Department = department }, cancellationToken: Ct);
        var received = 0;
        await foreach (var _r in call.ResponseStream.ReadAllAsync(Ct))
            received++;

        Assert.Equal(expected, received);
    }

    [Fact]
    public async Task A_cancelled_stream_surfaces_as_Cancelled_on_the_client()
    {
        for (var i = 0; i < 3; i++)
            await HubTestKit.CreateAsync(_factory, title: $"Row {i}");
        var (channel, client) = Connect(_factory);
        using var _ = channel;

        using var cts = CancellationTokenSource.CreateLinkedTokenSource(Ct);
        using var call = client.ListRequests(new ListRequestsMessage(), cancellationToken: cts.Token);
        Assert.True(await call.ResponseStream.MoveNext(cts.Token));  // first message is here...
        await cts.CancelAsync();                                    // ...the caller loses interest

        var ex = await Assert.ThrowsAnyAsync<Exception>(async () =>
        {
            while (await call.ResponseStream.MoveNext(cts.Token)) { }
        });
        Assert.True(ex is OperationCanceledException || ex is RpcException { StatusCode: StatusCode.Cancelled }, ex.ToString());
    }

    // ---------------------------------------------------------------- client streaming

    [Fact]
    public async Task Client_streaming_creates_every_valid_row_and_answers_once()
    {
        var (channel, client) = Connect(_factory);
        using var _ = channel;

        var reply = await ImportAsync(client,
            NewRequest("FIN", 12_000m, "Laptop refresh"),
            NewRequest("IT", 80_000m, "Data platform"),
            NewRequest("OPS", 30_000m, "Badge readers"));

        Assert.Equal(3, reply.Received);
        Assert.Equal(3, reply.CreatedIds.Count);
        Assert.Empty(reply.Errors);

        using var list = client.ListRequests(new ListRequestsMessage(), cancellationToken: Ct);
        var titles = new List<string>();
        await foreach (var r in list.ResponseStream.ReadAllAsync(Ct))
            titles.Add(r.Title);
        Assert.Equal(["Laptop refresh", "Data platform", "Badge readers"], titles);
    }

    [Fact]
    public async Task Bad_rows_are_reported_with_their_position_and_do_not_stop_the_import()
    {
        var (channel, client) = Connect(_factory);
        using var _ = channel;

        var reply = await ImportAsync(client,
            NewRequest(title: "Fine"),                                          // 1: ok
            NewRequest(title: "No", budget: 0m),                                // 2: title too short + budget out of range
            NewRequest(department: "XYZ", title: "Unknown department"),         // 3: database check
            NewRequest(requestedBy: "not-an-email", title: "Bad email"),        // 4
            NewRequest(budget: 300_000m, title: "Big, no justification"),       // 5: IValidatableObject rule
            NewRequest(title: "Also fine"));                                    // 6: ok

        Assert.Equal(6, reply.Received);
        Assert.Equal(2, reply.CreatedIds.Count);
        Assert.Equal([2, 3, 4, 5], reply.Errors.Select(e => e.Row).Distinct().Order());
        Assert.Contains(reply.Errors, e => e.Row == 3 && e.Field == "DepartmentCode" && e.Message == "Unknown department 'XYZ'.");
        Assert.Contains(reply.Errors, e => e.Row == 4 && e.Field == "RequestedBy");
        Assert.Contains(reply.Errors, e => e.Row == 5 && e.Field == "Justification");
    }

    [Fact]
    public async Task The_same_rules_apply_over_REST_and_gRPC()
    {
        // What REST rejects with a 400, gRPC reports in ImportReply.Errors: same input model, same attributes.
        var rest = await _factory.CreateClient().PostAsJsonAsync("/api/requests", new
        {
            title = "No", budget = 0, requestedBy = "alex.demo@contoso.com", departmentCode = "FIN",
        }, Ct);
        var (channel, client) = Connect(_factory);
        using var _ = channel;
        var grpc = await ImportAsync(client, NewRequest(title: "No", budget: 0m));

        Assert.Equal(System.Net.HttpStatusCode.BadRequest, rest.StatusCode);
        Assert.Empty(grpc.CreatedIds);
        var restFields = (await rest.Content.ReadFromJsonAsync<System.Text.Json.JsonElement>(Ct)).GetProperty("errors")
            .EnumerateObject().Select(p => p.Name).Order().ToArray();
        Assert.Equal(restFields, grpc.Errors.Select(e => e.Field).Distinct().Order().ToArray());
    }

    [Fact]
    public async Task Imported_requests_are_pushed_to_the_live_board_like_REST_ones()
    {
        // Episode 7's SignalR push is reached through the same creation code.
        var events = new RecordingEvents();
        using var factory = new RequestsApiFactory(services: s => s.Replace(ServiceDescriptor.Singleton<IRequestEvents>(events)));
        var (channel, client) = Connect(factory);
        using var _ = channel;

        var reply = await ImportAsync(client, NewRequest("FIN", 12_000m, "Laptop refresh"), NewRequest("IT", 80_000m, "Data platform"));

        Assert.Equal(["Laptop refresh", "Data platform"], events.Created.Select(r => r.Title));
        Assert.Equal(reply.CreatedIds, events.Created.Select(r => r.Id));
        factory.DeleteDatabase();
    }

    [Fact]
    public async Task Decimal_budgets_survive_the_wire_without_rounding()
    {
        var (channel, client) = Connect(_factory);
        using var _ = channel;

        var reply = await ImportAsync(client, NewRequest(budget: 12_345.67m, title: "Precise"));
        var stored = await client.GetRequestAsync(new GetRequestMessage { Id = reply.CreatedIds[0] }, cancellationToken: Ct);

        Assert.Equal(12_345.67m, (decimal)stored.Budget);
        Assert.Equal(12_345, stored.Budget.Units);
        Assert.Equal(670_000_000, stored.Budget.Nanos);
    }

    // ---------------------------------------------------------------- deadlines and cancellation

    [Fact]
    public async Task A_deadline_stops_the_client_and_cancels_the_token_the_server_received()
    {
        var serverToken = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        var slow = new RecordingEvents
        {
            OnCreated = async ct =>
            {
                ct.Register(() => serverToken.TrySetResult(true));            // ServerCallContext.CancellationToken fired
                await Task.Delay(TimeSpan.FromSeconds(2), CancellationToken.None);   // work that ignores it: runs on regardless
            },
        };
        using var factory = new RequestsApiFactory(services: s => s.Replace(ServiceDescriptor.Singleton<IRequestEvents>(slow)));
        var (channel, client) = Connect(factory);
        using var _ = channel;

        using var call = client.ImportRequests(deadline: DateTime.UtcNow.AddMilliseconds(500), cancellationToken: Ct);
        await call.RequestStream.WriteAsync(NewRequest(), Ct);
        await call.RequestStream.CompleteAsync();

        var ex = await Assert.ThrowsAsync<RpcException>(async () => await call.ResponseAsync);

        Assert.Equal(StatusCode.DeadlineExceeded, ex.StatusCode);          // client side, after ~0.5 s, not after 2 s
        Assert.True(await serverToken.Task.WaitAsync(HubTestKit.Wait, Ct), "the service's token must be cancelled too");
        factory.DeleteDatabase();
    }

    [Fact]
    public async Task A_deadline_in_the_past_fails_immediately()
    {
        var (channel, client) = Connect(_factory);
        using var _ = channel;

        var ex = await Assert.ThrowsAsync<RpcException>(async () =>
            await client.GetRequestAsync(new GetRequestMessage { Id = 1 }, deadline: DateTime.UtcNow.AddSeconds(-1), cancellationToken: Ct));

        Assert.Equal(StatusCode.DeadlineExceeded, ex.StatusCode);
    }

    // ---------------------------------------------------------------- unhandled exceptions

    private static RecordingEvents Exploding() => new() { OnCreated = _ => throw new InvalidOperationException("push exploded: secret detail") };

    [Fact]
    public async Task An_unhandled_exception_is_Unknown_with_a_generic_message_in_production()
    {
        using var factory = new RequestsApiFactory(environment: "Production",
            services: s => s.Replace(ServiceDescriptor.Singleton<IRequestEvents>(Exploding())));
        var (channel, client) = Connect(factory);
        using var _ = channel;

        var ex = await Assert.ThrowsAsync<RpcException>(async () => await ImportAsync(client, NewRequest()));

        Assert.Equal(StatusCode.Unknown, ex.StatusCode);
        Assert.DoesNotContain("secret detail", ex.Status.Detail);
        factory.DeleteDatabase();
    }

    [Fact]
    public async Task EnableDetailedErrors_puts_the_exception_message_on_the_wire_in_development()
    {
        using var factory = new RequestsApiFactory(environment: "Development",
            services: s => s.Replace(ServiceDescriptor.Singleton<IRequestEvents>(Exploding())));
        var (channel, client) = Connect(factory);
        using var _ = channel;

        var ex = await Assert.ThrowsAsync<RpcException>(async () => await ImportAsync(client, NewRequest()));

        Assert.Equal(StatusCode.Unknown, ex.StatusCode);
        Assert.Contains("push exploded: secret detail", ex.Status.Detail);
        factory.DeleteDatabase();
    }
}
