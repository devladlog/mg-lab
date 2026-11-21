using System.Text.RegularExpressions;
using System.Xml.Linq;

namespace ModernizationScan;

public static partial class Scanner
{
    private const string WebApplicationTypeGuid = "349c5851-65df-11da-9384-00065b846f21";
    private static readonly string[] SkipFolders = ["bin", "obj", "packages", ".git", ".vs", "node_modules", ".github"];

    [GeneratedRegex("""^Project\("\{[^}]+\}"\)\s*=\s*"(?<name>[^"]+)",\s*"(?<path>[^"]+)",\s*"\{(?<guid>[^}]+)\}"\s*$""", RegexOptions.Multiline)]
    private static partial Regex SolutionProject();

    public static Report Scan(string root)
    {
        root = Path.GetFullPath(root);
        if (!Directory.Exists(root)) throw new DirectoryNotFoundException($"not a directory: {root}");

        var warnings = new List<string>();
        var projectFiles = FindProjectFiles(root);
        if (projectFiles.Count == 0) throw new InvalidOperationException($"no .csproj or .vbproj files under {root}");

        var projects = projectFiles.Select(f => ReadProject(root, f)).OrderBy(p => p.Name, StringComparer.OrdinalIgnoreCase).ToList();
        var findings = new List<Finding>();
        foreach (var p in projects) findings.AddRange(FindingsFor(root, p));

        foreach (var sln in Directory.EnumerateFiles(root, "*.sln", SearchOption.TopDirectoryOnly))
            foreach (var (name, path) in SolutionProjects(sln))
                if (!File.Exists(Path.Combine(Path.GetDirectoryName(sln)!, path)))
                    warnings.Add($"{Path.GetFileName(sln)} lists {name} ({path}) but the file does not exist");

        var (order, cycle) = TopologicalOrder(projects);
        if (cycle.Count > 0) warnings.Add("project reference cycle: " + string.Join(", ", cycle));

        var web = projects.Any(p => p.IsWebApplication);
        var strategy = SuggestStrategy(projects, order, web);
        var score = Score(projects, findings);
        var readiness = score <= 4 ? "low effort" : score <= 12 ? "medium effort" : "high effort";
        return new Report(root, projects, order, findings, strategy, score, readiness, warnings);
    }

    private static List<string> FindProjectFiles(string root) =>
        Directory.EnumerateFiles(root, "*.*", SearchOption.AllDirectories)
            .Where(f => f.EndsWith(".csproj", StringComparison.OrdinalIgnoreCase) || f.EndsWith(".vbproj", StringComparison.OrdinalIgnoreCase))
            .Where(f => !IsSkipped(root, f))
            .OrderBy(f => f, StringComparer.Ordinal)
            .ToList();

    private static bool IsSkipped(string root, string file) =>
        Path.GetRelativePath(root, file).Split(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar)
            .SkipLast(1).Any(part => SkipFolders.Contains(part, StringComparer.OrdinalIgnoreCase));

