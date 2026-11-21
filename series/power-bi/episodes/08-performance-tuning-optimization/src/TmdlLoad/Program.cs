// tmdl-load <SemanticModel/definition folder>
// Loads a TMDL folder with the Tabular Object Model and prints what the engine would see: tables, columns, M partitions,
// shared expressions (parameters), relationships, roles. Exit 1 when TOM rejects the folder. Nothing is evaluated.
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
        var m = t.Partitions.Select(p => p.Source as MPartitionSource).FirstOrDefault(s => s != null);
        var csv = m == null ? "calculated" : System.Text.RegularExpressions.Regex.Match(m.Expression, "DataFolder & \"\\\\([^\"]+)\"").Groups[1].Value;
        Console.WriteLine($"  table {t.Name,-13} {t.Columns.Count,2} columns  {t.Measures.Count,2} measures  {t.Partitions.Count} partition(s)  reads {csv}");
    }
    foreach (var e in model.Expressions)
        Console.WriteLine($"  parameter {e.Name} = {e.Expression.Split(" meta ")[0]}");
    foreach (var r in model.Relationships.OfType<SingleColumnRelationship>())
        Console.WriteLine($"  relationship {r.FromColumn.Table.Name}[{r.FromColumn.Name}] -> {r.ToColumn.Table.Name}[{r.ToColumn.Name}] active={r.IsActive} filter={r.CrossFilteringBehavior}");
    foreach (var role in model.Roles)
        Console.WriteLine($"  role {role.Name}: {role.TablePermissions.Count} table permission(s)");
    Console.WriteLine($"{model.Tables.Count} table(s), {model.Expressions.Count} parameter(s), {model.Relationships.Count} relationship(s), {model.Roles.Count} role(s): loaded");
    return 0;
}
catch (Exception e)
{
    Console.WriteLine($"  ERROR  {e.GetType().Name}: {e.Message}");
    return 1;
}
