using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;
using ProjectRequests.Api.Data;

namespace ProjectRequests.Api.Notifications;

public sealed record DigestLine(string Department, int Requests, decimal TotalBudget, DateTime OldestCreatedAtUtc);

public sealed record PendingDigest(DateTime GeneratedAtUtc, int StaleAfterDays, IReadOnlyList<DigestLine> Lines)
{
    public int TotalRequests => Lines.Sum(l => l.Requests);
}

/// <summary>
/// Scoped: it needs the scoped DbContext, and IOptionsSnapshot (also scoped) gives it the settings
/// as they are for this request or this worker run.
/// </summary>
public sealed class PendingDigestBuilder(
    RequestsDbContext db, TimeProvider clock, IOptionsSnapshot<NotificationOptions> options)
{
    public async Task<PendingDigest> BuildAsync(CancellationToken ct)
    {
        var now = clock.GetUtcNow().UtcDateTime;
        var days = options.Value.StaleAfterDays;
        var cutoff = now.AddDays(-days);

        var lines = await db.Requests
            .Where(r => r.Status == RequestStatus.Submitted && r.CreatedAtUtc <= cutoff)
            .GroupBy(r => r.Department.Code)
            .OrderBy(g => g.Key)
            .Select(g => new DigestLine(g.Key, g.Count(), g.Sum(r => r.Budget), g.Min(r => r.CreatedAtUtc)))
            .ToListAsync(ct);

        return new PendingDigest(now, days, lines);
    }
}
