using System.Globalization;
using Contoso.Portfolio;
using Microsoft.EntityFrameworkCore;

// usage: dotnet run --project src/Contoso.Portfolio.Cli -- <report | import FILE | deferred | sql>
CultureInfo.CurrentCulture = CultureInfo.InvariantCulture;   // same number format on every machine
var mode = args.FirstOrDefault() ?? "report";

switch (mode)
{
    case "report": Report(); break;
    case "import": ImportFile(args.ElementAtOrDefault(1) ?? "samples/requests.csv"); break;
    case "deferred": DeferredDemo(); break;
    case "sql": await SqlDemoAsync(); break;
    default:
        await Console.Error.WriteLineAsync($"Unknown mode '{mode}'. Use report, import, deferred or sql.");
        return 2;
}
return 0;

static void Report()
{
    var requests = SampleData.Requests;
    Console.WriteLine("== Totals by department (AggregateBy, .NET 9)");
    foreach (var t in Reports.TotalsByDepartment(requests))
        Console.WriteLine($"  {t.DepartmentCode,-4} {t.Count,2} requests  {t.Total,10:N0} EUR");

    Console.WriteLine("\n== Every department, also without requests (LeftJoin, .NET 10)");
    foreach (var line in Reports.AllDepartments(SampleData.Departments, requests))
        Console.WriteLine($"  {line.Name,-24} {line.Count,2}  {line.Total,10:N0} EUR");

    Console.WriteLine("\n== Requests by status (CountBy, .NET 9)");
    Console.WriteLine("  " + string.Join("  ", Reports.CountByStatus(requests).OrderBy(kv => kv.Key).Select(kv => $"{kv.Key}={kv.Value}")));

    Console.WriteLine("\n== Top 3 by budget (Index, .NET 9)");
    foreach (var r in Reports.Top(requests, 3))
        Console.WriteLine($"  #{r.Rank}  {r.Code}  {r.Budget,10:N0} EUR  {r.Title}");

    Console.WriteLine("\n== Submitted and High priority (a rule passed in as a function)");
    foreach (var r in requests.Needing(r => Policy.PriorityFor(r.Budget) == Priority.High))
        Console.WriteLine($"  {r.Code}  {r.Budget,10:N0} EUR  {r.Title}");

    var methodSyntax = Reports.TotalsByDepartment(requests);
    var querySyntax = Reports.TotalsByDepartmentQuerySyntax(requests);
    Console.WriteLine($"\nmethod syntax == query syntax: {methodSyntax.SequenceEqual(querySyntax)}");
}

static void ImportFile(string path)
{
    var known = SampleData.Departments.Select(d => d.Code).ToHashSet();
    var result = Import.FromCsv(File.ReadLines(path), known);
    Console.WriteLine($"== {Path.GetFileName(path)}: {result.Accepted.Count} accepted, {result.Rejected.Count} rejected");
    foreach (var r in result.Accepted)
        Console.WriteLine($"  ok    {r.Code}  {r.DepartmentCode,-4} {r.Budget,10:N0} EUR  {r.Title}");
    foreach (var r in result.Rejected)
        Console.WriteLine($"  line {r.LineNumber}: {r.Error}");
}

static void DeferredDemo()
{
    var requests = SampleData.Requests;
    Console.WriteLine("== Count(), Sum(), First() on the same query");
    Console.WriteLine($"  without ToList(): source read {Deferred.EnumerationsWithoutMaterializing(requests)} times");
    Console.WriteLine($"  with ToList():    source read {Deferred.EnumerationsWithToList(requests)} time");

    Console.WriteLine("\n== The lambda captures the variable, not its value");
    var (before, after) = Deferred.CapturedVariable(requests);
    Console.WriteLine($"  threshold 50,000  -> big.Count() = {before}");
    Console.WriteLine($"  threshold changed to 250,000, same query object -> big.Count() = {after}");
}

