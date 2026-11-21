namespace ReadinessProbe;

/// <summary>Bound from the "Probe" section (App Service app settings: Probe__BlobContainerUri, ...).</summary>
public sealed class ProbeOptions
{
    public const string Section = "Probe";

    /// <summary>https://&lt;account&gt;.blob.core.windows.net/&lt;container&gt;</summary>
    public Uri? BlobContainerUri { get; set; }

    /// <summary>https://&lt;vault&gt;.vault.azure.net/</summary>
    public Uri? KeyVaultUri { get; set; }

    public string SecretName { get; set; } = "probe-secret";

    /// <summary>Per-dependency timeout. Health check pings that take longer than a minute count as failures.</summary>
    public TimeSpan Timeout { get; set; } = TimeSpan.FromSeconds(5);
}
