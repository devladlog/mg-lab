using Contoso.Requests.Service.Budget;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Data.Sqlite;
using Microsoft.Extensions.DependencyInjection;
using Yarp.ReverseProxy.Forwarder;

namespace Contoso.Microservices.Tests;

/// <summary>The "wire" between two services in the tests: counts every attempt and can pretend the other side is down.</summary>
public sealed class Wire(HttpMessageHandler inner) : DelegatingHandler(inner)
{
    private int _attempts;
    public int Attempts => _attempts;
    public volatile bool Down;

    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
    {
        Interlocked.Increment(ref _attempts);
        if (Down) throw new HttpRequestException("Connection refused (test: the service is down)");
        return base.SendAsync(request, ct);
    }
}

/// <summary>Maps the port a service-discovered address resolved to onto the in-memory server behind it.</summary>
public sealed class PortRouter : HttpMessageHandler
{
    private readonly Dictionary<int, HttpMessageHandler> _servers = new();
    public HashSet<int> Down { get; } = [];

    public PortRouter Add(int port, HttpMessageHandler server) { _servers[port] = server; return this; }

    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
    {
        var port = request.RequestUri!.Port;
        if (Down.Contains(port) || !_servers.TryGetValue(port, out var server))
            throw new HttpRequestException($"Connection refused (test: nothing listens on {request.RequestUri.Authority})");
        var invoker = new HttpMessageInvoker(server, disposeHandler: false);
        return invoker.SendAsync(request, ct);
    }
}

/// <summary>YARP calls its destinations through this instead of a real socket.</summary>
public sealed class InMemoryForwarderClients(HttpMessageHandler handler) : IForwarderHttpClientFactory
{
    public HttpMessageInvoker CreateClient(ForwarderHttpClientContext context) => new(handler, disposeHandler: false);
}

/// <summary>A real Budget service and a real Requests service, in memory, with the Budget HttpClient pointed at the Budget service.</summary>
public sealed class Lab : IDisposable
{
    private readonly string _db = Path.Combine(Path.GetTempPath(), $"requests-{Guid.NewGuid():N}.db");

    public WebApplicationFactory<BudgetServiceMarker> Budget { get; }
    public WebApplicationFactory<RequestsServiceMarker> Requests { get; }
    public Wire BudgetWire { get; }
    public HttpClient BudgetHttp { get; }
    public HttpClient RequestsHttp { get; }

    public Lab(int failFirstAttempts = 0, bool failAfterCommit = false, int breakerMinimumThroughput = 5, int breakSeconds = 15)
    {
        Budget = new WebApplicationFactory<BudgetServiceMarker>().WithWebHostBuilder(b =>
        {
            b.UseSetting("Faults:FailFirstAttemptsPerKey", failFirstAttempts.ToString());
            b.UseSetting("Faults:FailAfterCommit", failAfterCommit.ToString());
        });
        BudgetHttp = Budget.CreateClient();
        BudgetWire = new Wire(Budget.Server.CreateHandler());

        Requests = new WebApplicationFactory<RequestsServiceMarker>().WithWebHostBuilder(b =>
        {
            b.UseSetting("ConnectionStrings:Requests", $"Data Source={_db}");
            b.UseSetting("Recheck:IntervalSeconds", "0");                 // the tests call the re-check themselves
            b.UseSetting("Resilience:RetryDelayMs", "1");                 // real retries, just not slow ones
            b.UseSetting("Resilience:BreakerMinimumThroughput", breakerMinimumThroughput.ToString());
            b.UseSetting("Resilience:BreakDurationSeconds", breakSeconds.ToString());
            b.UseSetting("Services:budget:http:0", "budget.test:80");
            b.ConfigureTestServices(s => s.AddHttpClient<BudgetClient>().ConfigurePrimaryHttpMessageHandler(() => BudgetWire));
        });
        RequestsHttp = Requests.CreateClient();
    }

    public static object NewRequest(string department = "FIN", decimal amount = 12_000m, string title = "Standing desks") =>
        new { title, departmentCode = department, amount, requestedBy = "alex.demo@contoso.com" };

    public void Dispose()
    {
        RequestsHttp.Dispose(); BudgetHttp.Dispose(); Requests.Dispose(); Budget.Dispose();
        SqliteConnection.ClearAllPools();
        foreach (var f in Directory.GetFiles(Path.GetTempPath(), Path.GetFileName(_db) + "*")) File.Delete(f);
    }
}