static async Task SqlDemoAsync()
{
    var sql = new List<string>();
    await using var db = await PortfolioDb.CreateFreshAsync("portfolio.db", sql.Add);
    Console.WriteLine($"SQLite database: portfolio.db ({await db.Requests.CountAsync()} requests)");

    sql.Clear();
    db.ChangeTracker.Clear();
    var viaQueryable = await Queries.AtLeast(db.Requests, 50_000m).ToListAsync();
    Show("AtLeast(IQueryable<ProjectRequest>, 50,000)", viaQueryable.Count, db.ChangeTracker.Entries().Count(), sql);

    sql.Clear();
    db.ChangeTracker.Clear();
    var viaEnumerable = Queries.AtLeast((IEnumerable<ProjectRequest>)db.Requests, 50_000m).ToList();
    Show("AtLeast(IEnumerable<ProjectRequest>, 50,000)", viaEnumerable.Count, db.ChangeTracker.Entries().Count(), sql);

    sql.Clear();
    var rows = await Queries.DepartmentsWithRequests(db).ToListAsync();
    Console.WriteLine("\n== LeftJoin (.NET 10), translated by EF Core 10");
    Console.WriteLine(Indent(LastSql(sql)));
    foreach (var group in rows.GroupBy(r => r.Department))
        Console.WriteLine($"  {group.Key,-24} {group.Count(r => r.Request is not null)} requests");

    Console.WriteLine("\n== CountBy (.NET 9) on a DbSet");
    try
    {
        await Queries.CountByDepartmentUntranslatable(db).ToListAsync();
    }
    catch (InvalidOperationException ex)
    {
        Console.WriteLine($"  {ex.GetType().Name}: {Untranslatable(ex.Message)}");
    }
    sql.Clear();
    var counts = await Queries.CountByDepartment(db).ToListAsync();
    Console.WriteLine("  GroupBy + Count instead:");
    Console.WriteLine(Indent(LastSql(sql)));
    Console.WriteLine("  " + string.Join("  ", counts.Select(kv => $"{kv.Key}={kv.Value}")));

    Console.WriteLine("\n== A C# method inside Where");
    try
    {
        await Queries.StrategicUntranslatable(db).ToListAsync();
    }
    catch (InvalidOperationException ex)
    {
        Console.WriteLine($"  {ex.GetType().Name}: {Untranslatable(ex.Message)}");
    }
    var strategic = await Queries.StrategicAsync(db);
    Console.WriteLine($"  fix (filter in SQL first, then the C# rule in memory): {string.Join(", ", strategic.Select(r => r.Code))}");
}

static void Show(string label, int results, int materialized, List<string> sql)
{
    Console.WriteLine($"\n== {label}");
    Console.WriteLine(Indent(LastSql(sql)));
    Console.WriteLine($"  -> {results} results, {materialized} rows read from the database");
}

static string LastSql(List<string> sql)
{
    // LogTo message: "Executed DbCommand (..) [Parameters=[..], ...]" followed by the SQL text.
    var message = sql.LastOrDefault() ?? "";
    var lines = message.Split('\n').Select(l => l.TrimEnd()).ToList();
    var parameters = lines.FirstOrDefault()?.Split("[Parameters=[").ElementAtOrDefault(1)?.Split("],").FirstOrDefault();
    var body = string.Join('\n', lines.Skip(1).Where(l => l.Length > 0));
    return string.IsNullOrEmpty(parameters) ? body : $"-- parameters: {parameters}\n{body}";
}

static string Indent(string text) => string.Join('\n', text.Split('\n').Select(l => "    " + l));

// "The LINQ expression '...' could not be translated." on one line, without the long advice that follows.
static string Untranslatable(string message)
{
    var end = message.IndexOf("could not be translated", StringComparison.Ordinal);
    var head = end < 0 ? message : message[..(end + "could not be translated".Length)] + ".";
    return string.Join(' ', head.Split((char[])['\n', '\r', ' '], StringSplitOptions.RemoveEmptyEntries));
}
