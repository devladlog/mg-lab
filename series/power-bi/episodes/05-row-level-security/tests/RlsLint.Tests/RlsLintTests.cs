using MGLab.RlsLint;
using Microsoft.AnalysisServices.Tabular;
using Xunit;

namespace MGLab.RlsLint.Tests;

public class RlsLintTests
{
    static readonly string Root = FindRoot();
    static string ModelPath => Path.Combine(Root, "src", "ContosoSales.SemanticModel", "definition");
    static string LeakyPath => Path.Combine(Root, "tests", "fixtures", "leaky-model", "definition");

    static string FindRoot()
    {
        var d = new DirectoryInfo(AppContext.BaseDirectory);
        while (d is not null && !Directory.Exists(Path.Combine(d.FullName, "src", "RlsLint"))) d = d.Parent;
        return d?.FullName ?? throw new InvalidOperationException("episode folder not found");
    }

    static Model Episode() => Linter.Load(ModelPath);

    static LintResult LintEpisode(Model? m = null) => Linter.Lint(m ?? Episode(), ["Customer"]);

    [Fact]
    public void Episode_model_has_no_errors_and_only_the_userelationship_warning()
    {
        var r = LintEpisode();
        Assert.Equal(0, r.Errors);
        var w = Assert.Single(r.Findings, f => f.Severity == Severity.Warning);
        Assert.Equal("RLS009", w.Rule);
        Assert.Contains("Sales by Ship Date", w.Message);
    }

    [Fact]
    public void Head_office_is_reported_as_full_access()
    {
        var info = Assert.Single(LintEpisode().Findings, f => f.Severity == Severity.Info);
        Assert.Equal("RLS006", info.Rule);
        Assert.Contains("Head Office", info.Message);
    }

    [Fact]
    public void Store_managers_is_dynamic_and_reaches_sales_and_customer()
    {
        var role = LintEpisode().Roles.Single(r => r.Role == "Store Managers");
        Assert.True(role.Dynamic);
        Assert.Equal(["Store", "Store Access"], role.FilteredTables);
        Assert.Equal(["Customer", "Sales"], role.ReachedTables);
        Assert.Equal("Read", role.Permission);
        Assert.Equal(0, role.Members);          // members are added in the service, never in the files
    }

    [Fact]
    public void Store_filter_uses_userprincipalname_and_the_mapping_table()
    {
        var store = Episode().Roles.Find("Store Managers")!.TablePermissions.Find("Store")!;
        Assert.Contains("USERPRINCIPALNAME()", store.FilterExpression);
        Assert.Contains("'Store Access'[StoreKey]", store.FilterExpression);
        Assert.DoesNotContain("USERNAME()", store.FilterExpression.Replace("USERPRINCIPALNAME()", ""));
    }

    [Fact]
    public void Without_security_filtering_both_ways_customer_leaks()
    {
        var m = Episode();
        var rel = (SingleColumnRelationship)m.Relationships.Find("Sales to Customer")!;
        rel.SecurityFilteringBehavior = SecurityFilteringBehavior.OneDirection;
        var leak = Assert.Single(LintEpisode(m).Findings, f => f.Rule == "RLS010");
        Assert.Equal(Severity.Warning, leak.Severity);
        Assert.Contains("Store Managers", leak.Message);
        Assert.Contains("Customer", leak.Message);
    }

    [Fact]
    public void A_visible_mapping_table_is_flagged()
    {
        var m = Episode();
        m.Tables.Find("Store Access")!.IsHidden = false;
        Assert.Contains(LintEpisode(m).Findings, f => f.Rule == "RLS007" && f.Message.Contains("Store Access"));
    }

    [Fact]
    public void An_unfiltered_mapping_table_is_flagged()
    {
        var m = Episode();
        var role = m.Roles.Find("Store Managers")!;
        role.TablePermissions.Remove(role.TablePermissions.Find("Store Access")!);
        Assert.Contains(LintEpisode(m).Findings, f => f.Rule == "RLS008" && f.Message.Contains("Store Access"));
    }

