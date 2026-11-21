using System.Numerics;

namespace Contoso.Requests;

/// <summary>
/// C# 14 extension members: extension *properties* (not just methods), and static extension members
/// that appear on the type itself. The old `this` extension methods keep working next to them.
/// </summary>
public static class RequestExtensions
{
    extension(IEnumerable<ProjectRequest> requests)
    {
        /// <summary>requests.TotalBudget, a property on a type we don't own.</summary>
        public Euros TotalBudget => requests.Aggregate(Euros.Zero, (sum, r) => sum + r.Budget);

        public IEnumerable<ProjectRequest> HighPriority =>
            requests.Where(r => Rules.PriorityFor(r.Budget) == Priority.High);

        public IEnumerable<ProjectRequest> InState<TState>() where TState : RequestState =>
            requests.Where(r => r.State is TState);
    }

}

public static class TimeProviderExtensions
{
    extension(TimeProvider time)
    {
        /// <summary>time.Today: an extension property on a framework type.</summary>
        public DateOnly Today => DateOnly.FromDateTime(time.GetUtcNow().UtcDateTime);
    }

}

/// <summary>
/// One static class per receiver: with two non-generic extension blocks in one class, the .NET 10 SDK
/// analyzers report CA1708 ("names should differ by more than case") on the compiler-generated members.
/// </summary>
public static class EurosExtensions
{
    extension(Euros)
    {
        /// <summary>Static extension member: called as Euros.FromThousands(75).</summary>
        public static Euros FromThousands(decimal thousands) => new(thousands * 1_000m);
    }

}

public static class SpanMathExtensions
{
    extension<T>(ReadOnlySpan<T> values) where T : INumber<T>
    {
        /// <summary>
        /// Extension on ReadOnlySpan. With C# 14's implicit span conversions an int[] can use it directly:
        /// budgets.Mean() on an array finds this, no AsSpan() needed.
        /// </summary>
        public T Mean() => values.IsEmpty
            ? throw new InvalidOperationException("No values.")
            : Totals.Sum(values) / T.CreateChecked(values.Length);
    }
}
