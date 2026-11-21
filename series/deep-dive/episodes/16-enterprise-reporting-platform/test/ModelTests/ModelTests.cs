using System.Text.RegularExpressions;
using Microsoft.AnalysisServices.Tabular;
using Xunit;

namespace ModelTests;

[Collection("model")]
public class StructureTests(ModelFixture f)
{
    [Fact]
    public void Tmdl_folder_loads_with_the_official_serializer()
    {
        Assert.Equal(1601, f.Database.CompatibilityLevel);
        Assert.Equal("en-US", f.Model.Culture);
    }

    [Fact]
    public void Expected_tables_exist()
    {
        var names = f.Model.Tables.Select(t => t.Name).OrderBy(n => n).ToArray();
        Assert.Equal(new[] { "DimDate", "DimDepartment", "FactPurchaseRequest", "SecurityMap" }, names);
    }

    [Fact]
    public void Date_table_is_marked_with_a_key_column()
    {
        var date = f.Model.Tables["DimDate"];
        Assert.Equal("Time", date.DataCategory);
        var key = Assert.Single(date.Columns, c => c.IsKey);
        Assert.Equal("Date", key.Name);
        Assert.Equal(DataType.DateTime, key.DataType);
    }

    [Fact]
    public void Month_name_sorts_by_month_number()
    {
        Assert.Equal("MonthNumber", f.Model.Tables["DimDate"].Columns["Month"].SortByColumn.Name);
    }

    [Fact]
    public void Relationships_are_many_to_one_single_direction_and_active()
    {
        var rels = f.Model.Relationships.OfType<SingleColumnRelationship>().ToList();
        Assert.Equal(2, rels.Count);
        foreach (var r in rels)
        {
            Assert.Equal("FactPurchaseRequest", r.FromTable.Name);
            Assert.Equal(RelationshipEndCardinality.Many, r.FromCardinality);
            Assert.Equal(RelationshipEndCardinality.One, r.ToCardinality);
            Assert.Equal(CrossFilteringBehavior.OneDirection, r.CrossFilteringBehavior);
            Assert.True(r.IsActive);
            Assert.False(r.SecurityFilteringBehavior == SecurityFilteringBehavior.BothDirections);
        }
    }

    [Fact]
    public void Implicit_measures_are_discouraged_and_numeric_columns_are_hidden()
    {
        Assert.True(f.Model.DiscourageImplicitMeasures);
        var fact = f.Model.Tables["FactPurchaseRequest"];
        foreach (var name in new[] { "Amount", "CycleDays", "SlaBreached" })
            Assert.True(fact.Columns[name].IsHidden, $"{name} should be hidden so report authors use the measures");
    }

    [Fact]
    public void Parameters_hold_placeholders_not_real_endpoints()
    {
        foreach (var name in new[] { "SynapseServer", "UpnDomain" })
        {
            var e = f.Model.Expressions[name].Expression;
            Assert.Contains("REPLACE-WITH", e);
        }
    }
}

[Collection("model")]
public class MeasureTests(ModelFixture f)
{
    [Fact]
    public void Every_measure_has_description_format_and_folder()
    {
        Assert.NotEmpty(f.AllMeasures);
        foreach (var m in f.AllMeasures)
        {
            Assert.False(string.IsNullOrWhiteSpace(m.Description), $"[{m.Name}] has no description");
            Assert.False(string.IsNullOrWhiteSpace(m.FormatString), $"[{m.Name}] has no format string");
            Assert.False(string.IsNullOrWhiteSpace(m.DisplayFolder), $"[{m.Name}] has no display folder");
        }
    }

    [Fact]
    public void Expected_measures_exist()
    {
        var names = f.AllMeasures.Select(m => m.Name).ToHashSet();
        foreach (var n in new[] { "Requests", "Total Amount", "Open Amount", "Decided Requests", "SLA Breach Rate", "Avg Cycle Days", "Amount YTD", "Amount Prior Year" })
            Assert.Contains(n, names);
    }

