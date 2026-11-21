using System.Text;
using System.Text.RegularExpressions;

namespace Contoso.SecCopilotKit;

/// <summary>
/// Security Copilot templates use {{name}} placeholders (Learn, KQL plugins). This renders a template locally for testing.
/// Learn does not document how the service escapes values, so the kit treats every input as untrusted: placeholders must sit
/// inside a quoted string literal (checked by <see cref="KqlChecker"/>) and the local renderer escapes the value.
/// </summary>
public static partial class TemplateRenderer
{
    [GeneratedRegex(@"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")]
    private static partial Regex Placeholder();

    public static IReadOnlyList<string> Placeholders(string template) =>
        Placeholder().Matches(template).Select(m => m.Groups[1].Value).Distinct(StringComparer.Ordinal).ToList();

    /// <summary>Escapes a value for use inside a single- or double-quoted KQL string literal.</summary>
    public static string EscapeLiteral(string value)
    {
        var sb = new StringBuilder(value.Length + 8);
        foreach (var c in value)
        {
            switch (c)
            {
                case '\\': sb.Append("\\\\"); break;
                case '\'': sb.Append("\\'"); break;
                case '"': sb.Append("\\\""); break;
                case '\n': sb.Append("\\n"); break;
                case '\r': sb.Append("\\r"); break;
                case '\t': sb.Append("\\t"); break;
                default: sb.Append(c); break;
            }
        }
        return sb.ToString();
    }

    /// <summary>Replaces every placeholder; throws when a value is missing so a typo cannot render an empty filter.</summary>
    public static string Render(string template, IReadOnlyDictionary<string, string> values, bool escape = true) =>
        Placeholder().Replace(template, m =>
        {
            var name = m.Groups[1].Value;
            if (!values.TryGetValue(name, out var v)) throw new KeyNotFoundException($"No value for placeholder '{name}'.");
            return escape ? EscapeLiteral(v) : v;
        });
}
