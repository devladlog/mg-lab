using Grpc.Net.Client;
using ProjectRequests.Api.Live;
using ProjectRequests.Grpc;
using RequestsClient = ProjectRequests.Grpc.Requests.RequestsClient;

namespace ProjectRequests.Api.Tests;

/// <summary>Real gRPC client, real service, in memory: TestServer is a supported ASP.NET Core server for gRPC.</summary>
internal static class GrpcTestKit
{
    public static (GrpcChannel Channel, RequestsClient Client) Connect(RequestsApiFactory factory)
    {
        var http = factory.CreateDefaultClient();                    // handler of the in-memory server
        var channel = GrpcChannel.ForAddress(http.BaseAddress!, new GrpcChannelOptions { HttpClient = http });
        return (channel, new RequestsClient(channel));
    }

    public static NewRequestMessage NewRequest(string department = "FIN", decimal budget = 12_000m, string title = "Laptop refresh",
        string requestedBy = "alex.demo@contoso.com", string? justification = null) => new()
    {
        Title = title,
        Budget = budget,
        RequestedBy = requestedBy,
        DepartmentCode = department,
        Justification = justification,
    };

    public static async Task<ImportReply> ImportAsync(RequestsClient client, params NewRequestMessage[] rows)
    {
        using var call = client.ImportRequests(cancellationToken: Ct);
        foreach (var row in rows)
            await call.RequestStream.WriteAsync(row, Ct);
        await call.RequestStream.CompleteAsync();
        return await call.ResponseAsync;
    }
}

/// <summary>Records what the service told the outside world; optionally misbehaves.</summary>
internal sealed class RecordingEvents : IRequestEvents
{
    public List<RequestDto> Created { get; } = [];
    public Func<CancellationToken, Task>? OnCreated { get; init; }

    public async Task CreatedAsync(RequestDto request, CancellationToken ct)
    {
        Created.Add(request);
        if (OnCreated is not null)
            await OnCreated(ct);
    }

    public Task UpdatedAsync(RequestDto request, CancellationToken ct) => Task.CompletedTask;
}