    [Fact]
    public void Ratios_use_DIVIDE_not_the_slash_operator()
    {
        foreach (var m in f.AllMeasures.Where(m => m.Name.Contains("Rate")))
        {
            Assert.Contains("DIVIDE(", m.Expression);
            Assert.DoesNotContain(" / ", m.Expression);
        }
    }

    [Fact]
    public void Time_intelligence_measures_use_the_marked_date_table()
    {
        foreach (var n in new[] { "Amount YTD", "Amount Prior Year" })
            Assert.Contains("DimDate[Date]", f.Model.Tables["FactPurchaseRequest"].Measures[n].Expression);
    }

    [Fact]
    public void Every_column_and_measure_reference_in_DAX_resolves()
    {
        var problems = new List<string>();
        var measureNames = f.AllMeasures.Select(m => m.Name).ToHashSet();
        foreach (var t in f.Model.Tables)
            foreach (var m in t.Measures)
                problems.AddRange(DaxRefs.Unresolved(f.Model, measureNames, m.Expression, $"measure [{m.Name}]"));
        foreach (var role in f.Model.Roles)
            foreach (var tp in role.TablePermissions)
                problems.AddRange(DaxRefs.Unresolved(f.Model, measureNames, tp.FilterExpression, $"role {role.Name}/{tp.Name}"));
        Assert.True(problems.Count == 0, string.Join(Environment.NewLine, problems));
    }

    [Fact]
    public void The_reference_checker_catches_a_typo()
    {
        var measureNames = f.AllMeasures.Select(m => m.Name).ToHashSet();
        Assert.NotEmpty(DaxRefs.Unresolved(f.Model, measureNames, "SUM(FactPurchaseRequest[Amout])", "typo"));
        Assert.NotEmpty(DaxRefs.Unresolved(f.Model, measureNames, "[No Such Measure] + 1", "typo"));
        Assert.Empty(DaxRefs.Unresolved(f.Model, measureNames, "SUM(FactPurchaseRequest[Amount]) + [Requests]", "ok"));
    }
}

[Collection("model")]
public class SecurityTests(ModelFixture f)
{
    private ModelRole Reader => f.Model.Roles["Department Reader"];

    [Fact]
    public void One_read_role_exists_with_no_admin_permission()
    {
        var role = Assert.Single(f.Model.Roles);
        Assert.Equal(ModelPermission.Read, role.ModelPermission);
    }

    [Fact]
    public void Role_filters_the_dimension_by_the_signed_in_user()
    {
        var filter = Reader.TablePermissions["DimDepartment"].FilterExpression;
        Assert.Contains("USERPRINCIPALNAME()", filter);
        Assert.Contains("SecurityMap", filter);
        Assert.DoesNotContain("USERNAME()", filter.Replace("USERPRINCIPALNAME()", ""));
    }

    [Fact]
    public void Role_does_not_filter_the_fact_table_directly()
    {
        // one filter on the dimension reaches the fact through the relationship; a second, hand-written one on the fact drifts
        Assert.DoesNotContain(Reader.TablePermissions, tp => tp.Name == "FactPurchaseRequest");
    }

    [Fact]
    public void Mapping_table_is_hidden_and_filtered_to_the_caller()
    {
        Assert.True(f.Model.Tables["SecurityMap"].IsHidden);
        Assert.Contains("USERPRINCIPALNAME()", Reader.TablePermissions["SecurityMap"].FilterExpression);
    }

    [Fact]
    public void Mapping_table_has_no_relationships()
    {
        Assert.DoesNotContain(f.Model.Relationships.OfType<SingleColumnRelationship>(),
            r => r.FromTable.Name == "SecurityMap" || r.ToTable.Name == "SecurityMap");
    }

    [Fact]
    public void No_static_department_literals_in_the_role()
    {
        foreach (var tp in Reader.TablePermissions)
            foreach (var code in new[] { "\"FIN\"", "\"OPS\"", "\"IT\"", "\"HR\"", "\"MKT\"" })
                Assert.DoesNotContain(code, tp.FilterExpression);
    }

