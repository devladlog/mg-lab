using System.Text.RegularExpressions;

namespace Contoso.Requests;

/// <summary>Validated, lower-cased e-mail address. The regex is generated at compile time (source generator).</summary>
public readonly partial record struct EmailAddress
{
    public string Value { get; }

    private EmailAddress(string value) => Value = value;

    public static EmailAddress Parse(string text) =>
        TryParse(text, out var email) ? email : throw new FormatException($"'{text}' is not a valid e-mail address.");

    public static bool TryParse(string? text, out EmailAddress email)
    {
        var candidate = text?.Trim().ToLowerInvariant();
        email = candidate is not null && Pattern.IsMatch(candidate) ? new EmailAddress(candidate) : default;
        return email.Value is not null;
    }

    public override string ToString() => Value ?? "";

    // C# 13 partial property + [GeneratedRegex] (.NET 9+): the regex code is generated at build time, not parsed at run time.
    [GeneratedRegex(@"^[^\s@]+@[^\s@]+\.[^\s@]+$")]
    private static partial Regex Pattern { get; }
}
