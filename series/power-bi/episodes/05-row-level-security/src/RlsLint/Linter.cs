using System.Text.RegularExpressions;
using Microsoft.AnalysisServices.Tabular;

namespace MGLab.RlsLint;

public enum Severity { Info, Warning, Error }

public sealed record Finding(string Rule, Severity Severity, string Message);

/// <summary>What one role does: the tables it filters and every table those filters reach.</summary>
public sealed record RoleSummary(
    string Role,
    string Permission,
    IReadOnlyList<string> FilteredTables,
    IReadOnlyList<string> ReachedTables,
    bool Dynamic,
    int Members);

public sealed record LintResult(IReadOnlyList<RoleSummary> Roles, IReadOnlyList<Finding> Findings)
{
    public int Errors => Findings.Count(f => f.Severity == Severity.Error);
    public int Warnings => Findings.Count(f => f.Severity == Severity.Warning);
}

/// <summary>
/// Row-level security rules for a Power BI semantic model read from TMDL with the Tabular Object Model.
/// Each rule cites the Microsoft Learn page it comes from (see README, References).
/// </summary>
public static class Linter
{
    public static readonly IReadOnlyDictionary<string, string> Rules = new Dictionary<string, string>
    {
        ["RLS001"] = "roles only grant read (modelPermission: read)",
        ["RLS002"] = "role names have no comma",
        ["RLS003"] = "filters only reference tables and columns that exist",
        ["RLS004"] = "dynamic filters use USERPRINCIPALNAME(), not USERNAME()",
        ["RLS005"] = "no filter falls back to TRUE() (unexpected identities would see every row)",
        ["RLS006"] = "roles without filters are reported (they grant every row)",
        ["RLS007"] = "security mapping tables are hidden",
        ["RLS008"] = "security mapping tables are filtered in the roles that read them",
        ["RLS009"] = "USERELATIONSHIP isn't used next to RLS",
        ["RLS010"] = "every restricting role reaches the sensitive tables",
        ["RLS011"] = "a table has at most one relationship that applies security filters in both directions",
        ["RLS012"] = "every filtered table passes its filter on through an active relationship",
    };

    static readonly Regex Identity = new(@"\b(USERPRINCIPALNAME|USERNAME|CUSTOMDATA|USEROBJECTID)\s*\(", RegexOptions.IgnoreCase);
    static readonly Regex UserName = new(@"\bUSERNAME\s*\(", RegexOptions.IgnoreCase);
    static readonly Regex TrueFallback = new(@"\bTRUE\s*\(\s*\)", RegexOptions.IgnoreCase);
    static readonly Regex QualifiedRef = new(@"(?:'((?:[^']|'')+)'|([A-Za-z_][A-Za-z0-9_]*))\s*\[([^\]]+)\]");
    static readonly Regex BareRef = new(@"(?<![\]'A-Za-z0-9_])\[([^\]]+)\]");
    static readonly Regex UseRelationship = new(
        @"USERELATIONSHIP\s*\(\s*(?:'((?:[^']|'')+)'|([A-Za-z_]\w*))\s*\[[^\]]+\]\s*,\s*(?:'((?:[^']|'')+)'|([A-Za-z_]\w*))\s*\[",
        RegexOptions.IgnoreCase);

    public static Model Load(string tmdlFolder) =>
        TmdlSerializer.DeserializeDatabaseFromFolder(tmdlFolder).Model;

