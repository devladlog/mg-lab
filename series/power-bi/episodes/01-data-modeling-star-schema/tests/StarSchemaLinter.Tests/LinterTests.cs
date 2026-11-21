using MGLab.StarSchemaLinter;
using Microsoft.AnalysisServices.Tabular;
using Xunit;

public class LinterTests
{
    // tests/StarSchemaLinter.Tests/bin/Debug/net10.0 -> episode folder
    static readonly string Episode = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "../../../../.."));
    static readonly string StarModel = Path.Combine(Episode, "src/ContosoSales.SemanticModel/definition");
    static readonly string StarData = Path.Combine(Episode, "src/data/star");
    static readonly string BadModel = Path.Combine(Episode, "tests/fixtures/snowflake-model/definition");
    static readonly string BadData = Path.Combine(Episode, "tests/fixtures/data");

    static LintResult LintStar() => Linter.Lint(Linter.Load(StarModel), StarData);
    static LintResult LintBad() => Linter.Lint(Linter.Load(BadModel), BadData);

    [Fact]
    public void Star_model_loads_with_five_tables_and_five_relationships()
    {
        var model = Linter.Load(StarModel);
        Assert.Equal(new[] { "Customer", "Date", "Product", "Sales", "Store" }, model.Tables.Select(t => t.Name).OrderBy(n => n));
        Assert.Equal(5, model.Relationships.Count);
    }

    [Fact]
    public void Star_model_has_no_findings_at_all()
    {
        var r = LintStar();
        Assert.Empty(r.Findings);
        Assert.Equal(Linter.Rules.Count, r.PassedRules.Count);
    }

    [Fact]
    public void Star_model_classifies_one_fact_and_four_dimensions()
    {
        var r = LintStar();
        Assert.Equal(new[] { "Sales" }, r.FactTables);
        Assert.Equal(new[] { "Customer", "Date", "Product", "Store" }, r.DimensionTables);
    }

    [Fact]
    public void Ship_date_is_a_role_playing_inactive_relationship()
    {
        var model = Linter.Load(StarModel);
        var ship = model.Relationships.OfType<SingleColumnRelationship>().Single(r => r.FromColumn.Name == "Ship Date");
        Assert.False(ship.IsActive);
        Assert.Equal("Date", ship.ToTable.Name);
        Assert.Equal(1, LintStar().InactiveRelationships);
    }

    [Fact]
    public void Date_table_is_marked_and_month_sorts_by_month_number()
    {
        var date = Linter.Load(StarModel).Tables["Date"];
        Assert.Equal("Time", date.DataCategory);
        Assert.True(date.Columns["Date"].IsKey);
        Assert.Equal("Month Number", date.Columns["Month"].SortByColumn.Name);
        Assert.Equal("Year Month Number", date.Columns["Year Month"].SortByColumn.Name);
    }

    [Fact]
    public void Product_hierarchy_spans_category_to_product_in_one_table()
    {
        var h = Linter.Load(StarModel).Tables["Product"].Hierarchies["Product Hierarchy"];
        Assert.Equal(new[] { "Category", "Subcategory", "Product" }, h.Levels.OrderBy(l => l.Ordinal).Select(l => l.Column.Name));
    }

    [Fact]
    public void Money_columns_use_fixed_decimal()
    {
        var sales = Linter.Load(StarModel).Tables["Sales"];
        Assert.Equal(DataType.Decimal, sales.Columns["Unit Price"].DataType);
        Assert.Equal(DataType.Decimal, sales.Columns["Unit Cost"].DataType);
    }

    [Fact]
    public void Margin_percent_uses_DIVIDE_not_the_slash_operator()
    {
        var m = Linter.Load(StarModel).Tables["Sales"].Measures["Margin %"];
        Assert.StartsWith("DIVIDE(", m.Expression);
        Assert.DoesNotContain("/", m.Expression);
    }

    [Fact]
    public void Bad_model_flags_the_snowflake_chain()
    {
        var snow = LintBad().Findings.Where(f => f.Rule == "SS003").Select(f => f.Message).ToList();
        Assert.Contains(snow, m => m.Contains("Product filters through Subcategory"));
        Assert.Contains(snow, m => m.Contains("Subcategory filters through Category"));
    }

    [Fact]
    public void Bad_model_flags_bidirectional_and_many_to_many()
    {
        var r = LintBad();
        Assert.Contains(r.Findings, f => f.Rule == "SS002" && f.Message.Contains("Sales[CustomerKey]"));
        Assert.Contains(r.Findings, f => f.Rule == "SS001" && f.Severity == Severity.Error && f.Message.Contains("Budget"));
    }

    [Fact]
    public void Bad_model_flags_visible_and_summarized_keys()
    {
        var r = LintBad();
        Assert.Contains(r.Findings, f => f.Rule == "SS004" && f.Message.Contains("Sales[ProductKey]"));
        Assert.Contains(r.Findings, f => f.Rule == "SS004" && f.Message.Contains("Product[SubcategoryKey]"));
        Assert.Contains(r.Findings, f => f.Rule == "SS005" && f.Message.Contains("Sales[ProductKey]"));
    }

    [Fact]
    public void Bad_model_flags_missing_date_table_format_strings_and_implicit_measures()
    {
        var r = LintBad();
        Assert.Contains(r.Findings, f => f.Rule == "SS006" && f.Severity == Severity.Error);
        Assert.Contains(r.Findings, f => f.Rule == "SS007" && f.Message.Contains("[Total]"));
        Assert.Contains(r.Findings, f => f.Rule == "SS008");
    }

    [Fact]
    public void Bad_model_flags_a_source_column_that_is_not_in_the_csv()
    {
        var r = LintBad();
        var f = Assert.Single(r.Findings, f => f.Rule == "SS009");
        Assert.Contains("SalesAmount", f.Message);
    }

    [Fact]
    public void Bad_model_has_errors_so_the_cli_would_fail_the_build()
    {
        var r = LintBad();
        Assert.True(r.Errors >= 3);
        Assert.DoesNotContain("SS003", r.PassedRules);
    }

    [Fact]
    public void Script_is_a_createOrReplace_with_every_table_and_relationship()
    {
        var model = Linter.Load(StarModel);
        var script = Linter.CreateOrReplaceScript(model);
        Assert.StartsWith("createOrReplace\n", script);
        foreach (var t in model.Tables) Assert.Contains($"\ttable {t.Name}\n", script);
        Assert.Equal(5, script.Split('\n').Count(l => l.StartsWith("\trelationship ")));
        Assert.Contains("\texpression DataFolder", script);
    }

    [Fact]
    public void Committed_TMDL_view_script_is_up_to_date()
    {
        var committed = File.ReadAllText(Path.Combine(Episode, "src/ContosoSales.SemanticModel/TMDLScripts/create-model.tmdl"));
        Assert.Equal(Linter.CreateOrReplaceScript(Linter.Load(StarModel)), committed);
    }

    [Fact]
    public void Script_body_parses_back_into_the_same_model()
    {
        // Drop the command line, dedent one tab and let TOM parse the objects again.
        var script = Linter.CreateOrReplaceScript(Linter.Load(StarModel));
        var body = string.Join("\n", script.Split('\n').Skip(1).Select(l => l.StartsWith('\t') ? l[1..] : l));
        var dir = Directory.CreateTempSubdirectory("tmdl-script-");
        try
        {
            File.WriteAllText(Path.Combine(dir.FullName, "database.tmdl"), "database Roundtrip\n\tcompatibilityLevel: 1600\n");
            File.WriteAllText(Path.Combine(dir.FullName, "model.tmdl"), "model Model\n\tculture: en-US\n\n" + body);
            var again = Linter.Load(dir.FullName);
            Assert.Equal(5, again.Tables.Count);
            Assert.Equal(5, again.Relationships.Count);
            Assert.DoesNotContain(Linter.Lint(again, StarData).Findings, f => f.Rule != "SS008");
        }
        finally { dir.Delete(recursive: true); }
    }
}
