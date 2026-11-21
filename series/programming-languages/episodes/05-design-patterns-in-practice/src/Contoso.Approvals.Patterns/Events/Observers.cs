using System.Globalization;
using Microsoft.Extensions.Options;

namespace Contoso.Approvals.Patterns.Events;

/// <summary>Observer: anything that wants to react to a routed request implements this and registers itself.</summary>
public interface IRequestObserver
{
    Task OnRoutedAsync(RequestRouted routed, CancellationToken cancellationToken);
}

/// <summary>Per unit of work (one batch = one DI scope). Registered as scoped.</summary>
public sealed class AuditTrail
{
    private readonly List<string> _entries = [];

    public IReadOnlyList<string> Entries => _entries;

    public void Add(string entry) => _entries.Add(entry);
}

/// <summary>Scoped observer: writes into the AuditTrail of the current scope.</summary>
public sealed class AuditObserver(AuditTrail trail) : IRequestObserver
{
    public Task OnRoutedAsync(RequestRouted routed, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(routed);
        trail.Add($"{routed.Request.Code} routed to {routed.Route} ({routed.Steps.Count} step(s))");
        return Task.CompletedTask;
    }
}

/// <summary>Singleton observer: one notification file per request for the first approver.</summary>
public sealed class OutboxObserver(IOptions<OutboxOptions> options) : IRequestObserver
{
    public async Task OnRoutedAsync(RequestRouted routed, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(routed);
        var folder = options.Value.Folder;
        Directory.CreateDirectory(folder);
        var first = routed.Steps[0];
        var body = string.Create(CultureInfo.InvariantCulture,
            $"To: {first.Approver} ({first.Role})\nSubject: {routed.Request.Code} needs your approval\n\n" +
            $"{routed.Request.Title}, {routed.Request.Budget:N2} EUR, route {routed.Route}, due in {routed.DueInDays} days.\n");
        await File.WriteAllTextAsync(Path.Combine(folder, $"{routed.Request.Code}.txt"), body, cancellationToken)
            .ConfigureAwait(false);
    }
}

/// <summary>Application-wide totals per route. Singleton, so it must be thread-safe.</summary>
public sealed class BudgetTally
{
    private readonly Lock _gate = new();
    private readonly SortedDictionary<string, (int Count, decimal Total)> _byRoute = new(StringComparer.Ordinal);

    public void Add(string route, decimal budget)
    {
        lock (_gate)
        {
            var current = _byRoute.GetValueOrDefault(route);
            _byRoute[route] = (current.Count + 1, current.Total + budget);
        }
    }

    public IReadOnlyList<(string Route, int Count, decimal Total)> Snapshot()
    {
        lock (_gate)
        {
            return [.. _byRoute.Select(kv => (kv.Key, kv.Value.Count, kv.Value.Total))];
        }
    }
}

public sealed class BudgetTallyObserver(BudgetTally tally) : IRequestObserver
{
    public Task OnRoutedAsync(RequestRouted routed, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(routed);
        tally.Add(routed.Route, routed.Request.Budget);
        return Task.CompletedTask;
    }
}
