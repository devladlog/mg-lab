using System.Diagnostics.CodeAnalysis;
using System.Globalization;

namespace Contoso.Requests;

/// <summary>
/// "PR-2026-0042" parsed from a span: no Substring, no Split, no allocations.
/// ISpanParsable gives it the same shape as int.Parse / int.TryParse.
/// </summary>
public readonly record struct RequestCode(int Year, int Number) : ISpanParsable<RequestCode>
{
    public static bool TryParse(ReadOnlySpan<char> s, IFormatProvider? provider, out RequestCode result)
    {
        result = default;
        // "PR-" yyyy "-" nnnn  -> exactly 12 characters
        if (s.Length != 12 || !s.StartsWith("PR-") || s[7] != '-') return false;
        if (!int.TryParse(s.Slice(3, 4), NumberStyles.None, CultureInfo.InvariantCulture, out var year)) return false;
        if (!int.TryParse(s.Slice(8, 4), NumberStyles.None, CultureInfo.InvariantCulture, out var number)) return false;
        if (year is < 2000 or > 2099 || number == 0) return false;
        result = new RequestCode(year, number);
        return true;
    }

    public static bool TryParse(ReadOnlySpan<char> s, out RequestCode result) => TryParse(s, null, out result);

    public static RequestCode Parse(ReadOnlySpan<char> s, IFormatProvider? provider) =>
        TryParse(s, provider, out var code) ? code : throw new FormatException($"'{s}' is not a request code like PR-2026-0042.");

    public static RequestCode Parse(string s, IFormatProvider? provider) => Parse(s.AsSpan(), provider);

    public static bool TryParse([NotNullWhen(true)] string? s, IFormatProvider? provider, out RequestCode result) =>
        TryParse(s.AsSpan(), provider, out result);

    public override string ToString() => string.Create(CultureInfo.InvariantCulture, $"PR-{Year:D4}-{Number:D4}");
}
