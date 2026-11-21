using System.Net;
using System.Runtime.CompilerServices;

namespace Contoso.Approvals.Tests;

internal static class Wait
{
    /// <summary>Polls until <paramref name="condition"/> is true (continuations may run on the thread pool).</summary>
    public static async Task UntilAsync(Func<bool> condition, int timeoutMs = 5000)
    {
        var deadline = Environment.TickCount64 + timeoutMs;
        while (!condition())
        {
            if (Environment.TickCount64 > deadline) throw new TimeoutException("Condition not met in time.");
            await Task.Delay(5);
        }
    }
}

internal static class Data
{
    public static ProjectRequest Request(int n, string costCenter = "CC-100", decimal budget = 10_000m, string department = "IT") =>
        new($"PR-2026-{n:0000}", $"Request {n}", department, costCenter, budget);

    public static List<ProjectRequest> Batch(int count) => [.. Enumerable.Range(1, count).Select(n => Request(n))];

    public static async IAsyncEnumerable<T> ToAsync<T>(IEnumerable<T> items, [EnumeratorCancellation] CancellationToken ct = default)
    {
        foreach (var item in items)
        {
            await Task.Yield();
            ct.ThrowIfCancellationRequested();
            yield return item;
        }
    }

    public static HttpRequestException Http(HttpStatusCode code) => new($"HTTP {(int)code}", null, code);
}

/// <summary>A fake Finance API client with real (small) delays that records how many calls overlap.</summary>
internal sealed class CountingClient(int delayMs = 30) : IFinanceClient
{
    private int _budgetInFlight, _maxBudgetInFlight, _totalInFlight, _maxTotalInFlight;
    public int MaxBudgetInFlight => Volatile.Read(ref _maxBudgetInFlight);
    public int MaxTotalInFlight => Volatile.Read(ref _maxTotalInFlight);
    public int Completed;
    public Func<ProjectRequest, int>? DelayFor { get; init; }
    public decimal Remaining { get; init; } = 100_000m;

    public async Task<BudgetInfo> GetBudgetAsync(string costCenter, CancellationToken ct)
    {
        Raise(ref _budgetInFlight, ref _maxBudgetInFlight);
        Raise(ref _totalInFlight, ref _maxTotalInFlight);
        try
        {
            await Task.Delay(delayMs, ct);
            return new BudgetInfo(costCenter, Remaining);
        }
        finally
        {
            Interlocked.Decrement(ref _budgetInFlight);
            Interlocked.Decrement(ref _totalInFlight);
            Interlocked.Increment(ref Completed);
        }
    }

    public async Task<Approver> GetApproverAsync(string department, CancellationToken ct)
    {
        Raise(ref _totalInFlight, ref _maxTotalInFlight);
        try
        {
            await Task.Delay(delayMs, ct);
            return new Approver(department, "kim.demo@contoso.com");
        }
        finally
        {
            Interlocked.Decrement(ref _totalInFlight);
        }
    }

    public IAsyncEnumerable<ProjectRequest> StreamRequestsAsync(CancellationToken ct) => Data.ToAsync(Data.Batch(12), ct);

    private static void Raise(ref int current, ref int max)
    {
        var now = Interlocked.Increment(ref current);
        int seen;
        while (now > (seen = Volatile.Read(ref max)))
            if (Interlocked.CompareExchange(ref max, now, seen) == seen) break;
    }
}

/// <summary>A client whose calls finish only when the test says so (per cost center).</summary>
internal sealed class GatedClient : IFinanceClient
{
    public readonly Dictionary<string, TaskCompletionSource<BudgetInfo>> Budgets = [];
    public int BudgetCalls, ApproverCalls;

    public Task<BudgetInfo> GetBudgetAsync(string costCenter, CancellationToken ct)
    {
        Interlocked.Increment(ref BudgetCalls);
        lock (Budgets)
        {
            if (!Budgets.TryGetValue(costCenter, out var tcs))
                Budgets[costCenter] = tcs = new TaskCompletionSource<BudgetInfo>(TaskCreationOptions.RunContinuationsAsynchronously);
            return tcs.Task.WaitAsync(ct);
        }
    }

    public Task<Approver> GetApproverAsync(string department, CancellationToken ct)
    {
        Interlocked.Increment(ref ApproverCalls);
        return Task.FromResult(new Approver(department, "kim.demo@contoso.com"));
    }

    public IAsyncEnumerable<ProjectRequest> StreamRequestsAsync(CancellationToken ct) => throw new NotSupportedException();

    public void Release(string costCenter, decimal remaining)
    {
        lock (Budgets) Budgets[costCenter].SetResult(new BudgetInfo(costCenter, remaining));
    }
}
