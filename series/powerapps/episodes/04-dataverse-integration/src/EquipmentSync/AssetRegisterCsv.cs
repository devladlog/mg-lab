using System.Globalization;
using System.Text;
using System.Text.RegularExpressions;

namespace EquipmentSync;

/// <summary>
/// Reads the nightly export of the (fictional) Contoso asset register:
/// asset_tag,name,category,serial_number,purchase_date,status
/// Bad rows are rejected with a reason instead of being sent to Dataverse, so one typo doesn't cost a round trip.
/// </summary>
public static partial class AssetRegisterCsv
{
    public static readonly string[] Header = ["asset_tag", "name", "category", "serial_number", "purchase_date", "status"];
    private static readonly HashSet<string> RegisterStatuses = ["in_service", "in_repair", "retired"];

    // CT- and four digits. Also keeps out the characters Learn says break alternate-key upserts: / < > * % & : \ ? +
    [GeneratedRegex(@"^CT-\d{4}$")]
    private static partial Regex TagPattern();

    public sealed record ParseResult(IReadOnlyList<AssetRow> Rows, IReadOnlyList<RowResult> Rejected);

    public static ParseResult Parse(TextReader reader)
    {
        var rows = new List<AssetRow>();
        var rejected = new List<RowResult>();
        var seen = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);

        var header = reader.ReadLine() ?? throw new FormatException("The file is empty.");
        var columns = SplitLine(header).Select(c => c.Trim().ToLowerInvariant()).ToArray();
        if (!columns.SequenceEqual(Header))
            throw new FormatException($"Unexpected header '{header}'. Expected: {string.Join(",", Header)}");

        var lineNo = 1;
        while (reader.ReadLine() is { } line)
        {
            lineNo++;
            if (line.Trim().Length == 0) continue;
            var f = SplitLine(line).Select(v => v.Trim()).ToArray();
            var tag = f.Length > 0 ? f[0].ToUpperInvariant() : "";
            string? error = f.Length != Header.Length ? $"expected {Header.Length} fields, found {f.Length}"
                : !TagPattern().IsMatch(tag) ? $"asset tag '{f[0]}' is not like CT-0042"
                : f[1].Length is 0 or > 100 ? "name is required (max 100 characters)"
                : !Equipment.Categories.ContainsKey(f[2]) ? $"unknown category '{f[2]}'"
                : f[3].Length > 50 ? "serial number is longer than 50 characters"
                : f[4].Length > 0 && !DateOnly.TryParseExact(f[4], "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out _) ? $"purchase date '{f[4]}' is not yyyy-MM-dd"
                : !RegisterStatuses.Contains(f[5].ToLowerInvariant()) ? $"unknown status '{f[5]}'"
                : seen.TryGetValue(tag, out var first) ? $"duplicate of line {first}"
                : null;

            if (error != null)
            {
                rejected.Add(new RowResult(lineNo, tag, RowOutcome.Rejected, error));
                continue;
            }
            seen[tag] = lineNo;
            rows.Add(new AssetRow(lineNo, tag, f[1], f[2], f[3].Length > 0 ? f[3] : null,
                f[4].Length > 0 ? DateOnly.ParseExact(f[4], "yyyy-MM-dd", CultureInfo.InvariantCulture) : null,
                f[5].ToLowerInvariant()));
        }
        return new ParseResult(rows, rejected);
    }

    /// <summary>RFC 4180-style split of one line: commas, double quotes, "" inside quotes.</summary>
    internal static List<string> SplitLine(string line)
    {
        var fields = new List<string>();
        var current = new StringBuilder();
        var quoted = false;
        for (var i = 0; i < line.Length; i++)
        {
            var c = line[i];
            if (quoted)
            {
                if (c == '"' && i + 1 < line.Length && line[i + 1] == '"') { current.Append('"'); i++; }
                else if (c == '"') quoted = false;
                else current.Append(c);
            }
            else if (c == '"') quoted = true;
            else if (c == ',') { fields.Add(current.ToString()); current.Clear(); }
            else current.Append(c);
        }
        fields.Add(current.ToString());
        return fields;
    }

    /// <summary>Quotes a value for CSV output when needed.</summary>
    internal static string Quote(string? value) =>
        value is null ? "" : value.IndexOfAny([',', '"', '\n', '\r']) >= 0 ? "\"" + value.Replace("\"", "\"\"") + "\"" : value;
}