    public static LintResult Lint(Model model, IEnumerable<string>? sensitiveTables = null)
    {
        var findings = new List<Finding>();
        var summaries = new List<RoleSummary>();
        var sensitive = (sensitiveTables ?? []).ToList();
        foreach (var s in sensitive.Where(s => model.Tables.Find(s) is null))
            findings.Add(new("RLS010", Severity.Error, $"--sensitive names table '{s}', which isn't in the model"));

        var rels = model.Relationships.OfType<SingleColumnRelationship>().ToList();

        // RLS011: Learn: "If a table takes part in multiple bi-directional relationships, you can only select this
        // option for one of those relationships."
        var bothWays = rels.Where(r => r.SecurityFilteringBehavior == SecurityFilteringBehavior.BothDirections).ToList();
        foreach (var t in bothWays.SelectMany(r => new[] { r.FromTable.Name, r.ToTable.Name }).GroupBy(n => n).Where(g => g.Count() > 1))
            findings.Add(new("RLS011", Severity.Error,
                $"{t.Key} takes part in {t.Count()} relationships that apply security filters in both directions; only one is allowed"));

        // Every table that a role reads through an identity function is a security mapping table.
        var mappingTables = new HashSet<string>();

        foreach (var role in model.Roles)
        {
            if (role.ModelPermission != ModelPermission.Read)
                findings.Add(new("RLS001", Severity.Error,
                    $"role '{role.Name}' has modelPermission {role.ModelPermission}; Power BI roles filter data, use read"));
            if (role.Name.Contains(','))
                findings.Add(new("RLS002", Severity.Error, $"role '{role.Name}' has a comma in its name; Power BI doesn't allow it"));

            var filtered = role.TablePermissions.Where(tp => !string.IsNullOrWhiteSpace(tp.FilterExpression)).ToList();
            bool dynamic = false;
            var readByIdentity = new HashSet<string>();

            foreach (var tp in filtered)
            {
                var expr = tp.FilterExpression;
                var where = $"role '{role.Name}', table {tp.Table.Name}";
                var refs = References(expr, tp.Table.Name).ToList();
                foreach (var (table, column) in refs)
                {
                    var t = model.Tables.Find(table);
                    if (t is null)
                        findings.Add(new("RLS003", Severity.Error, $"{where}: table '{table}' doesn't exist"));
                    else if (t.Columns.Find(column) is null && t.Measures.Find(column) is null)
                        findings.Add(new("RLS003", Severity.Error, $"{where}: '{table}'[{column}] doesn't exist"));
                }
                if (Identity.IsMatch(expr))
                {
                    // The table that holds the user names: another table the filter looks up, or the permission's own
                    // table when the filter compares one of its own columns with the identity.
                    dynamic = true;
                    var others = refs.Select(r => r.Table).Where(n => n != tp.Table.Name && model.Tables.Find(n) is not null).ToHashSet();
                    if (others.Count > 0) readByIdentity.UnionWith(others);
                    else if (refs.Count > 0) readByIdentity.Add(tp.Table.Name);
                }
                if (UserName.IsMatch(expr))
                    findings.Add(new("RLS004", Severity.Warning,
                        $"{where}: USERNAME() returns DOMAIN\\user in Desktop and the UPN in the service; use USERPRINCIPALNAME()"));
                if (TrueFallback.IsMatch(expr))
                    findings.Add(new("RLS005", Severity.Warning,
                        $"{where}: the filter can return TRUE(); test unexpected identities, they should see no rows"));
            }

            if (filtered.Count == 0)
                findings.Add(new("RLS006", Severity.Info, $"role '{role.Name}' has no filters: its members see every row"));

            foreach (var m in readByIdentity)
            {
                mappingTables.Add(m);
                if (!filtered.Any(tp => tp.Table.Name == m))
                    findings.Add(new("RLS008", Severity.Warning,
                        $"role '{role.Name}' reads mapping table {m} but doesn't filter it: members can query other users' rows " +
                        "(hidden is not secured)"));
            }

            var start = filtered.Select(tp => tp.Table.Name).ToHashSet();
            var reached = Propagate(start, rels);

            // RLS012: Learn: "RLS filters only propagate through active relationships."
            foreach (var t in start.Where(t => !mappingTables.Contains(t) && !readByIdentity.Contains(t)))
            {
                var touching = rels.Where(r => r.ToTable.Name == t || r.FromTable.Name == t).ToList();
                if (touching.Count > 0 && touching.All(r => !r.IsActive))
                    findings.Add(new("RLS012", Severity.Warning,
                        $"role '{role.Name}' filters {t}, but every relationship of {t} is inactive: the filter stops there"));
            }

            if (filtered.Count > 0)
                foreach (var s in sensitive.Where(s => model.Tables.Find(s) is not null && !reached.Contains(s)))
                    findings.Add(new("RLS010", Severity.Warning,
                        $"role '{role.Name}' doesn't reach {s}: its rows stay visible to members (filters flow from the one side to the many side " +
                        "unless the relationship applies security filters in both directions)"));

            summaries.Add(new(role.Name, role.ModelPermission.ToString(), start.OrderBy(x => x).ToList(),
                reached.Except(start).OrderBy(x => x).ToList(), dynamic, role.Members.Count));
        }

        foreach (var m in mappingTables.Order())
            if (model.Tables.Find(m) is { IsHidden: false })
                findings.Add(new("RLS007", Severity.Warning, $"mapping table {m} is visible; hide it (it holds user names)"));

        // RLS009: DAX reference: "USERELATIONSHIP cannot be used when row level security is defined for the table in which
        // the measure is included". Learn RLS limitations: with RLS, USERELATIONSHIP "might cause unexpected errors".
        if (model.Roles.Count > 0)
        {
            var secured = model.Roles.SelectMany(r => r.TablePermissions)
                .Where(tp => !string.IsNullOrWhiteSpace(tp.FilterExpression)).Select(tp => tp.Table.Name).ToHashSet();
            foreach (var t in model.Tables)
                foreach (var m in t.Measures)
                    foreach (Match u in UseRelationship.Matches(m.Expression ?? ""))
                    {
                        var a = Name(u.Groups[1], u.Groups[2]);
                        var b = Name(u.Groups[3], u.Groups[4]);
                        var hit = new[] { a, b, t.Name }.Where(secured.Contains).Distinct().ToList();
                        findings.Add(hit.Count > 0
                            ? new("RLS009", Severity.Error,
                                $"{t.Name}[{m.Name}] uses USERELATIONSHIP and RLS is defined on {string.Join(", ", hit)}: the query returns an error")
                            : new("RLS009", Severity.Warning,
                                $"{t.Name}[{m.Name}] uses USERELATIONSHIP in a model with RLS: test it under every role (Learn: may cause unexpected errors)"));
                    }
        }

        return new(summaries, findings);
    }

