using Microsoft.AnalysisServices.Tabular;
using MGLab.TmdlCheck;
using Xunit;

public class TmdlCheckTests
{
    static readonly string Src = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "../../../../../src"));
    static readonly string Definition = Path.Combine(Src, "ContosoSales.SemanticModel/definition");
    static readonly string Queries = Path.Combine(Src, "queries");

    static string CopyDefinition()
    {
        var dir = Path.Combine(Path.GetTempPath(), "tmdlcheck-" + Guid.NewGuid().ToString("N"));
        foreach (var f in Directory.GetFiles(Definition, "*", SearchOption.AllDirectories))
        {
            var target = Path.Combine(dir, Path.GetRelativePath(Definition, f));
            Directory.CreateDirectory(Path.GetDirectoryName(target)!);
            File.Copy(f, target);
        }
        return dir;
    }

    [Fact]
    public void Episode_model_loads_and_matches_every_query_file()
    {
        var findings = Checker.Check(Checker.Load(Definition), Checker.ReadQueries(Queries));
        Assert.DoesNotContain(findings, f => f.Severity == "ERROR");
    }

    [Fact]
    public void Model_has_five_import_tables_and_four_shared_expressions()
    {
        var model = Checker.Load(Definition);
        Assert.Equal(new[] { "Customer", "Date", "Product", "Sales", "Store" }, model.Tables.Select(t => t.Name).OrderBy(n => n));
        Assert.Equal(new[] { "ExportFolder", "SalesExport", "fnDimension", "fnReadExport" },
            model.Expressions.Select(e => e.Name).OrderBy(n => n, StringComparer.Ordinal));
        Assert.All(model.Tables, t => Assert.Equal(ModeType.Import, t.Partitions.Single().Mode));
        Assert.Equal(5, model.Relationships.Count);
    }

    [Fact]
    public void ExportFolder_is_a_required_text_parameter()
    {
        var e = Checker.Load(Definition).Expressions.Find("ExportFolder")!;
        Assert.Contains("IsParameterQuery = true", e.Expression);
        Assert.Contains("Type = \"Text\"", e.Expression);
        Assert.Contains("IsParameterQueryRequired = true", e.Expression);
    }

    [Fact]
    public void Loaded_tables_read_from_the_staging_query_not_from_files()
    {
        var model = Checker.Load(Definition);
        foreach (var t in model.Tables)
        {
            var m = ((MPartitionSource)t.Partitions.Single().Source).Expression;
            Assert.DoesNotContain("File.Contents", m);
            Assert.DoesNotContain("Folder.Files", m);
        }
    }

    [Fact]
    public void Edited_partition_is_reported_as_drift()
    {
        var dir = CopyDefinition();
        try
        {
            var file = Path.Combine(dir, "tables/Store.tmdl");
            File.WriteAllText(file, File.ReadAllText(file).Replace("{\"StoreName\", \"Store\"}", "{\"StoreName\", \"Shop\"}"));
            var findings = Checker.Check(Checker.Load(dir), Checker.ReadQueries(Queries));
            Assert.Contains(findings, f => f.Severity == "ERROR" && f.Message.StartsWith("Store: the model's M differs"));
        }
        finally { Directory.Delete(dir, true); }
    }

    [Fact]
    public void Query_file_missing_from_the_model_is_reported()
    {
        var queries = new Dictionary<string, string>(Checker.ReadQueries(Queries)) { ["Budget"] = "let x = 1 in x" };
        var findings = Checker.Check(Checker.Load(Definition), queries);
        Assert.Contains(findings, f => f.Severity == "ERROR" && f.Message.StartsWith("Budget.pq is not in the model"));
    }

    [Fact]
    public void TMDL_view_script_is_up_to_date_and_round_trips()
    {
        var model = Checker.Load(Definition);
        var script = Checker.CreateOrReplaceScript(model);
        var committed = File.ReadAllText(Path.Combine(Src, "ContosoSales.SemanticModel/TMDLScripts/create-model.tmdl"));
        Assert.Equal(committed, script);
        Assert.StartsWith("createOrReplace", script);
        Assert.Contains("expression SalesExport =", script);
        Assert.Contains("Table.Buffer(Newest)", script);
    }
}
