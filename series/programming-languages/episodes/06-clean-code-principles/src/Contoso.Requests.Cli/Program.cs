using System.Globalization;
using Contoso.Requests.Clean;
using Contoso.Requests.Legacy;

// Usage (from the episode folder):
//   dotnet run --project src/Contoso.Requests.Cli -- process samples/requests.csv
//   dotnet run --project src/Contoso.Requests.Cli -- golden  samples/requests.csv > golden/legacy-output.approved.txt
//   dotnet run --project src/Contoso.Requests.Cli -- compare samples/requests.csv [--rounding AwayFromZero]
CultureInfo.CurrentCulture = CultureInfo.InvariantCulture;

if (args.Length < 2)
{
    Console.Error.WriteLine("usage: process|golden|compare FILE [--rounding ToEven|AwayFromZero]");
    return 2;
}

var lines = File.ReadAllLines(args[1]);
var rounding = args.Length == 4 && args[2] == "--rounding" ? Enum.Parse<MidpointRounding>(args[3]) : MidpointRounding.ToEven;

return args[0] switch
{
    "process" => Commands.Process(lines),
    "golden" => Commands.Golden(lines),
    "compare" => Commands.Compare(lines, rounding),
    _ => 2,
};

internal static class Commands
{
    public static int Process(string[] lines)
    {
        var processor = new RequestProcessor();
        foreach (var (line, number) in lines.Select((l, i) => (l, i + 1)))
        {
            Console.WriteLine($"{number:00}  {Explain(processor.Process(line))}");
        }

        return 0;
    }

    /// <summary>Characterization: record what the legacy code does today, both modes, every line.</summary>
    public static int Golden(string[] lines)
    {
        foreach (var entry in GoldenMaster.Record(lines, new RequestProcessor2()))
        {
            Console.WriteLine(entry);
        }

        return 0;
    }

    public static int Compare(string[] lines, MidpointRounding rounding)
    {
        var legacy = GoldenMaster.Record(lines, new RequestProcessor2());
        var clean = GoldenMaster.Record(lines, new RequestProcessor(rounding));
        Console.WriteLine($"clean code rounding: {rounding}");
        Console.WriteLine($"{"line",-11} {"legacy",-50} clean");
        var differences = 0;
        for (var i = 0; i < legacy.Count; i++)
        {
            var same = legacy[i] == clean[i];
            differences += same ? 0 : 1;
            if (!same || legacy[i].Contains(" plain ", StringComparison.Ordinal))
            {
                Console.WriteLine($"{legacy[i],-62} {(same ? "same" : "DIFF  " + clean[i][9..])}");
            }
        }

        Console.WriteLine($"{lines.Length} lines x 2 modes: {legacy.Count - differences} identical, {differences} different");
        return 0;
    }

    private static string Explain(Outcome outcome) => outcome switch
    {
        Routed r => $"{r.Code}  {r.Priority,-6}  {string.Join(" -> ", r.Approvers),-34} {r.TotalWithContingency,10:N0} EUR",
        Rejected x => $"rejected: {x.Reason}",
        _ => outcome.ToString(),
    };
}

/// <summary>The golden-master format: "NN plain OUTPUT" and "NN mail  OUTPUT" for every input line.</summary>
internal static class GoldenMaster
{
    public static List<string> Record(string[] lines, RequestProcessor2 legacy) =>
        Format(lines, line => legacy.Process(line, false), line => legacy.Process(line, true));

    public static List<string> Record(string[] lines, RequestProcessor clean) =>
        Format(lines,
            line => LegacyFormat.Describe(clean.Process(line)),
            line => LegacyFormat.DescribeAfterNotifying(clean.Process(line)));

    private static List<string> Format(string[] lines, Func<string, string> plain, Func<string, string> mail) =>
    [
        .. lines.SelectMany((line, i) => new[]
        {
            $"{i + 1:00} plain {plain(line)}",
            $"{i + 1:00} mail  {mail(line)}",
        }),
    ];
}
