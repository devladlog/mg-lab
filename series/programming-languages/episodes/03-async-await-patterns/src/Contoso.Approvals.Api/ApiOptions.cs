namespace Contoso.Approvals.Api;

/// <summary>Settings for the demo API. Override on the command line, e.g. <c>--Api:LatencyMs=50 --Api:Flaky=CC-400</c>.</summary>
public sealed class ApiOptions
{
    /// <summary>How long each budget / approver lookup takes (a fixed delay, so timings are reproducible).</summary>
    public int LatencyMs { get; set; } = 300;

    /// <summary>A cost center whose budget lookup answers 503 on every odd call (to show retries). Empty = off.</summary>
    public string Flaky { get; set; } = "";

    /// <summary>No per-call console lines (used by the integration tests).</summary>
    public bool Quiet { get; set; }
}