    public static ProjectInfo ReadProject(string root, string file)
    {
        var doc = XDocument.Load(file);
        var proj = doc.Root ?? throw new InvalidDataException($"{file}: empty project file");
        IEnumerable<XElement> All(string name) => proj.Descendants().Where(e => e.Name.LocalName == name);
        string? Prop(string name) => All(name).Select(e => e.Value.Trim()).FirstOrDefault(v => v.Length > 0);

        var isSdk = proj.Attribute("Sdk") is not null || All("Import").Any(i => (string?)i.Attribute("Sdk") is not null);
        var tfm = Prop("TargetFramework") ?? Prop("TargetFrameworks");
        if (tfm is null)
        {
            var v = Prop("TargetFrameworkVersion"); // v4.7.2
            tfm = v is null ? "unknown" : "net" + v.TrimStart('v').Replace(".", "");
        }

        var dir = Path.GetDirectoryName(file)!;
        var packagesConfig = Path.Combine(dir, "packages.config");
        var packages = new List<PackageRef>();
        foreach (var pr in All("PackageReference"))
        {
            var id = (string?)pr.Attribute("Include") ?? (string?)pr.Attribute("Update");
            if (id is null) continue;
            var version = (string?)pr.Attribute("Version") ?? pr.Elements().FirstOrDefault(e => e.Name.LocalName == "Version")?.Value ?? "";
            packages.Add(new PackageRef(id, version));
        }
        var usesPackagesConfig = File.Exists(packagesConfig);
        if (usesPackagesConfig)
        {
            foreach (var p in XDocument.Load(packagesConfig).Descendants().Where(e => e.Name.LocalName == "package"))
                packages.Add(new PackageRef((string?)p.Attribute("id") ?? "", (string?)p.Attribute("version") ?? ""));
        }

        var refs = All("ProjectReference")
            .Select(r => (string?)r.Attribute("Include"))
            .Where(r => r is not null)
            .Select(r => Path.GetFileNameWithoutExtension(r!.Replace('\\', '/')))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .OrderBy(r => r, StringComparer.OrdinalIgnoreCase)
            .ToList();

        var typeGuids = Prop("ProjectTypeGuids") ?? "";
        var isWeb = typeGuids.Contains(WebApplicationTypeGuid, StringComparison.OrdinalIgnoreCase)
                    || (!isSdk && All("Import").Any(i => ((string?)i.Attribute("Project") ?? "").Contains("WebApplication.targets", StringComparison.OrdinalIgnoreCase)));

        return new ProjectInfo(
            Path.GetFileNameWithoutExtension(file),
            Path.GetRelativePath(root, file).Replace('\\', '/'),
            isSdk, tfm, usesPackagesConfig, isWeb, refs,
            packages.DistinctBy(p => p.Id, StringComparer.OrdinalIgnoreCase).OrderBy(p => p.Id, StringComparer.OrdinalIgnoreCase).ToList());
    }

    public static IEnumerable<Finding> FindingsFor(string root, ProjectInfo p)
    {
        if (!p.IsSdkStyle)
            yield return new Finding(p.Name, "project", "legacy (non-SDK-style) project file", p.Path, Rules.SdkStyleScenario, "The agent converts it during the version upgrade; it can also run on its own.");
        if (p.UsesPackagesConfig)
            yield return new Finding(p.Name, "project", "packages.config", Path.GetDirectoryName(p.Path)?.Replace('\\', '/') + "/packages.config", "Converting to SDK-style (skill): packages.config to PackageReference", "");
        if (Rules.OldFramework(p.TargetFramework))
            yield return new Finding(p.Name, "project", $"targets {p.TargetFramework}, an old .NET Framework", p.Path, null, "Learn's sample (4.5): Visual Studio offers to retarget to 4.8 on open; commit that retarget first.");
        if (p.IsWebApplication)
            yield return new Finding(p.Name, "project", "ASP.NET (System.Web) web application", p.Path, "Upgrading ASP.NET Framework to Core (skill)", "Orchestrates the MVC skills; side-by-side or in-place is an option in upgrade-options.md.");

        foreach (var pkg in p.Packages)
        {
            var rule = Rules.Packages.FirstOrDefault(r => pkg.Id.Equals(r.IdPrefix, StringComparison.OrdinalIgnoreCase));
            if (rule is not null)
                yield return new Finding(p.Name, "package", $"{rule.What} {pkg.Version}".Trim(), pkg.Id, rule.Capability, rule.Note);
        }

        var dir = Path.GetDirectoryName(Path.Combine(root, p.Path))!;
        var sources = Directory.EnumerateFiles(dir, "*.*", SearchOption.AllDirectories)
            .Where(f => !IsSkipped(dir, f))
            .Where(f => f.EndsWith(".cs", StringComparison.OrdinalIgnoreCase) || f.EndsWith(".cshtml", StringComparison.OrdinalIgnoreCase)
                        || f.EndsWith(".config", StringComparison.OrdinalIgnoreCase) || f.EndsWith(".asax", StringComparison.OrdinalIgnoreCase)
                        || f.EndsWith(".edmx", StringComparison.OrdinalIgnoreCase))
            .OrderBy(f => f, StringComparer.Ordinal)
            .ToList();

        foreach (var f in sources)
        {
            var rel = Path.GetRelativePath(root, f).Replace('\\', '/');
            var ext = Path.GetExtension(f).ToLowerInvariant();
            if (ext == ".asax")
            {
                yield return new Finding(p.Name, "code", "Global.asax", rel, "Upgrading Global.asax (skill)", "Moves to Program.cs and middleware.");
                continue;
            }
            if (ext == ".edmx")
            {
                yield return new Finding(p.Name, "code", "EDMX model", rel, "Upgrading EDMX to Code-First (skill)", "");
                continue;
            }
            if (Path.GetFileName(f).Equals("packages.config", StringComparison.OrdinalIgnoreCase)) continue;
            var lines = File.ReadAllLines(f);
            foreach (var rule in Rules.Code.Where(r => r.Extensions.Contains(ext)))
            {
                // one finding per file and rule: the first matching line is the evidence
                var idx = Array.FindIndex(lines, l => rule.Pattern.IsMatch(l));
                if (idx < 0) continue;
                yield return new Finding(p.Name, "code", rule.What, $"{rel}:{idx + 1}", rule.Capability, rule.Note);
            }
        }
    }

