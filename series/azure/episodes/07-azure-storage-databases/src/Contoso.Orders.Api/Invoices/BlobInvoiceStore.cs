using System.Text.Json;
using Azure.Storage.Blobs;
using Azure.Storage.Blobs.Models;
using Azure.Storage.Sas;
using Contoso.Orders.Api.Orders;

namespace Contoso.Orders.Api.Invoices;

public interface IInvoiceStore
{
    /// <summary>Writes the invoice document. Named after the order id, so a retry overwrites instead of duplicating.</summary>
    Task SaveAsync(Order order, CancellationToken ct);

    /// <summary>Short-lived, read-only HTTPS link to one invoice (user delegation SAS).</summary>
    Task<InvoiceLink> GetReadLinkAsync(Order order, TimeSpan lifetime, CancellationToken ct);
}

public sealed record InvoiceLink(Uri Url, DateTimeOffset ExpiresOn);

public sealed class InvoiceOptions
{
    /// <summary>https://&lt;account&gt;.blob.core.windows.net (Bicep output). No keys, no connection string.</summary>
    public string? BlobServiceUri { get; set; }
    public string Container { get; set; } = "invoices";
}

/// <summary>
/// Invoices in Blob Storage with shared keys disabled. Downloads go through a user delegation SAS:
/// signed with a key that Storage hands out to an Entra identity (role with
/// generateUserDelegationKey, e.g. Storage Blob Data Contributor), valid at most seven days.
/// </summary>
public sealed class BlobInvoiceStore(BlobServiceClient service, string containerName, TimeProvider time) : IInvoiceStore
{
    public static readonly TimeSpan MaxLinkLifetime = TimeSpan.FromHours(1);
    private static readonly TimeSpan KeyLifetime = TimeSpan.FromHours(2);
    private static readonly TimeSpan ClockSkew = TimeSpan.FromMinutes(5);

    private readonly SemaphoreSlim _gate = new(1, 1);
    private UserDelegationKey? _key;

    private BlobContainerClient Container => service.GetBlobContainerClient(containerName);

    /// <summary>invoices/2026/11/1001.json: the date prefix keeps listings and lifecycle filters cheap.</summary>
    public static string BlobName(Order order) => $"{order.CreatedUtc:yyyy}/{order.CreatedUtc:MM}/{order.Id}.json";

    public async Task SaveAsync(Order order, CancellationToken ct)
    {
        var json = JsonSerializer.SerializeToUtf8Bytes(OrderDto.From(order), JsonSerializerOptions.Web);
        await Container.GetBlobClient(BlobName(order)).UploadAsync(new BinaryData(json), new BlobUploadOptions
        {
            HttpHeaders = new BlobHttpHeaders { ContentType = "application/json" },
            Metadata = new Dictionary<string, string> { ["customer"] = order.CustomerId },
        }, ct);
    }

    public async Task<InvoiceLink> GetReadLinkAsync(Order order, TimeSpan lifetime, CancellationToken ct)
    {
        if (lifetime <= TimeSpan.Zero || lifetime > MaxLinkLifetime)
            throw new ArgumentOutOfRangeException(nameof(lifetime), $"1 second to {MaxLinkLifetime}.");

        var now = time.GetUtcNow();
        var key = await GetKeyAsync(now, lifetime, ct);
        var blob = Container.GetBlobClient(BlobName(order));
        var sas = new BlobSasBuilder
        {
            BlobContainerName = containerName,
            BlobName = blob.Name,
            Resource = "b",                       // one blob, not the container
            StartsOn = now - ClockSkew,
            ExpiresOn = now + lifetime,
            Protocol = SasProtocol.Https,
        };
        sas.SetPermissions(BlobSasPermissions.Read);

        var uri = new BlobUriBuilder(blob.Uri) { Sas = sas.ToSasQueryParameters(key, service.AccountName) }.ToUri();
        return new InvoiceLink(uri, sas.ExpiresOn);
    }

    /// <summary>One key serves many links; get a new one before the current key can't cover the link.</summary>
    private async Task<UserDelegationKey> GetKeyAsync(DateTimeOffset now, TimeSpan lifetime, CancellationToken ct)
    {
        await _gate.WaitAsync(ct);
        try
        {
            if (_key is null || _key.SignedExpiresOn < now + lifetime)
                _key = (await service.GetUserDelegationKeyAsync(now - ClockSkew, now + KeyLifetime, ct)).Value;
            return _key;
        }
        finally
        {
            _gate.Release();
        }
    }
}

/// <summary>Used when no storage account is configured (local runs without Azurite).</summary>
public sealed class DisabledInvoiceStore : IInvoiceStore
{
    public Task SaveAsync(Order order, CancellationToken ct) => Task.CompletedTask;
    public Task<InvoiceLink> GetReadLinkAsync(Order order, TimeSpan lifetime, CancellationToken ct) =>
        throw new InvalidOperationException("Invoices:BlobServiceUri is not configured.");
}