    [Fact]
    public void Mapping_covers_every_department_and_one_user_has_two()
    {
        var m = f.Model.Tables["SecurityMap"].Partitions[0].Source as MPartitionSource;
        Assert.NotNull(m);
        foreach (var code in new[] { "FIN", "HR", "IT", "MKT", "OPS" })
            Assert.Contains($"\"{code}\"", m!.Expression);
        Assert.Equal(2, Regex.Matches(m.Expression, "riley\\.demo@").Count);
    }
}

[Collection("model")]
public class SerializationTests(ModelFixture f)
{
    [Fact]
    public void Model_round_trips_through_TMDL_without_losing_objects()
    {
        var tmp = Path.Combine(Path.GetTempPath(), "tmdl-" + Guid.NewGuid().ToString("N"));
        try
        {
            TmdlSerializer.SerializeDatabaseToFolder(f.Database, tmp);
            var again = TmdlSerializer.DeserializeDatabaseFromFolder(tmp);
            Assert.Equal(f.Model.Tables.Count, again.Model.Tables.Count);
            Assert.Equal(f.AllMeasures.Count(), again.Model.Tables.SelectMany(t => t.Measures).Count());
            Assert.Equal(f.Model.Roles.Count, again.Model.Roles.Count);
            Assert.Equal(f.Model.Relationships.Count, again.Model.Relationships.Count);
        }
        finally { if (Directory.Exists(tmp)) Directory.Delete(tmp, true); }
    }

    [Fact]
    public void Model_converts_to_TMSL_json_that_a_service_can_take()
    {
        var json = JsonSerializer.SerializeDatabase(f.Database);
        Assert.Contains("\"Department Reader\"", json);
        Assert.Contains("USERPRINCIPALNAME()", json);
    }

    [Fact]
    public void No_tenant_identifiers_in_the_committed_model()
    {
        var guid = new Regex("[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", RegexOptions.IgnoreCase);
        foreach (var file in Directory.GetFiles(f.Folder, "*.tmdl", SearchOption.AllDirectories))
        {
            var text = File.ReadAllText(file);
            Assert.DoesNotMatch(guid, text);
            Assert.DoesNotContain("devladlog", text, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("sql.azuresynapse.net", text.Replace("<workspace>-ondemand.sql.azuresynapse.net", ""));
        }
    }
}

/// <summary>A small static check of table[column] and [measure] references. It is not a DAX parser.</summary>
public static class DaxRefs
{
    private static readonly Regex Qualified = new(@"(?<t>'[^']+'|[A-Za-z_][A-Za-z0-9_]*)\[(?<c>[^\]]+)\]", RegexOptions.Compiled);
    private static readonly Regex Bare = new(@"(?<![A-Za-z0-9_'])\[(?<m>[^\]]+)\]", RegexOptions.Compiled);

    public static IEnumerable<string> Unresolved(Model model, ISet<string> measures, string? dax, string where)
    {
        if (string.IsNullOrEmpty(dax)) yield break;
        var stripped = Regex.Replace(dax, "\"[^\"]*\"", "\"\"");   // string literals are not references
        foreach (Match q in Qualified.Matches(stripped))
        {
            var table = q.Groups["t"].Value.Trim('\'');
            var col = q.Groups["c"].Value;
            var t = model.Tables.Find(table);
            if (t == null) { yield return $"{where}: unknown table {table}"; continue; }
            if (t.Columns.Find(col) == null && t.Measures.Find(col) == null)
                yield return $"{where}: {table}[{col}] does not exist";
        }
        var withoutQualified = Qualified.Replace(stripped, "");
        foreach (Match b in Bare.Matches(withoutQualified))
            if (!measures.Contains(b.Groups["m"].Value))
                yield return $"{where}: [{b.Groups["m"].Value}] is not a measure";
    }
}
