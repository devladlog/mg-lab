using MGLab.DaxLint;
using Microsoft.AnalysisServices.Tabular;
using Xunit;

public class DaxTextTests
{
    [Fact]
    public void Strips_line_and_block_comments_and_keeps_string_literals_out()
    {
        var strings = new List<string>();
        var s = DaxText.StripStringsAndComments("DIVIDE([A], [B]) // a / b\n/* x / y */ \"Sales / unit\"", strings);
        Assert.DoesNotContain("/", s);
        Assert.Equal(new[] { "Sales / unit" }, strings);
    }

    [Fact]
    public void Finds_qualified_quoted_and_unqualified_references()
    {
        var refs = DaxText.References("SUMX(Sales, Sales[Quantity]) + 'Product Line'[Name] - [Margin]").ToList();
        Assert.Equal(new (string?, string)[] { ("Sales", "Quantity"), ("Product Line", "Name"), (null, "Margin") },
            refs.Select(r => (r.Table, r.Name)));
    }

    [Fact]
    public void Splits_top_level_arguments_only()
    {
        var args = DaxText.CallArguments("TOTALYTD(CALCULATE([X], ALL(T)), 'Date'[Date])", "TOTALYTD").Single();
        Assert.Equal(new[] { "CALCULATE([X], ALL(T))", "'Date'[Date]" }, args);
    }

    [Theory]
    [InlineData("[A] / [B]", 1)]
    [InlineData("[A] / 3", 0)]
    [InlineData("[A] /  .5", 0)]
    [InlineData("[Sales/Unit] * 2", 0)]
    [InlineData("'Odd/Table'[X] * 2", 0)]
    public void Detects_divisions_by_non_constants(string dax, int expected) =>
        Assert.Equal(expected, DaxText.NonConstantDivisions(DaxText.StripStringsAndComments(dax)).Count());
}

public class ModelTests
{
    static readonly string Episode = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "../../../../.."));
    static readonly string ModelDir = Path.Combine(Episode, "src/ContosoSales.SemanticModel/definition");
    static readonly string Queries = Path.Combine(Episode, "src/ContosoSales.SemanticModel/DAXQueries");
    static readonly string BadDir = Path.Combine(Episode, "tests/fixtures/bad-measures/definition");
    static readonly string BadQueries = Path.Combine(Episode, "tests/fixtures/bad-measures/queries");

    static Model Load() => Linter.Load(ModelDir);
    static Measure M(string name) => Load().Tables["Sales"].Measures[name];

    [Fact]
    public void Episode_model_and_saved_queries_have_no_findings()
    {
        var r = Linter.Lint(Load(), Queries);
        Assert.Empty(r.Findings);
        Assert.Equal(14, r.Measures);
        Assert.Equal(5, r.Queries);
        Assert.Equal(Linter.Rules.Count, r.PassedRules.Count);
    }

    [Theory]
    [InlineData("Base", 6)]
    [InlineData("Time intelligence", 5)]
    [InlineData("Ranking and share", 2)]
    [InlineData("Context transition", 1)]
    public void Measures_are_organised_in_display_folders(string folder, int count) =>
        Assert.Equal(count, Load().Tables["Sales"].Measures.Count(m => m.DisplayFolder == folder));

    [Fact]
    public void Multi_line_measures_keep_their_variables()
    {
        var yoy = M("Sales YoY %").Expression;
        Assert.Contains("VAR CurrentSales = [Sales Amount]", yoy);
        Assert.Contains("VAR PriorSales = [Sales PY]", yoy);
        Assert.Contains("IF(NOT ISBLANK(CurrentSales), DIVIDE(CurrentSales - PriorSales, PriorSales))", yoy);
    }

    [Fact]
    public void Last_three_months_uses_explicit_month_boundaries()
    {
        var e = M("Sales Last 3 Months").Expression;
        Assert.Contains("EOMONTH(LastDate, -3) + 1", e);
        Assert.Contains("DATESBETWEEN('Date'[Date], FirstDate, LastDate)", e);
    }

    [Fact]
    public void Ship_date_measure_activates_the_inactive_relationship()
    {
        var rel = Load().Relationships.OfType<SingleColumnRelationship>().Single(r => r.FromColumn.Name == "Ship Date");
        Assert.False(rel.IsActive);
        Assert.Contains("USERELATIONSHIP(Sales[Ship Date], 'Date'[Date])", M("Sales by Ship Date").Expression);
    }

    [Fact]
    public void Customers_over_1K_relies_on_a_measure_reference_inside_FILTER()
    {
        var e = M("Customers Over 1K").Expression;
        Assert.Contains("FILTER(", e);
        Assert.Contains("[Sales Amount] > 1000", e);      // measure -> automatic context transition
        Assert.DoesNotContain("SUMX", e);
    }

    [Fact]
    public void Multi_line_description_is_read_from_triple_slash_comments()
    {
        var d = M("Customers Over 1K").Description;
        Assert.Contains("context transition", d);
        Assert.Contains("\n", d);
    }

    [Fact]
    public void Bad_fixture_hits_every_error_rule()
    {
        var r = Linter.Lint(Linter.Load(BadDir), BadQueries);
        foreach (var rule in new[] { "DX005", "DX007", "DX008", "DX009" })
            Assert.Contains(r.Findings, f => f.Rule == rule && f.Severity == Severity.Error);
        Assert.Equal(5, r.Errors);
    }

    [Fact]
    public void Bad_fixture_hits_every_warning_rule_and_nothing_else()
    {
        var r = Linter.Lint(Linter.Load(BadDir), BadQueries);
        var warnings = r.Findings.Where(f => f.Severity == Severity.Warning).Select(f => (f.Rule, f.Where)).OrderBy(x => x).ToList();
        Assert.Equal(new[]
        {
            ("DX001", "[Margin Pct]"), ("DX003", "[Qty]"), ("DX004", "[Double]"),
            ("DX006", "[Margin Pct]"), ("DX008", "[Ship Sales]"),
        }, warnings);
    }

    [Fact]
    public void Slash_in_a_comment_and_division_by_a_constant_are_not_flagged()
    {
        var r = Linter.Lint(Linter.Load(BadDir));
        Assert.DoesNotContain(r.Findings, f => f.Rule == "DX006" && (f.Where == "[Margin Share]" || f.Where == "[Half]"));
    }

    [Fact]
    public void Query_measures_and_result_columns_are_allowed_in_queries()
    {
        var r = Linter.Lint(Linter.Load(BadDir), BadQueries);
        var q = r.Findings.Where(f => f.Where == "bad.dax").ToList();
        var only = Assert.Single(q);
        Assert.Contains("[Profit]", only.Message);
    }

    [Fact]
    public void Committed_TMDL_view_script_is_up_to_date()
    {
        var committed = File.ReadAllText(Path.Combine(Episode, "src/ContosoSales.SemanticModel/TMDLScripts/create-model.tmdl"));
        Assert.Equal(Linter.CreateOrReplaceScript(Load()), committed);
        Assert.StartsWith("createOrReplace\n", committed);
        Assert.Contains("\t\tmeasure 'Customers Over 1K' =", committed);
    }
}