    public static (IReadOnlyList<string> Order, IReadOnlyList<string> Cycle) TopologicalOrder(IReadOnlyList<ProjectInfo> projects)
    {
        var names = projects.Select(p => p.Name).ToHashSet(StringComparer.OrdinalIgnoreCase);
        var deps = projects.ToDictionary(p => p.Name, p => p.ProjectReferences.Where(names.Contains).ToHashSet(StringComparer.OrdinalIgnoreCase), StringComparer.OrdinalIgnoreCase);
        var order = new List<string>();
        var remaining = new HashSet<string>(deps.Keys, StringComparer.OrdinalIgnoreCase);
        while (remaining.Count > 0)
        {
            // leaves first: projects whose references are all already upgraded
            var ready = remaining.Where(n => deps[n].All(d => !remaining.Contains(d))).OrderBy(n => n, StringComparer.OrdinalIgnoreCase).ToList();
            if (ready.Count == 0) return (order, remaining.OrderBy(n => n, StringComparer.OrdinalIgnoreCase).ToList());
            order.AddRange(ready);
            foreach (var n in ready) remaining.Remove(n);
        }
        return (order, []);
    }

    private static string SuggestStrategy(IReadOnlyList<ProjectInfo> projects, IReadOnlyList<string> order, bool web)
    {
        if (projects.Count <= 3 && !web)
            return "all-at-once: a small solution without a web app. Learn lists all-at-once for small, simple solutions";
        if (web || projects.Count >= 4)
            return "bottom-up: libraries first, the web application last. Learn lists bottom-up for larger solutions with a dependency graph";
        return "top-down or bottom-up: let the agent recommend one in upgrade-options.md";
    }

    private static int Score(IReadOnlyList<ProjectInfo> projects, IReadOnlyList<Finding> findings)
    {
        // Our own heuristic, not a Microsoft measure: project format work is cheap, web and library swaps are not.
        var score = 0;
        foreach (var f in findings)
        {
            score += f.Kind switch
            {
                "project" when f.What.StartsWith("ASP.NET", StringComparison.Ordinal) => 4,
                "project" => 1,
                "package" => 2,
                _ => 1,
            };
        }
        return score;
    }

    public static IReadOnlyList<(string Name, string Path)> SolutionProjects(string slnPath)
    {
        var text = File.ReadAllText(slnPath);
        return SolutionProject().Matches(text)
            .Select(m => (m.Groups["name"].Value, m.Groups["path"].Value.Replace('\\', '/')))
            .Where(p => p.Item2.EndsWith("proj", StringComparison.OrdinalIgnoreCase))
            .ToList();
    }
}
