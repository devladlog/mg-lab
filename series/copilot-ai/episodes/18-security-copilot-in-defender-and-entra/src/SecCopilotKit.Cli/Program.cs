using System.Globalization;
using System.Text.Json.Nodes;
using Contoso.SecCopilotKit;
using Kusto.Language;

namespace Contoso.SecCopilotKit.Cli;

public static class Program
{
    private const string Usage = """
        seckit: check, price and pre-flight Microsoft Security Copilot plugins and agents (offline, no sign-in)

          seckit check <manifest.yaml>
          seckit render <manifest.yaml> <SkillName> <name=value> [<name=value> ...]
          seckit scu provisioned --scus <n> --hours <h> [--overage-used <scus>]
          seckit scu inclusion --licences <n> --used <scus-per-month>
          seckit preflight <conditional-access-optimization|phishing-triage> <tenant-profile.json>
        """;

    public static int Main(string[] args) => Run(args, Console.Out, Console.Error);

    public static int Run(string[] args, TextWriter @out, TextWriter err)
    {
        try
        {
            if (args.Length == 0 || args[0] is "-h" or "--help") { @out.WriteLine(Usage); return args.Length == 0 ? 2 : 0; }
            return args[0] switch
            {
                "check" => Check(args, @out),
                "render" => Render(args, @out),
                "scu" => Scu(args, @out),
                "preflight" => PreflightCmd(args, @out),
                _ => Fail(err, $"Unknown command '{args[0]}'.\n{Usage}"),
            };
        }
        catch (Exception e) when (e is ArgumentException or FileNotFoundException or FormatException or KeyNotFoundException or InvalidOperationException)
        {
            return Fail(err, e.Message);
        }
    }

    private static int Fail(TextWriter err, string message) { err.WriteLine(message); return 2; }

    private static int Check(string[] a, TextWriter o)
    {
        if (a.Length != 2) throw new ArgumentException("Usage: seckit check <manifest.yaml>");
        var findings = ManifestChecker.CheckText(File.ReadAllText(a[1]));
        foreach (var f in findings.OrderByDescending(x => x.Severity)) o.WriteLine(f);
        o.WriteLine($"{findings.Errors()} error(s), {findings.Warnings()} warning(s)");
        return findings.Errors() > 0 ? 1 : 0;
    }

    private static int Render(string[] a, TextWriter o)
    {
        if (a.Length < 4) throw new ArgumentException("Usage: seckit render <manifest.yaml> <SkillName> <name=value> ...");
        var root = YamlLoader.Load(a[1]);
        var skill = (root["SkillGroups"] as JsonArray ?? new JsonArray())
            .OfType<JsonObject>().Where(g => (string?)g["Format"] == "KQL")
            .SelectMany(g => (g["Skills"] as JsonArray ?? new JsonArray()).OfType<JsonObject>())
            .FirstOrDefault(s => (string?)s["Name"] == a[2]) ?? throw new KeyNotFoundException($"No KQL skill named '{a[2]}'.");
        var template = (string?)skill["Settings"]?["Template"] ?? throw new FormatException("The skill has no inline Template.");
        var values = a.Skip(3).Select(kv => kv.Split('=', 2)).ToDictionary(p => p[0], p => p.Length == 2 ? p[1] : throw new FormatException("Use name=value."));
        var query = TemplateRenderer.Render(template, values);
        o.WriteLine(query);
        var diags = KustoCode.ParseAndAnalyze(query, HuntingSchema.Globals).GetDiagnostics().Where(d => d.Severity == "Error").ToList();
        o.WriteLine(diags.Count == 0 ? "-- parses and analyses without errors" : "-- " + string.Join("; ", diags.Select(d => d.Message)));
        return diags.Count == 0 ? 0 : 1;
    }

    private static int Scu(string[] a, TextWriter o)
    {
        if (a.Length < 2) throw new ArgumentException("Usage: seckit scu provisioned|inclusion ...");
        var opt = Options(a.Skip(2));
        var inv = CultureInfo.InvariantCulture;
        switch (a[1])
        {
            case "provisioned":
            {
                var e = ScuEstimator.Provisioned((int)Num(opt, "scus"), Num(opt, "hours"), opt.ContainsKey("overage-used") ? Num(opt, "overage-used") : 0);
                o.WriteLine($"provisioned: {e.Scus} SCU x {e.Hours.ToString("0.#", inv)} h x {ScuEstimator.ProvisionedUsdPerScuHour.ToString("0.00", inv)} USD = {e.ProvisionedUsd.ToString("0.00", inv)} USD");
                o.WriteLine($"overage:     {e.OverageScus.ToString("0.0", inv)} SCU x {ScuEstimator.OverageUsdPerScu.ToString("0.00", inv)} USD = {e.OverageUsd.ToString("0.00", inv)} USD");
                o.WriteLine($"total:       {e.TotalUsd.ToString("0.00", inv)} USD");
                return 0;
            }
            case "inclusion":
            {
                var e = ScuEstimator.Inclusion((int)Num(opt, "licences"), Num(opt, "used"));
                o.WriteLine($"included:    {e.IncludedScus.ToString("0.#", inv)} SCU a month ({ScuEstimator.InclusionScusPer1000Licences:0} per 1,000 licences, cap {ScuEstimator.InclusionCapScus:0})");
                o.WriteLine($"used:        {e.UsedScus.ToString("0.#", inv)} SCU; covered {e.CoveredScus.ToString("0.#", inv)}; beyond {e.BeyondScus.ToString("0.#", inv)}");
                o.WriteLine($"beyond, at the announced pay-as-you-go rate of {ScuEstimator.OverageUsdPerScu:0.00} USD: {e.BeyondUsdAtOverageRate.ToString("0.00", inv)} USD (Learn: throttling and this option start at a future date)");
                return 0;
            }
            default: throw new ArgumentException("Usage: seckit scu provisioned|inclusion ...");
        }
    }

    private static int PreflightCmd(string[] a, TextWriter o)
    {
        if (a.Length != 3) throw new ArgumentException("Usage: seckit preflight <agent> <tenant-profile.json>");
        var profile = TenantProfile.Parse(File.ReadAllText(a[2]));
        var items = Preflight.Check(a[1], profile);
        foreach (var i in items) o.WriteLine($"{i.State.ToString().ToUpperInvariant(),-8} {i.Requirement}  [{i.Source}]");
        var ready = Preflight.Ready(items);
        o.WriteLine(ready ? "ready" : $"not ready: {items.Count(i => i.State != CheckState.Met)} item(s) to fix");
        return ready ? 0 : 1;
    }

    private static Dictionary<string, string> Options(IEnumerable<string> args)
    {
        var d = new Dictionary<string, string>(StringComparer.Ordinal);
        var list = args.ToList();
        for (int i = 0; i < list.Count; i += 2)
        {
            if (!list[i].StartsWith("--") || i + 1 >= list.Count) throw new ArgumentException($"Expected --name value, got '{list[i]}'.");
            d[list[i][2..]] = list[i + 1];
        }
        return d;
    }

    private static double Num(Dictionary<string, string> o, string name) =>
        o.TryGetValue(name, out var v) && double.TryParse(v, NumberStyles.Float, CultureInfo.InvariantCulture, out var n)
            ? n : throw new ArgumentException($"--{name} <number> is required.");
}
