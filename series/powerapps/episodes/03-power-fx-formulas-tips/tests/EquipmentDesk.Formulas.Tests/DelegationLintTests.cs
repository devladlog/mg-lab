using System.Text.RegularExpressions;
using Microsoft.PowerFx.Types;
using Xunit;

namespace EquipmentDesk.Formulas.Tests;

/// <summary>
/// The interpreter works on in-memory tables, so it can't tell us what Dataverse will delegate. These are lints based on
/// Microsoft Learn: the Dataverse delegable-functions table, "AddColumns output is subject to the non-delegation record
/// limit" (table shaping), and "With, UpdateContext and Set create collections internally ... You don't see a
/// delegation warning" (delegation overview).
/// </summary>
public class DelegationLintTests
{
    private static readonly CanvasSource Source = new();
    private static readonly string[] DataSources = ["Loans", "Equipment"];

    // Learn, delegable functions for Dataverse (date and text columns). Today() is a constant for every row.
    private static readonly HashSet<string> Delegable = ["Filter", "LookUp", "First", "Sort", "SortByColumns", "StartsWith", "IsBlank", "And", "Or", "Not", "CountRows", "CountIf", "Today"];

    internal static IEnumerable<string> Functions(string formula) =>
        Regex.Matches(Regex.Replace(formula, @"'[^']*'|""[^""]*""", "x"), @"\b([A-Z][A-Za-z]+)\s*\(").Select(m => m.Groups[1].Value).Distinct();

    /// <summary>Every formula in the app: control properties plus the App.Formulas definitions.</summary>
    public static IEnumerable<object[]> AllFormulas() =>
        Source.Controls.Values.SelectMany(c => c.Properties.Where(p => p.Value.StartsWith('=')).Select(p => new object[] { $"{c.Name}.{p.Key}", p.Value[1..] }))
            .Concat(Source.Definitions().Select(d => new object[] { $"App.Formulas {d.Name}", d.Text }));

    [Fact]
    public void Gallery_Items_uses_only_functions_Dataverse_can_delegate()
    {
        var used = Functions(Source.Formula("galLoans", "Items")).ToArray();
        Assert.Equal(new[] { "Sort", "Filter", "IsBlank", "Today" }, used);
        Assert.All(used, f => Assert.Contains(f, Delegable));
    }

    [Fact]
    public void OverdueCount_uses_only_functions_Dataverse_can_delegate()
    {
        var expr = Source.Definitions().Single(d => d.Name == "OverdueCount").Expression;
        Assert.All(Functions(expr), f => Assert.Contains(f, Delegable));
    }

    [Theory]
    [MemberData(nameof(AllFormulas))]
    public void No_With_record_holds_a_data_source(string where, string formula)
    {
        // With({ open: Filter(Loans, ...) }, ...) looks tidy but the record becomes an in-memory collection: no delegation,
        // and Studio shows no warning. Only scalars go into a With record in this app.
        foreach (Match m in Regex.Matches(formula, @"With\s*\(\s*\{(?<rec>[^}]*)\}"))
            Assert.DoesNotContain(DataSources, ds => Regex.IsMatch(m.Groups["rec"].Value, $@"\b{ds}\b"));
        Assert.True(true, where);
    }

    [Theory]
    [MemberData(nameof(AllFormulas))]
    public void No_AddColumns_over_a_data_source(string where, string formula)
    {
        Assert.DoesNotMatch(new Regex(@"AddColumns\s*\(\s*(Loans|Equipment)\b"), formula);
        Assert.True(true, where);
    }

    [Theory]
    [InlineData("With({ open: Filter(Loans, IsBlank('Returned on')) }, Sort(open, 'Due date'))")]
    [InlineData("With({ all: Equipment }, CountRows(all))")]
    public void The_With_lint_catches_a_table_in_the_record(string formula)
    {
        var records = Regex.Matches(formula, @"With\s*\(\s*\{(?<rec>[^}]*)\}").Select(m => m.Groups["rec"].Value);
        Assert.Contains(records, r => DataSources.Any(ds => Regex.IsMatch(r, $@"\b{ds}\b")));
    }

    [Fact]
    public void In_memory_the_With_version_gives_the_same_rows_which_is_why_we_need_a_lint()
    {
        // The two formulas are equivalent on an in-memory table. Only the real connector shows the difference: the With
        // version works on the first rows only (data row limit, 500 by default), without a warning.
        var h = new Harness(Source);
        var tidy = "With({ open: Filter(Loans, IsBlank('Returned on')) }, Sort(Filter(open, !tglOverdueOnly.Value || 'Due date' < Today()), 'Due date'))";
        Assert.Equal(h.Tags((TableValue)h.Eval(Source.Formula("galLoans", "Items"))), h.Tags((TableValue)h.Eval(tidy)));
    }
}
