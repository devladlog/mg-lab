using System.Globalization;

namespace Contoso.Portfolio;

public sealed record Rejected(int LineNumber, string Error);
public sealed record ImportResult(IReadOnlyList<ProjectRequest> Accepted, IReadOnlyList<Rejected> Rejected);

/// <summary>CSV import as a pipeline of small pure functions. Errors are values, not exceptions.</summary>
public static class Import
{
    public static Result<ProjectRequest> ParseLine(string line, int id, IReadOnlySet<string> departments) =>
        from fields in Fields(line, expected: 5)
        from budget in Budget(fields[3])
        from department in Department(fields[2], departments)
        from submitted in Date(fields[4])
        select new ProjectRequest(id, fields[0].Trim(), fields[1].Trim(), department, budget,
            RequestStatus.Draft, submitted);

    public static ImportResult FromCsv(IEnumerable<string> lines, IReadOnlySet<string> departments)
    {
        var parsed = lines
            .Skip(1)                                         // header
            .Index()
            .Where(x => !string.IsNullOrWhiteSpace(x.Item))
            .Select(x => (Line: x.Index + 2, Result: ParseLine(x.Item, 1000 + x.Index, departments)))
            .ToList();                                       // enumerate once, then split

        return new ImportResult(
            [.. parsed.Where(p => p.Result.IsOk).Select(p => p.Result.Value)],
            [.. parsed.Where(p => !p.Result.IsOk).Select(p => new Rejected(p.Line, p.Result.Error!))]);
    }

    private static Result<string[]> Fields(string line, int expected)
    {
        var fields = line.Split(',');
        return fields.Length == expected
            ? Result.Ok(fields)
            : Result.Fail<string[]>($"expected {expected} fields, found {fields.Length}");
    }

    private static Result<decimal> Budget(string text) =>
        decimal.TryParse(text, NumberStyles.Number, CultureInfo.InvariantCulture, out var value) && value > 0
            ? Result.Ok(value)
            : Result.Fail<decimal>($"budget '{text}' is not a positive number");

    private static Result<string> Department(string name, IReadOnlySet<string> known) =>
        DepartmentCodes.TryGetValue(name.Trim(), out var code) && known.Contains(code)
            ? Result.Ok(code)
            : Result.Fail<string>($"unknown department '{name.Trim()}'");

    private static Result<DateOnly> Date(string text) =>
        DateOnly.TryParseExact(text.Trim(), "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out var date)
            ? Result.Ok(date)
            : Result.Fail<DateOnly>($"date '{text.Trim()}' is not yyyy-MM-dd");

    private static readonly Dictionary<string, string> DepartmentCodes = new(StringComparer.OrdinalIgnoreCase)
    {
        ["IT"] = "IT", ["Sales"] = "SAL", ["Operations"] = "OPS", ["Marketing"] = "MKT", ["Legal"] = "LEG",
    };
}
