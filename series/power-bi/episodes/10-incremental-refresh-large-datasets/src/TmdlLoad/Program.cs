// tmdl-load <SemanticModel/definition folder>
// Loads a TMDL folder with the Tabular Object Model (the parser Desktop and the service use) and prints what the engine would see:
// tables with columns, measures, partitions, the incremental refresh policy of each table, parameters and other shared expressions,
// relationships, roles. Exit 1 when TOM rejects the folder. Nothing is evaluated.
using Microsoft.AnalysisServices.Tabular;

if (args.Length != 1 || !Directory.Exists(args[0]))
{
    Console.Error.WriteLine("usage: tmdl-load <SemanticModel/definition folder>");
    return 2;
}

try
{
    var model = TmdlSerializer.DeserializeDatabaseFromFolder(args[0]).Model;
    foreach (var t in model.Tables)
    {
        Console.WriteLine($"  table {t.Name,-12} {t.Columns.Count,2} columns  {t.Measures.Count,2} measures  {t.Partitions.Count} partition(s)");
        if (t.RefreshPolicy is BasicRefreshPolicy p)
            Console.WriteLine($"    refresh policy: {p.Mode}, keep {p.RollingWindowPeriods} {p.RollingWindowGranularity}(s), refresh {p.IncrementalPeriods} {p.IncrementalGranularity}(s), offset {p.IncrementalPeriodsOffset}" +
                              (string.IsNullOrEmpty(p.PollingExpression) ? "" : ", detect data changes") + $", source expression {p.SourceExpression.Split('\n').Length} line(s)");
    }
    int parameters = 0;
    foreach (var e in model.Expressions)
    {
        var isParam = e.Expression.Contains("IsParameterQuery=true", StringComparison.Ordinal) || e.Expression.Contains("IsParameterQuery = true", StringComparison.Ordinal);
        if (isParam)
        {
            parameters++;
            Console.WriteLine($"  parameter {e.Name} = {e.Expression.Split(" meta ")[0]}");
        }
        else
            Console.WriteLine($"  expression {e.Name} ({e.Expression.Split('\n').Length} lines)");
    }
    foreach (var r in model.Relationships.OfType<SingleColumnRelationship>())
        Console.WriteLine($"  relationship {r.FromColumn.Table.Name}[{r.FromColumn.Name}] -> {r.ToColumn.Table.Name}[{r.ToColumn.Name}] active={r.IsActive}");
    foreach (var role in model.Roles)
        Console.WriteLine($"  role {role.Name}: {role.TablePermissions.Count} table permission(s)");
    Console.WriteLine($"{model.Tables.Count} table(s), {parameters} parameter(s), {model.Expressions.Count - parameters} other expression(s), {model.Relationships.Count} relationship(s), {model.Roles.Count} role(s): loaded");
    return 0;
}
catch (Exception e)
{
    Console.WriteLine($"  ERROR  {e.GetType().Name}: {e.Message}");
    return 1;
}
