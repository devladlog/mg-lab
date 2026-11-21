namespace Contoso.Approvals;

public sealed record EnricherOptions(TimeSpan AttemptTimeout, int MaxAttempts, TimeSpan RetryBaseDelay)
{
    public static EnricherOptions Default { get; } = new(TimeSpan.FromSeconds(2), 3, TimeSpan.FromMilliseconds(200));
}

/// <summary>Fetches what an approver needs: remaining budget and the department's approver, at the same time.</summary>
public sealed class Enricher(IFinanceClient client, TimeProvider time, EnricherOptions? options = null)
{
    private readonly EnricherOptions _options = options ?? EnricherOptions.Default;

    /// <summary>Raised on every retry (attempt, delay, error). The CLI prints it.</summary>
    public event Action<string, int, TimeSpan, Exception>? Retrying;

    public async Task<EnrichedRequest> EnrichAsync(ProjectRequest request, CancellationToken ct)
    {
        // Start both calls first, then await: they overlap. Awaiting each call in turn would add the latencies.
        Task<BudgetInfo> budget = CallAsync($"budget {request.CostCenter}", c => client.GetBudgetAsync(request.CostCenter, c), ct);
        Task<Approver> approver = CallAsync($"approver {request.Department}", c => client.GetApproverAsync(request.Department, c), ct);

        await Task.WhenAll(budget, approver).ConfigureAwait(false);
        return new EnrichedRequest(request, await budget.ConfigureAwait(false), await approver.ConfigureAwait(false));
    }

    // Each attempt gets its own timeout; transient failures (503, timeout) are retried with backoff.
    private Task<T> CallAsync<T>(string what, Func<CancellationToken, Task<T>> call, CancellationToken ct) =>
        Resilience.RetryAsync(
            attemptCt => Resilience.WithTimeoutAsync(call, _options.AttemptTimeout, time, attemptCt),
            _options.MaxAttempts, _options.RetryBaseDelay, time, ct,
            (attempt, delay, error) => Retrying?.Invoke(what, attempt, delay, error));
}
