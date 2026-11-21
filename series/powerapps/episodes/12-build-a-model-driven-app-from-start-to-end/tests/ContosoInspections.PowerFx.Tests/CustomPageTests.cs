using System.Text.RegularExpressions;
using Microsoft.PowerFx.Types;
using Xunit;

namespace ContosoInspections.PowerFx.Tests;

public class CustomPageTests
{
    private static readonly PageSource Page = new();
    private Harness h = new();

    private void Open(string number) { h = new Harness(); h.LoadPage(Page, number); }   // named formulas can only be defined once per engine
    private string Label(string control) => h.Text(Page.Formula(control, "Text"));

    [Fact]
    public void Named_formulas_and_every_control_formula_bind()
    {
        Open("INS-01002");
        foreach (var (name, _) in Page.NamedFormulas()) Assert.True(h.Check(name).IsSuccess, name);
        foreach (var control in new[] { "lblTitle", "lblScore", "lblOpenCritical", "lblPassRate", "lblVerdict" })
            foreach (var prop in new[] { "Text", "Fill", "Color" }.Where(p => Page.Controls[control].Properties.ContainsKey(p)))
            {
                var check = h.Check(Page.Formula(control, prop));
                Assert.True(check.IsSuccess, $"{control}.{prop}: {string.Join("; ", check.Errors.Select(e => e.Message))}");
            }
        Assert.True(h.Check(Page.Formula("galFindings", "Items")).IsSuccess);
    }

    [Fact]
    public void The_page_finds_its_inspection_from_the_id_it_was_opened_with()
    {
        Open("INS-01002");
        Assert.Equal("Review INS-01002 - North Depot", Label("lblTitle"));
        Open("INS-01003");
        Assert.Equal("Review INS-01003 - Maple Office Block", Label("lblTitle"));
    }

    [Fact]
    public void Findings_belong_to_the_opened_inspection_only()
    {
        Open("INS-01002");
        Assert.Equal(3, (int)((DecimalValue)h.Eval("CountRows(Findings)")).Value);
        Open("INS-01004");
        Assert.Equal(3, (int)((DecimalValue)h.Eval("CountRows(Findings)")).Value);
        Assert.Equal(new[] { "Door seals", "Floor drains", "Temperature log" }, h.Eval("Sort(Findings, Item)") is TableValue t ? t.Rows.Select(r => ((StringValue)r.Value.GetField("cin_name")).Value).ToArray() : []);
    }

    [Fact]
    public void Open_findings_exclude_passed_checks_and_resolved_failures()
    {
        Open("INS-01000");             // two items: one passed, one failed but already resolved
        Assert.Equal(2, (int)((DecimalValue)h.Eval("CountRows(Findings)")).Value);
        Assert.Equal(0, (int)((DecimalValue)h.Eval("CountRows(OpenFindings)")).Value);
    }

    [Theory]
    [InlineData("INS-01001", 2, "0%", "Reject: open critical findings")]
    [InlineData("INS-01002", 1, "33%", "Reject: open critical findings")]
    [InlineData("INS-01003", 0, "100%", "Approve")]
    [InlineData("INS-01004", 0, "33%", "Send back: fewer than half of the checks passed")]
    public void Counts_pass_rate_and_suggested_decision(string number, int openCritical, string passRate, string verdict)
    {
        Open(number);
        // INS-01001 has one critical item; the other open item is Major
        var expectedCritical = number == "INS-01001" ? 1 : openCritical;
        Assert.Equal($"{expectedCritical} open critical", Label("lblOpenCritical"));
        Assert.Equal($"{passRate} of checks passed", Label("lblPassRate"));
        Assert.Equal($"Suggested decision: {verdict}", Label("lblVerdict"));
    }

    [Fact]
    public void An_approved_inspection_with_every_finding_resolved_gets_Approve()
    {
        Open("INS-01000");
        Assert.Equal("Approve", h.Text("Verdict"));
        Assert.Equal("good", h.Text("ScoreBand"));
    }

    [Fact]
    public void An_inspection_without_checks_has_a_pass_rate_of_zero_instead_of_a_division_error()
    {
        Open("INS-01006");              // Draft, no items
        Assert.Equal(0, (int)((DecimalValue)h.Eval("CountRows(Findings)")).Value);
        Assert.Equal("0% of checks passed", Label("lblPassRate"));
    }

    [Fact]
    public void A_missing_score_says_so_and_sends_the_inspection_back()
    {
        Open("INS-01005");
        Assert.Equal("No score", Label("lblScore"));
        Assert.Equal("none", h.Text("ScoreBand"));
        Assert.Equal("Suggested decision: Send back: score missing or below 70", Label("lblVerdict"));
    }

    [Theory]
    [InlineData("INS-01003", "good", 91)]
    [InlineData("INS-01004", "watch", 73)]
    [InlineData("INS-01001", "poor", 52)]
    [InlineData("INS-01005", "none", -1)]
    public void Score_badge_band_follows_the_thresholds_80_and_70(string number, string band, int score)
    {
        Open(number);
        Assert.Equal(band, h.Text("ScoreBand"));
        if (score >= 0) Assert.Equal(score.ToString(), Label("lblScore"));
        var fill = Page.Formula("lblScore", "Fill");
        Assert.Contains("ScoreBand", fill);
        Assert.True(h.Check(fill).IsSuccess);
    }

    [Fact]
    public void The_gallery_lists_open_findings_sorted_by_item_name()
    {
        Open("INS-01002");
        var names = ((TableValue)h.Eval(Page.Formula("galFindings", "Items"))).Rows.Select(r => ((StringValue)r.Value.GetField("cin_name")).Value).ToArray();
        Assert.Equal(new[] { "Emergency exit blocked", "Exit signage" }, names);
    }

    [Fact]
    public void Navigation_buttons_target_the_table_and_the_record()
    {
        // Navigate(table) opens the default view, Navigate(record) the default form (Learn: Using Power Fx in a custom page).
        // The harness has no single Navigate that takes either, so check the arguments themselves.
        Open("INS-01002");
        var back = Regex.Match(Page.Formula("btnBack", "OnSelect"), @"^Navigate\((.+)\)$").Groups[1].Value;
        var open = Regex.Match(Page.Formula("btnOpenRecord", "OnSelect"), @"^Navigate\((.+)\)$").Groups[1].Value;
        Assert.IsAssignableFrom<TableValue>(h.Eval(back));
        Assert.Equal("INS-01002", ((StringValue)((RecordValue)h.Eval(open)).GetField("cin_name")).Value);
    }

    [Fact]
    public void Param_is_available_in_a_page_but_not_in_a_command()
    {
        // Learn lists Param() among the functions NOT supported in commands; the page is where it belongs.
        Assert.Contains("Param(", Page.AppProperties["Formulas"]);
        foreach (var c in Commands.Load()) Assert.DoesNotContain("Param(", c.Visible + c.OnSelect);
    }
}
