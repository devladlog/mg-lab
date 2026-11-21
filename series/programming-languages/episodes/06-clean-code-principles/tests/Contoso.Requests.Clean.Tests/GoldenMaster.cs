using Contoso.Requests.Legacy;

namespace Contoso.Requests.Clean.Tests;

/// <summary>Same format as the CLI's golden command: "NN plain OUTPUT" / "NN mail  OUTPUT".</summary>
internal static class GoldenMaster
{
    public static string[] Inputs => File.ReadAllLines(Path.Combine(AppContext.BaseDirectory, "samples", "requests.csv"));

    public static string[] Approved =>
        File.ReadAllLines(Path.Combine(AppContext.BaseDirectory, "golden", "legacy-output.approved.txt"));

    public static string[] Record(RequestProcessor2 legacy) =>
        Format(line => legacy.Process(line, false), line => legacy.Process(line, true));

    public static string[] Record(RequestProcessor clean) =>
        Format(line => LegacyFormat.Describe(clean.Process(line)),
               line => LegacyFormat.DescribeAfterNotifying(clean.Process(line)));

    /// <summary>The "NN mode" prefix of every line that differs from the approved master.</summary>
    public static string[] DifferencesFrom(string[] actual) =>
        [.. Approved.Zip(actual).Where(pair => pair.First != pair.Second).Select(pair => pair.First[..8].TrimEnd())];

    private static string[] Format(Func<string, string> plain, Func<string, string> mail) =>
        [.. Inputs.SelectMany((line, i) => new[] { $"{i + 1:00} plain {plain(line)}", $"{i + 1:00} mail  {mail(line)}" })];
}