    /// <summary>Tables a set of filtered tables reaches: one side to many side over active relationships, and many side to
    /// one side only where the relationship applies security filters in both directions.</summary>
    public static HashSet<string> Propagate(IEnumerable<string> start, IReadOnlyList<SingleColumnRelationship> rels)
    {
        var reached = start.ToHashSet();
        bool grew = true;
        while (grew)
        {
            grew = false;
            foreach (var r in rels.Where(r => r.IsActive))
            {
                if (reached.Contains(r.ToTable.Name) && reached.Add(r.FromTable.Name)) grew = true;
                if (r.SecurityFilteringBehavior == SecurityFilteringBehavior.BothDirections
                    && reached.Contains(r.FromTable.Name) && reached.Add(r.ToTable.Name)) grew = true;
            }
        }
        return reached;
    }

    /// <summary>Column references in a DAX filter: 'Table'[Col], Table[Col], and bare [Col] (the permission's own table).</summary>
    public static IEnumerable<(string Table, string Column)> References(string expr, string ownTable)
    {
        var text = StripStrings(expr);
        foreach (Match m in QualifiedRef.Matches(text))
        {
            var table = Name(m.Groups[1], m.Groups[2]);
            if (IsFunction(table)) continue;
            yield return (table, m.Groups[3].Value);
        }
        foreach (Match m in BareRef.Matches(text))
            yield return (ownTable, m.Groups[1].Value);
    }

    static bool IsFunction(string word) => word.ToUpperInvariant() is "VALUES" or "ALL" or "DISTINCT";

    static string Name(Group quoted, Group plain) => quoted.Success ? quoted.Value.Replace("''", "'") : plain.Value;

    static string StripStrings(string expr) => Regex.Replace(expr, "\"(?:[^\"]|\"\")*\"", "\"\"");

    /// <summary>A createOrReplace script for Desktop's TMDL view with everything this episode adds to the episode 2 model.</summary>
    public static string CreateOrReplaceScript(Model model, IEnumerable<string> tables, IEnumerable<string> expressions,
        IEnumerable<string> relationships)
    {
        var parts = new List<string>();
        parts.AddRange(expressions.Select(n => TmdlSerializer.SerializeObject(model.Expressions.Find(n), qualifyObject: false)));
        parts.AddRange(tables.Select(n => TmdlSerializer.SerializeObject(model.Tables.Find(n), qualifyObject: false)));
        parts.AddRange(relationships.Select(n => TmdlSerializer.SerializeObject(model.Relationships.Find(n), qualifyObject: false)));
        parts.AddRange(model.Roles.Select(r => TmdlSerializer.SerializeObject(r, qualifyObject: false)));
        var body = string.Join("\n", parts).Replace("\r\n", "\n").Split('\n')
            .Select(line => line.Length == 0 ? line : "\t" + line);
        return "createOrReplace\n\n" + string.Join("\n", body).TrimEnd() + "\n";
    }
}
