using System.Globalization;

namespace Contoso.Requests.Clean;

/// <summary>
/// One line of the request file: Code;Title;Department;Budget;Justification.
/// Each question about a field has a name, so the processor reads like the rules.
/// </summary>
public readonly record struct RequestFields
{
    public const char Separator = ';';
    public const int Count = 5;
    private const string CodePrefix = "PR-";

    private readonly string[] _fields;

    private RequestFields(string[] fields) => _fields = fields;

    public string Code => _fields[0];

    public string Department => _fields[2];

    public bool HasValidCode => Code.StartsWith(CodePrefix, StringComparison.Ordinal);

    public bool HasJustification => !string.IsNullOrWhiteSpace(_fields[4]);

    public static bool TrySplit(string line, out RequestFields fields)
    {
        ArgumentNullException.ThrowIfNull(line);
        var parts = line.Split(Separator);
        fields = new RequestFields(parts);
        return parts.Length == Count;
    }

    /// <summary>NumberStyles.Any, like the legacy code: " 75,000 " is a valid budget. Must be positive.</summary>
    public bool TryGetBudget(out decimal budget) =>
        decimal.TryParse(_fields[3], NumberStyles.Any, CultureInfo.InvariantCulture, out budget) && budget > 0;
}
