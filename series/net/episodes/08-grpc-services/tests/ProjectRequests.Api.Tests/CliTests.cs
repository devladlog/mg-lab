using System.Net;
using Grpc.Core;
using Grpc.Net.Client;
using ProjectRequests.Cli;
using RequestsClient = ProjectRequests.Grpc.Requests.RequestsClient;

namespace ProjectRequests.Api.Tests;

/// <summary>Episode 8: the console client's pieces, run against the real service in memory.</summary>
public sealed class CliTests : IDisposable
{
    private readonly RequestsApiFactory _factory = new();
    private static readonly TimeSpan Timeout = TimeSpan.FromSeconds(5);

    public void Dispose() { _factory.Dispose(); _factory.DeleteDatabase(); }

    private (GrpcChannel Channel, RequestsClient Client) Connect() => GrpcTestKit.Connect(_factory);

    // ---------------------------------------------------------------- CSV

    [Fact]
    public void Csv_rows_become_messages_and_bad_lines_become_errors()
    {
        var rows = CsvRows.Read([
            "title,budget,requestedBy,department,justification",
            "Badge readers,30000,alex.demo@contoso.com,OPS,",
            "",
            "\"Data platform, phase 1\",80000.50,sam.demo@contoso.com,IT,\"Replaces the \"\"old\"\" server\"",
            "Office plants,abc,jordan.demo@contoso.com,OPS,",
            "Only,three,columns",
        ]).ToList();

        Assert.Equal([2, 4, 5, 6], rows.Select(r => r.Line));
        Assert.Equal("Badge readers", rows[0].Message!.Title);
        Assert.Null(rows[0].Message!.Justification);                          // empty column = null, not ""
        Assert.Equal("Data platform, phase 1", rows[1].Message!.Title);        // quoted comma
        Assert.Equal(80_000.50m, (decimal)rows[1].Message!.Budget);
        Assert.Equal("Replaces the \"old\" server", rows[1].Message!.Justification);
        Assert.Equal("budget 'abc' is not a number", rows[2].Error);
        Assert.Equal("expected at least 4 columns, found 3", rows[3].Error);
    }

    // ---------------------------------------------------------------- the three call shapes

    [Fact]
    public async Task Get_prints_one_line_and_NotFound_is_an_RpcException()
    {
        var created = await HubTestKit.CreateAsync(_factory, "IT", 80_000m, "Data platform");
        var (channel, client) = Connect();
        using var _ = channel;
        var output = new StringWriter();

        await Commands.GetAsync(client, created.Id, Timeout, output, Ct);
        var missing = await Assert.ThrowsAsync<RpcException>(() => Commands.GetAsync(client, 999, Timeout, output, Ct));

        Assert.Contains($"#{created.Id} IT  Data platform", output.ToString());
        Assert.Contains("80,000  High     Submitted", output.ToString());
        Assert.Equal(StatusCode.NotFound, missing.StatusCode);
    }

    [Fact]
    public async Task List_prints_every_row_then_the_count()
    {
        await HubTestKit.CreateAsync(_factory, "FIN", title: "First");
        await HubTestKit.CreateAsync(_factory, "IT", title: "Second");
        var (channel, client) = Connect();
        using var _ = channel;
        var output = new StringWriter();

        var all = await Commands.ListAsync(client, null, Timeout, output, Ct);
        var fin = await Commands.ListAsync(client, "FIN", Timeout, output, Ct);

        Assert.Equal(2, all);
        Assert.Equal(1, fin);
        Assert.Contains("2 request(s)", output.ToString());
        Assert.Contains("1 request(s)", output.ToString());
    }

