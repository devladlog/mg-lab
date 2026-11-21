using Contoso.Mobile.Core.Api;
using Contoso.Mobile.Core.Models;

namespace Contoso.Mobile.Core.Offline;

/// <summary>What the app asks the OS: is there a network? (MAUI: <c>Connectivity.Current</c>, wrapped in the app project.)</summary>
public interface IConnectivityService
{
    bool IsOnline { get; }
    event EventHandler? Changed;
}

/// <summary>Sends the outbox to the server, oldest first.</summary>
public sealed class SyncService(IOutbox outbox, IRequestsApi api, IConnectivityService connectivity)
{
    private readonly SemaphoreSlim _running = new(1, 1);

    public async Task<SyncReport> FlushAsync(CancellationToken ct = default)
    {
        if (!connectivity.IsOnline) return new SyncReport(0, 0, (await outbox.ListAsync(ct)).Count, Skipped: true);

        // One flush at a time: "back online" and a pull-to-refresh can arrive together, and the same draft must not go twice in parallel.
        await _running.WaitAsync(ct);
        try
        {
            int sent = 0, rejected = 0;
            foreach (var draft in await outbox.ListAsync(ct))
            {
                if (draft.NeedsAttention) continue;   // the server said no: waits for the user, never retried by itself

                var result = await api.SubmitAsync(draft, ct);
                if (result.IsStored) { await outbox.RemoveAsync(draft.Key, ct); sent++; }
                else if (result.Outcome == SubmitOutcome.Rejected)
                {
                    await outbox.MarkRejectedAsync(draft.Key, result.Error ?? "Rejected by the server.", ct);
                    rejected++;
                }
                else break;   // Unavailable: the network is not really there. Keep the rest, in order, for next time.
            }
            return new SyncReport(sent, rejected, (await outbox.ListAsync(ct)).Count(d => !d.NeedsAttention), Skipped: false);
        }
        finally { _running.Release(); }
    }
}
