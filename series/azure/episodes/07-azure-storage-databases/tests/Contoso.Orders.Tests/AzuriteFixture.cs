using System.Diagnostics;
using System.Net;
using System.Net.Sockets;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text;
using System.Text.Json;
using Azure.Core;
using Azure.Core.Pipeline;
using Azure.Storage.Blobs;

namespace Contoso.Orders.Tests;

/// <summary>
/// Starts Azurite (the Blob Storage emulator) over HTTPS with OAuth enabled, so the tests exercise the
/// real Entra-token flow: GetUserDelegationKey needs a bearer token, and Azurite checks the
/// user delegation SAS signature. Needs node/npx (Windows, macOS or Linux); downloads azurite@3.38.0 once.
/// </summary>
public sealed class AzuriteFixture : IAsyncLifetime
{
    public const string Account = "devstoreaccount1";
    private readonly string _dir = Directory.CreateTempSubdirectory("azurite-").FullName;
    private Process? _azurite;

    public Uri ServiceUri { get; private set; } = null!;

    /// <summary>Self-signed certificate: trust it in tests only.</summary>
    public static HttpClient InsecureHttp() => new(new HttpClientHandler
    {
        ServerCertificateCustomValidationCallback = HttpClientHandler.DangerousAcceptAnyServerCertificateValidator,
    });

    public BlobServiceClient NewServiceClient() => new(ServiceUri, new FakeEntraToken(), new BlobClientOptions
    {
        Transport = new HttpClientTransport(InsecureHttp()),
        Retry = { MaxRetries = 0 },
    });

    public async Task InitializeAsync()
    {
        WriteSelfSignedCertificate();
        var port = FreePort();
        ServiceUri = new Uri($"https://127.0.0.1:{port}/{Account}");
        _azurite = Process.Start(new ProcessStartInfo(Npx(),
            $"--yes --package azurite@3.38.0 azurite-blob --blobHost 127.0.0.1 --blobPort {port} " +
            $"--cert cert.pem --key key.pem --oauth basic --inMemoryPersistence --silent --skipApiVersionCheck")
        {
            WorkingDirectory = _dir, RedirectStandardOutput = true, RedirectStandardError = true,
        })!;

        using var http = InsecureHttp();
        for (var i = 0; i < 120; i++) // first run downloads the package
        {
            try { await http.GetAsync(ServiceUri); return; }
            catch (HttpRequestException) { await Task.Delay(500); }
        }
        throw new InvalidOperationException("Azurite did not start: " + await _azurite.StandardError.ReadToEndAsync());
    }

    public Task DisposeAsync()
    {
        try { _azurite?.Kill(entireProcessTree: true); } catch (InvalidOperationException) { }
        _azurite?.Dispose();
        Directory.Delete(_dir, recursive: true);
        return Task.CompletedTask;
    }

    /// <summary>
    /// npx with a full path. On Windows the npx.cmd shim finds npm relative to its own folder, which breaks
    /// when it is started by bare name from another working directory, so look it up on PATH first.
    /// </summary>
    private static string Npx()
    {
        if (!OperatingSystem.IsWindows()) return "npx";
        foreach (var dir in (Environment.GetEnvironmentVariable("PATH") ?? "").Split(Path.PathSeparator, StringSplitOptions.RemoveEmptyEntries))
        {
            var candidate = Path.Combine(dir.Trim('"'), "npx.cmd");
            if (File.Exists(candidate)) return candidate;
        }
        return "npx.cmd";
    }

    /// <summary>A one-day self-signed certificate for 127.0.0.1, written as cert.pem and key.pem (no openssl needed).</summary>
    private void WriteSelfSignedCertificate()
    {
        using var rsa = RSA.Create(2048);
        var req = new CertificateRequest("CN=127.0.0.1", rsa, HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1);
        var san = new SubjectAlternativeNameBuilder();
        san.AddIpAddress(IPAddress.Loopback);
        req.CertificateExtensions.Add(san.Build());
        using var cert = req.CreateSelfSigned(DateTimeOffset.UtcNow.AddMinutes(-5), DateTimeOffset.UtcNow.AddDays(1));
        File.WriteAllText(Path.Combine(_dir, "cert.pem"), cert.ExportCertificatePem());
        File.WriteAllText(Path.Combine(_dir, "key.pem"), rsa.ExportPkcs8PrivateKeyPem());
    }

    private static int FreePort()
    {
        using var l = new TcpListener(IPAddress.Loopback, 0);
        l.Start();
        return ((IPEndPoint)l.LocalEndpoint).Port;
    }

    /// <summary>An unsigned JWT with the claims Azurite's "basic" OAuth mode checks (aud, iss, iat, nbf, exp; oid/tid go into the delegation key).</summary>
    private sealed class FakeEntraToken : TokenCredential
    {
        public override AccessToken GetToken(TokenRequestContext requestContext, CancellationToken cancellationToken)
        {
            var now = DateTimeOffset.UtcNow;
            static string B64(object o) => Convert.ToBase64String(Encoding.UTF8.GetBytes(JsonSerializer.Serialize(o)))
                .TrimEnd('=').Replace('+', '-').Replace('/', '_');
            var jwt = B64(new { alg = "RS256", typ = "JWT" }) + "." + B64(new
            {
                aud = "https://storage.azure.com",
                iss = "https://sts.windows.net/00000000-0000-0000-0000-000000000000/",
                iat = now.AddMinutes(-5).ToUnixTimeSeconds(),
                nbf = now.AddMinutes(-5).ToUnixTimeSeconds(),
                exp = now.AddHours(1).ToUnixTimeSeconds(),
                oid = "00000000-0000-0000-0000-000000000001",
                tid = "00000000-0000-0000-0000-000000000000",
            }) + ".c2ln";
            return new AccessToken(jwt, now.AddHours(1));
        }

        public override ValueTask<AccessToken> GetTokenAsync(TokenRequestContext requestContext, CancellationToken cancellationToken) =>
            new(GetToken(requestContext, cancellationToken));
    }
}

[CollectionDefinition("azurite")]
public class AzuriteCollection : ICollectionFixture<AzuriteFixture>;
