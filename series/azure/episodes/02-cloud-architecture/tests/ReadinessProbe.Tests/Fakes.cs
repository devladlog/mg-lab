using Azure;
using Azure.Security.KeyVault.Secrets;
using Azure.Storage.Blobs;
using Azure.Storage.Blobs.Models;

namespace ReadinessProbe.Tests;

/// <summary>Azure SDK clients have protected constructors and virtual methods so they can be faked.</summary>
public sealed class FakeContainer(Func<CancellationToken, Task>? behaviour = null) : BlobContainerClient
{
    public override string Name => "probe";

    public override async Task<Response<BlobContainerProperties>> GetPropertiesAsync(
        BlobRequestConditions? conditions = null, CancellationToken cancellationToken = default)
    {
        if (behaviour is not null) await behaviour(cancellationToken);
        return Response.FromValue(BlobsModelFactory.BlobContainerProperties(DateTimeOffset.UnixEpoch, ETag.All), null!);
    }
}

public sealed class FakeSecrets(Func<CancellationToken, Task>? behaviour = null) : SecretClient
{
    public const string Value = "s3cr3t-value-that-must-never-leak";

    // SDK 4.12 has two overloads; GetSecretAsync(name, cancellationToken: ct) binds to the newer one with
    // outContentType. Override both, or the base class runs with no pipeline and throws NullReferenceException.
    public override Task<Response<KeyVaultSecret>> GetSecretAsync(
        string name, string? version = null, CancellationToken cancellationToken = default) =>
        Get(name, cancellationToken);

    public override Task<Response<KeyVaultSecret>> GetSecretAsync(
        string name, string? version, SecretContentType? outContentType, CancellationToken cancellationToken = default) =>
        Get(name, cancellationToken);

    private async Task<Response<KeyVaultSecret>> Get(string name, CancellationToken cancellationToken)
    {
        if (behaviour is not null) await behaviour(cancellationToken);
        return Response.FromValue(SecretModelFactory.KeyVaultSecret(new SecretProperties(name), Value), null!);
    }
}

public static class Behaviours
{
    public static Func<CancellationToken, Task> Throw(Exception ex) => _ => Task.FromException(ex);
    public static Func<CancellationToken, Task> Hang => ct => Task.Delay(Timeout.Infinite, ct);
}
