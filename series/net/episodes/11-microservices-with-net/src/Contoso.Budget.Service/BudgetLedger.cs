using System.Collections.Concurrent;

namespace Contoso.Budget.Service;

public sealed record Reservation(Guid Id, string Department, decimal Amount, string Reference, DateTime CreatedAtUtc);

public sealed record BudgetStatus(string Department, decimal Limit, decimal Reserved, decimal Remaining);

public enum ReserveOutcome { Created, Replayed, OverBudget, KeyReusedForDifferentRequest, UnknownDepartment }

/// <summary>
/// The Budget service's own data (in memory: it is this service's private store, nobody else reads it).
/// Every reservation is stored under the caller's idempotency key, so a repeated call returns the first answer.
/// </summary>
public sealed class BudgetLedger(IReadOnlyDictionary<string, decimal> limits)
{
    private readonly object _gate = new();
    private readonly ConcurrentDictionary<Guid, Reservation> _byKey = new();
    private readonly Dictionary<string, decimal> _reserved = limits.ToDictionary(l => l.Key, _ => 0m, StringComparer.OrdinalIgnoreCase);
    private readonly IReadOnlyDictionary<string, decimal> _limits =
        new Dictionary<string, decimal>(limits, StringComparer.OrdinalIgnoreCase);

    public IReadOnlyList<BudgetStatus> All() => _limits.Keys.Order().Select(d => Status(d)!).ToList();

    public BudgetStatus? Status(string department)
    {
        lock (_gate)
        {
            if (!_limits.TryGetValue(department, out var limit)) return null;
            var reserved = _reserved[department];
            return new BudgetStatus(department.ToUpperInvariant(), limit, reserved, limit - reserved);
        }
    }

    public (ReserveOutcome Outcome, Reservation? Reservation) Reserve(Guid key, string department, decimal amount, string reference)
    {
        lock (_gate)   // check-then-add must be one step, or two parallel calls could both fit
        {
            if (!_limits.TryGetValue(department, out var limit)) return (ReserveOutcome.UnknownDepartment, null);

            if (_byKey.TryGetValue(key, out var existing))
            {
                var same = existing.Department.Equals(department, StringComparison.OrdinalIgnoreCase)
                           && existing.Amount == amount && existing.Reference == reference;
                return same ? (ReserveOutcome.Replayed, existing) : (ReserveOutcome.KeyReusedForDifferentRequest, null);
            }

            if (_reserved[department] + amount > limit) return (ReserveOutcome.OverBudget, null);

            var reservation = new Reservation(Guid.NewGuid(), department.ToUpperInvariant(), amount, reference, DateTime.UtcNow);
            _byKey[key] = reservation;
            _reserved[department] += amount;
            return (ReserveOutcome.Created, reservation);
        }
    }
}
