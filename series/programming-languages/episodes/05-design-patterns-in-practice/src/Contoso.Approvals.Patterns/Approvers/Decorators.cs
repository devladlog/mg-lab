using System.Collections.Concurrent;
using Microsoft.Extensions.Options;

namespace Contoso.Approvals.Patterns.Approvers;

/// <summary>
/// Decorator: same interface as the thing it wraps, adds caching, and the caller can't tell the difference.
/// </summary>
public sealed class CachingApproverDirectory(
    IApproverDirectory inner,
    TimeProvider time,
    IOptions<ApproverDirectoryOptions> options) : IApproverDirectory
{
    private readonly ConcurrentDictionary<(string Department, ApproverRole Role), CacheEntry> _cache = new();

    public async Task<string> FindAsync(string department, ApproverRole role, CancellationToken cancellationToken = default)
    {
        var key = (department, role);
        var now = time.GetUtcNow();
        if (_cache.TryGetValue(key, out var entry) && entry.ExpiresAt > now)
        {
            return entry.Approver;
        }

        var approver = await inner.FindAsync(department, role, cancellationToken).ConfigureAwait(false);
        _cache[key] = new CacheEntry(approver, now.AddSeconds(options.Value.CacheSeconds));
        return approver;
    }

    private sealed record CacheEntry(string Approver, DateTimeOffset ExpiresAt);
}

/// <summary>Decorator: counts every lookup that reaches this layer, then delegates.</summary>
public sealed class MeteredApproverDirectory(IApproverDirectory inner, DirectoryStats stats) : IApproverDirectory
{
    public Task<string> FindAsync(string department, ApproverRole role, CancellationToken cancellationToken = default)
    {
        stats.CountLookup();
        return inner.FindAsync(department, role, cancellationToken);
    }
}