    [Fact]
    public void Username_and_a_true_fallback_are_flagged()
    {
        var m = Episode();
        m.Roles.Find("Store Managers")!.TablePermissions.Find("Store")!.FilterExpression =
            "IF(USERNAME() = \"head.office\", TRUE(), [Country] = \"Portugal\")";
        var rules = LintEpisode(m).Findings.Select(f => f.Rule).ToHashSet();
        Assert.Contains("RLS004", rules);
        Assert.Contains("RLS005", rules);
    }

    [Fact]
    public void A_typo_in_a_filter_column_is_an_error()
    {
        var m = Episode();
        m.Roles.Find("Store Managers")!.TablePermissions.Find("Store")!.FilterExpression = "'Store'[Contry] = \"Spain\"";
        var e = Assert.Single(LintEpisode(m).Findings, f => f.Rule == "RLS003");
        Assert.Equal(Severity.Error, e.Severity);
        Assert.Contains("'Store'[Contry]", e.Message);
    }

    [Fact]
    public void Strings_in_filters_are_not_read_as_column_references()
    {
        var refs = Linter.References("'Store'[Store] = \"Contoso [Lisboa]\"", "Store").ToList();
        Assert.Equal([("Store", "Store")], refs);
    }

    [Fact]
    public void Bare_column_references_belong_to_the_permission_table()
    {
        var refs = Linter.References("[Country] = \"Spain\" && Store[Channel] = \"Store\"", "Store").ToList();
        Assert.Contains(("Store", "Country"), refs);
        Assert.Contains(("Store", "Channel"), refs);
    }

    [Fact]
    public void Leaky_fixture_breaks_every_rule()
    {
        var r = Linter.Lint(Linter.Load(LeakyPath), ["Product"]);
        var rules = r.Findings.Select(f => f.Rule).Distinct().Order().ToList();
        Assert.Equal(Linter.Rules.Keys.Order().ToList(), rules);
        Assert.Equal(5, r.Errors);
        Assert.Equal(7, r.Warnings);
    }

    [Fact]
    public void Userelationship_on_a_secured_table_is_an_error()
    {
        var r = Linter.Lint(Linter.Load(LeakyPath));
        var e = Assert.Single(r.Findings, f => f.Rule == "RLS009");
        Assert.Equal(Severity.Error, e.Severity);
        Assert.Contains("Region", e.Message);
    }

    [Fact]
    public void Filters_only_flow_through_active_relationships()
    {
        var m = Linter.Load(LeakyPath);
        var rels = m.Relationships.OfType<SingleColumnRelationship>().ToList();
        Assert.Equal(["Channel"], Linter.Propagate(["Channel"], rels).ToList());
        Assert.Equal(["Customer", "Region", "Sales"], Linter.Propagate(["Region"], rels).Order().ToList());
    }

    [Fact]
    public void Unknown_sensitive_table_is_an_error()
    {
        Assert.Contains(Linter.Lint(Episode(), ["Customers"]).Findings, f => f.Rule == "RLS010" && f.Severity == Severity.Error);
    }

    [Fact]
    public void Tmdl_view_script_round_trips_through_the_serializer()
    {
        var script = Linter.CreateOrReplaceScript(Episode(), ["Store Access", "Sales"], ["UpnDomain"], ["Sales to Customer"]);
        Assert.StartsWith("createOrReplace\n", script);
        Assert.Contains("\trole 'Store Managers'", script);
        Assert.Contains("\tsecurityFilteringBehavior: bothDirections", script);
        var committed = File.ReadAllText(Path.Combine(Root, "src", "ContosoSales.SemanticModel", "TMDLScripts", "add-rls.tmdl"));
        Assert.Equal(committed, script);
    }
}
