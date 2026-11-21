using System.Collections.Concurrent;

namespace Contoso.Budget.Service;

/// <summary>
/// DEMO ONLY, off by default (both settings are 0 / false in appsettings.json). Makes the first N attempts per idempotency key
/// answer 503. With FailAfterCommit the reservation IS made first and the answer is lost: the nasty case,
/// the one where a retry without an idempotency key would reserve the money twice.
/// </summary>
public sealed class FaultOptions
{
    public int FailFirstAttemptsPerKey { get; set; }
    public bool FailAfterCommit { get; set; }
}

public sealed class FaultInjector(Microsoft.Extensions.Options.IOptionsMonitor<FaultOptions> options)
{
    private readonly ConcurrentDictionary<Guid, int> _attempts = new();

    public int AttemptsSeen(Guid key) => _attempts.TryGetValue(key, out var n) ? n : 0;

    /// <summary>Counts the attempt and says whether it should fail.</summary>
    public bool ShouldFail(Guid key, out bool afterCommit)
    {
        var o = options.CurrentValue;
        afterCommit = o.FailAfterCommit;
        var attempt = _attempts.AddOrUpdate(key, 1, (_, n) => n + 1);
        return attempt <= o.FailFirstAttemptsPerKey;
    }
}
