using System.Globalization;
using ProjectRequests.Grpc;

namespace ProjectRequests.Cli;

/// <summary>
/// One data line of the import file: either a message ready to send, or what's wrong with the line.
/// Columns: title,budget,requestedBy,department,justification (header line first, justification optional).
/// </summary>
public sealed record CsvRow(int Line, NewRequestMessage? Message, string? Error);

public static class CsvRows
{
    public static IEnumerable<CsvRow> Read(IEnumerable<string> lines)
    {
        var line = 0;
        foreach (var text in lines)
        {
            line++;
            if (line == 1 || string.IsNullOrWhiteSpace(text))
                continue;                                              // header, blank lines

            var fields = Split(text);
            if (fields.Count < 4)
            {
                yield return new CsvRow(line, null, $"expected at least 4 columns, found {fields.Count}");
                continue;
            }
            if (!decimal.TryParse(fields[1], NumberStyles.Number, CultureInfo.InvariantCulture, out var budget))
            {
                yield return new CsvRow(line, null, $"budget '{fields[1]}' is not a number");
                continue;
            }

            yield return new CsvRow(line, new NewRequestMessage
            {
                Title = fields[0],
                Budget = budget,                                       // implicit decimal -> DecimalValue
                RequestedBy = fields[2],
                DepartmentCode = fields[3],
                Justification = fields.Count > 4 && fields[4].Length > 0 ? fields[4] : null,   // StringValue: null stays null
            }, null);
        }
    }

    /// <summary>Comma-separated, with "double quotes" around fields that contain commas ("" is a quote).</summary>
    public static List<string> Split(string line)
    {
        var fields = new List<string>();
        var current = new System.Text.StringBuilder();
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
            else if (c == ',') { fields.Add(current.ToString().Trim()); current.Clear(); }
            else current.Append(c);
        }
        fields.Add(current.ToString().Trim());
        return fields;
    }
}
