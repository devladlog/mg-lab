using System.Collections.Concurrent;
using System.Text.Json;
using Azure;
using Azure.Storage.Blobs;
using Microsoft.Extensions.Options;

namespace Contoso.Orders.Api.Orders;

public interface IOrderStore
{
    Task SaveAsync(StoredOrder order, CancellationToken ct);
    Task<StoredOrder?> FindAsync(string orderId, CancellationToken ct);
}

/// <summary>
/// Blob storage with a managed identity (no keys). The Azure SDK calls show up as dependencies
/// in Application Insights because the distro turns on Azure SDK instrumentation.
/// </summary>
public sealed class BlobOrderStore(BlobContainerClient container) : IOrderStore
{
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);

    public async Task SaveAsync(StoredOrder order, CancellationToken ct) =>
        await container.GetBlobClient($"{order.OrderId}.json")
            .UploadAsync(BinaryData.FromObjectAsJson(order, Json), overwrite: true, ct);

    public async Task<StoredOrder?> FindAsync(string orderId, CancellationToken ct)
    {
        try
        {
            var blob = await container.GetBlobClient($"{orderId}.json").DownloadContentAsync(ct);
            return blob.Value.Content.ToObjectFromJson<StoredOrder>(Json);
        }
        catch (RequestFailedException e) when (e.Status == 404)
        {
            return null; // the dependency call is recorded as failed (404); the API answers 404
        }
    }
}

/// <summary>Local runs and tests: no storage account needed.</summary>
public sealed class InMemoryOrderStore : IOrderStore
{
    private readonly ConcurrentDictionary<string, StoredOrder> orders = new();

    public Task SaveAsync(StoredOrder order, CancellationToken ct)
    {
        orders[order.OrderId] = order;
        return Task.CompletedTask;
    }

    public Task<StoredOrder?> FindAsync(string orderId, CancellationToken ct) =>
        Task.FromResult(orders.TryGetValue(orderId, out var o) ? o : null);
}

/// <summary>App settings Chaos__FailurePercent and Chaos__ExtraLatencyMs. Both 0 by default.</summary>
public sealed class ChaosOptions
{
    public int FailurePercent { get; set; }
    public int ExtraLatencyMs { get; set; }
}

public sealed class InjectedFaultException(int percent)
    : Exception($"Injected fault (Chaos:FailurePercent={percent}).");

/// <summary>Returns 0..99. Replaced in tests so the outcome is deterministic.</summary>
public interface IFaultDice
{
    int Roll();
}

public sealed class RandomFaultDice : IFaultDice
{
    public int Roll() => Random.Shared.Next(100);
}

/// <summary>
/// Fault injection for the demo: makes a share of saves fail (HTTP 500) or slow, so the failure
/// alert and the slow-operation query have something real to find. Off unless configured.
/// </summary>
public sealed class ChaosOrderStore(IOrderStore inner, IOptionsMonitor<ChaosOptions> options, IFaultDice dice)
    : IOrderStore
{
    public async Task SaveAsync(StoredOrder order, CancellationToken ct)
    {
        var chaos = options.CurrentValue;
        if (chaos.ExtraLatencyMs > 0)
            await Task.Delay(chaos.ExtraLatencyMs, ct);
        if (chaos.FailurePercent > 0 && dice.Roll() < chaos.FailurePercent)
            throw new InjectedFaultException(chaos.FailurePercent);
        await inner.SaveAsync(order, ct);
    }

    public Task<StoredOrder?> FindAsync(string orderId, CancellationToken ct) => inner.FindAsync(orderId, ct);
}