    [Fact]
    public async Task Import_of_the_sample_file_creates_the_good_rows_and_names_the_bad_lines()
    {
        var (channel, client) = Connect();
        using var _ = channel;
        var output = new StringWriter();

        var outcome = await Commands.ImportAsync(client, CsvRows.Read(File.ReadLines("sample-import.csv")), Timeout, output, Ct);

        var text = output.ToString();
        Assert.Equal(new ImportOutcome(Received: 6, Created: 3, Errors: 4), outcome);   // 1 line skipped by the client, 3 by the server
        Assert.Contains("line 4: skipped, budget 'abc' is not a number", text);          // never sent
        Assert.Contains("line 5: DepartmentCode: Unknown department 'XYZ'.", text);      // server row 3 -> file line 5
        Assert.Contains("line 6: Justification:", text);                                 // ERP upgrade, 300,000 with no justification
        Assert.Contains("line 7: RequestedBy:", text);                                   // not-an-email
        Assert.Contains("created 3: [1, 2, 3]", text);
    }

    // ---------------------------------------------------------------- the channel's retry policy

    /// <summary>Answers the first calls with "UNAVAILABLE" (a trailers-only gRPC response), then lets the real server answer.</summary>
    private sealed class FlakyHandler(HttpMessageHandler inner, int failures) : DelegatingHandler(inner)
    {
        public int Attempts { get; private set; }
        public List<string?> PreviousAttemptHeaders { get; } = [];

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            Attempts++;
            PreviousAttemptHeaders.Add(request.Headers.TryGetValues("grpc-previous-rpc-attempts", out var values) ? values.Single() : null);
            if (Attempts <= failures)
            {
                var response = new HttpResponseMessage(HttpStatusCode.OK) { Version = HttpVersion.Version20, Content = new ByteArrayContent([]) };
                response.Content.Headers.ContentType = new("application/grpc");
                response.Headers.Add("grpc-status", ((int)StatusCode.Unavailable).ToString());
                response.Headers.Add("grpc-message", "simulated outage");
                return response;
            }
            return await base.SendAsync(request, ct);
        }
    }

    private (GrpcChannel Channel, FlakyHandler Handler, RequestsClient Client) Flaky(int failures)
    {
        var handler = new FlakyHandler(_factory.Server.CreateHandler(), failures);
        var channel = ChannelFactory.Create(_factory.Server.BaseAddress, handler);
        return (channel, handler, new RequestsClient(channel));
    }

    [Fact]
    public async Task A_read_is_retried_on_Unavailable_and_the_server_is_told_how_many_attempts_came_before()
    {
        var created = await HubTestKit.CreateAsync(_factory);
        var (channel, handler, client) = Flaky(failures: 2);
        using var _ = channel;

        var reply = await client.GetRequestAsync(new() { Id = created.Id }, cancellationToken: Ct);

        Assert.Equal(created.Id, reply.Id);
        Assert.Equal(3, handler.Attempts);                                   // MaxAttempts 3 includes the first call
        Assert.Equal([null, "1", "2"], handler.PreviousAttemptHeaders);      // grpc-previous-rpc-attempts
    }

    [Fact]
    public async Task Retries_stop_at_MaxAttempts()
    {
        var created = await HubTestKit.CreateAsync(_factory);
        var (channel, handler, client) = Flaky(failures: 10);
        using var _ = channel;

        var ex = await Assert.ThrowsAsync<RpcException>(async () =>
            await client.GetRequestAsync(new() { Id = created.Id }, cancellationToken: Ct));

        Assert.Equal(StatusCode.Unavailable, ex.StatusCode);
        Assert.Equal(3, handler.Attempts);
    }

    [Fact]
    public async Task Import_is_never_retried_because_it_is_not_idempotent()
    {
        var (channel, handler, client) = Flaky(failures: 1);
        using var _ = channel;

        var ex = await Assert.ThrowsAsync<RpcException>(async () => await GrpcTestKit.ImportAsync(client, GrpcTestKit.NewRequest()));

        Assert.Equal(StatusCode.Unavailable, ex.StatusCode);
        Assert.Equal(1, handler.Attempts);                                   // no MethodConfig for ImportRequests
    }
}
