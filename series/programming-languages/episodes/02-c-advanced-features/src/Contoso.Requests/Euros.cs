using System.Globalization;
using System.Numerics;

namespace Contoso.Requests;

/// <summary>
/// A money value that can't be mixed up with a plain decimal. Implementing the generic math interfaces
/// lets it flow through generic algorithms (<see cref="Totals.Sum{T}(ReadOnlySpan{T})"/>) like any number.
/// </summary>
public readonly record struct Euros(decimal Amount)
    : IAdditionOperators<Euros, Euros, Euros>,
      IAdditiveIdentity<Euros, Euros>,
      IComparisonOperators<Euros, Euros, bool>
{
    public static Euros Zero => new(0m);
    public static Euros AdditiveIdentity => Zero;

    public static Euros operator +(Euros left, Euros right) => new(left.Amount + right.Amount);
    public static bool operator <(Euros left, Euros right) => left.Amount < right.Amount;
    public static bool operator >(Euros left, Euros right) => left.Amount > right.Amount;
    public static bool operator <=(Euros left, Euros right) => left.Amount <= right.Amount;
    public static bool operator >=(Euros left, Euros right) => left.Amount >= right.Amount;

    public override string ToString() => Amount.ToString("#,0.##", CultureInfo.InvariantCulture) + " EUR";
}

public static class Totals
{
    /// <summary>One implementation for int, decimal, Euros... anything with + and a zero.</summary>
    public static T Sum<T>(ReadOnlySpan<T> values) where T : IAdditionOperators<T, T, T>, IAdditiveIdentity<T, T>
    {
        var total = T.AdditiveIdentity;
        foreach (var value in values) total += value;
        return total;
    }
}
