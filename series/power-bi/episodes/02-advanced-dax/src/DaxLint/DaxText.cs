using System.Text;
using System.Text.RegularExpressions;

namespace MGLab.DaxLint;

/// <summary>A DAX object reference: Table[Name], 'Table Name'[Name] or [Name].</summary>
public sealed record DaxRef(string? Table, string Name, int Position);

/// <summary>Just enough DAX lexing for linting: strings, comments, references and function arguments.
/// It is not a parser; it never evaluates anything.</summary>
public static class DaxText
{
    /// <summary>Replaces comments with spaces and string literals with "" (same length is not kept).</summary>
    public static string StripStringsAndComments(string dax, List<string>? strings = null)
    {
        var sb = new StringBuilder(dax.Length);
        int i = 0;
        while (i < dax.Length)
        {
            char c = dax[i];
            if (c == '"')
            {
                int j = i + 1;
                var lit = new StringBuilder();
                while (j < dax.Length)
                {
                    if (dax[j] == '"' && j + 1 < dax.Length && dax[j + 1] == '"') { lit.Append('"'); j += 2; continue; }
                    if (dax[j] == '"') break;
                    lit.Append(dax[j++]);
                }
                strings?.Add(lit.ToString());
                sb.Append("\"\"");
                i = j + 1;
            }
            else if (c == '\'' )
            {
                // quoted table name: copy as-is (may contain // or --)
                int j = i + 1;
                while (j < dax.Length && !(dax[j] == '\'' && (j + 1 >= dax.Length || dax[j + 1] != '\''))) j += dax[j] == '\'' ? 2 : 1;
                sb.Append(dax, i, Math.Min(j + 1, dax.Length) - i);
                i = j + 1;
            }
            else if (c == '[')
            {
                int j = dax.IndexOf(']', i);
                if (j < 0) j = dax.Length - 1;
                sb.Append(dax, i, j - i + 1);
                i = j + 1;
            }
            else if ((c == '/' && Next(dax, i) == '/') || (c == '-' && Next(dax, i) == '-'))
            {
                while (i < dax.Length && dax[i] != '\n') { sb.Append(' '); i++; }
            }
            else if (c == '/' && Next(dax, i) == '*')
            {
                int j = dax.IndexOf("*/", i + 2, StringComparison.Ordinal);
                j = j < 0 ? dax.Length : j + 2;
                sb.Append(' ', j - i);
                i = j;
            }
            else { sb.Append(c); i++; }
        }
        return sb.ToString();
    }

    static char Next(string s, int i) => i + 1 < s.Length ? s[i + 1] : '\0';

    static readonly Regex RefPattern = new(
        @"(?:'(?<qt>(?:[^']|'')+)'|(?<t>(?<![\w\]])[A-Za-z_][A-Za-z0-9_]*))?\[(?<n>[^\]]+)\]",
        RegexOptions.Compiled);

    /// <summary>References in already-stripped DAX text.</summary>
    public static IEnumerable<DaxRef> References(string stripped)
    {
        foreach (Match m in RefPattern.Matches(stripped))
        {
            string? table = m.Groups["qt"].Success ? m.Groups["qt"].Value.Replace("''", "'")
                          : m.Groups["t"].Success ? m.Groups["t"].Value : null;
            yield return new DaxRef(table, m.Groups["n"].Value, m.Index);
        }
    }

    /// <summary>Top-level arguments of every call to <paramref name="function"/> in stripped text.</summary>
    public static IEnumerable<List<string>> CallArguments(string stripped, string function)
    {
        var pattern = new Regex(@"(?<![\w.])" + Regex.Escape(function) + @"\s*\(", RegexOptions.IgnoreCase);
        foreach (Match m in pattern.Matches(stripped))
        {
            var args = new List<string>();
            int depth = 0, start = m.Index + m.Length;
            for (int i = start; i < stripped.Length; i++)
            {
                char c = stripped[i];
                if (c is '(' or '{') depth++;
                else if ((c is ')' or '}') && depth > 0) depth--;
                else if (c == ')' && depth == 0) { args.Add(stripped[start..i].Trim()); break; }
                else if (c == ',' && depth == 0) { args.Add(stripped[start..i].Trim()); start = i + 1; }
            }
            yield return args;
        }
    }

    /// <summary>Positions of a '/' division whose right operand is not a numeric literal.</summary>
    public static IEnumerable<int> NonConstantDivisions(string stripped)
    {
        for (int i = 0; i < stripped.Length; i++)
        {
            char c = stripped[i];
            if (c == '[') { int k = stripped.IndexOf(']', i); i = k < 0 ? stripped.Length : k; continue; }
            if (c == '\'') { int k = stripped.IndexOf('\'', i + 1); i = k < 0 ? stripped.Length : k; continue; }
            if (c != '/') continue;
            int j = i + 1;
            while (j < stripped.Length && char.IsWhiteSpace(stripped[j])) j++;
            if (j < stripped.Length && (char.IsDigit(stripped[j]) || stripped[j] == '.')) continue;
            yield return i;
        }
    }
}
