using System.Globalization;
using Money = (decimal Amount, string Currency);   // C# 12: alias any type, here a tuple

namespace ProjectRequests.Features;

/// <summary>C# 12 on .NET 8: primary constructor on a class, collection expressions with spread, default lambda parameters.</summary>
public sealed class RequestReport(IReadOnlyList<RequestRecord> requests, TimeProvider clock)
{
    public int OpenCount => requests.Count(r => r.Status == RequestStatus.Submitted);

    public DateTime GeneratedAtUtc => clock.GetUtcNow().UtcDateTime;

    public Money Total(string currency = "EUR") => (requests.Sum(r => r.Budget), currency);

    /// <summary>High priority first, then the rest: two collection expressions joined by spread elements.</summary>
    public IReadOnlyList<RequestRecord> HighThenStandard()
    {
        RequestRecord[] high = [.. requests.Where(r => r.Priority == Priority.High)];
        RequestRecord[] standard = [.. requests.Where(r => r.Priority == Priority.Standard)];
        return [.. high, .. standard];
    }

    public static string[] FormatAll(IEnumerable<decimal> values)
    {
        var format = (decimal value, string currency = "EUR") => string.Create(CultureInfo.InvariantCulture, $"{value:N2} {currency}");   // default parameter in a lambda
        return [.. values.Select(v => format(v))];
    }
}

/// <summary>
/// The primary-constructor gotcha: for a class (not a record) the parameter is NOT a property. It is captured state that
/// any member can change.
/// </summary>
public sealed class Ticket(int start)
{
    public int Next() => start++;
}

public sealed record TicketRange(int Start);   // a record DOES get a public property per primary-constructor parameter
