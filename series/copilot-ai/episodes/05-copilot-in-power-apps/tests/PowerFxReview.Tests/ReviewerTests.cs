using PowerFxReview;
using Xunit;

namespace PowerFxReview.Tests;

public class ReviewerTests
{
    [Fact]
    public void A_correct_formula_is_clean_and_reports_its_type()
    {
        var r = Samples.Review("Text", "CountRows(Filter(Loans, IsBlank(ReturnedOn) && DueDate < Today())) & \" overdue\"");
        Assert.Equal("ok", r.Status);
        Assert.Equal("text", r.ReturnType);
        Assert.Empty(r.Findings);
    }

    [Fact]
    public void Unknown_column_is_an_error()
    {
        var r = Samples.Review("Text", "galLoans.Selected.Borrowr");
        Assert.True(r.HasErrors);
        Assert.Contains(r.Findings, f => f.Code == "PF001" && f.Message.Contains("Borrowr"));
    }

    [Fact]
    public void Missing_closing_parenthesis_is_an_error()
    {
        var r = Samples.Review("Text", "Text(CountRows(Filter(Loans, DueDate < Today())");
        Assert.Equal("error", r.Status);
        Assert.Contains(r.Findings, f => f.Code == "PF001");
    }

    [Theory]
    [InlineData("Text", "LookUp(Loans, Borrower = txtSearch.Text)", Severity.Error)]
    [InlineData("Items", "LookUp(Loans, Borrower = txtSearch.Text)", Severity.Error)]
    [InlineData("Visible", "Text(CountRows(Loans))", Severity.Warning)]
    public void Wrong_result_type_for_the_property(string property, string formula, Severity expected)
    {
        var r = Samples.Review(property, formula);
        var f = Assert.Single(r.Findings, x => x.Code == "PF002");
        Assert.Equal(expected, f.Severity);
    }

    [Fact]
    public void Hard_coded_email_and_guid_are_flagged_inside_string_literals_only()
    {
        var literal = Samples.Review("Text", "\"alex.demo@contoso.example\"");
        Assert.Contains(literal.Findings, f => f.Code == "PF003" && f.Message.Contains("e-mail"));

        var guid = Samples.Review("Text", "\"00000000-0000-0000-0000-000000000000\"");
        Assert.Contains(guid.Findings, f => f.Code == "PF003" && f.Message.Contains("GUID"));

        var column = Samples.Review("Text", "galLoans.Selected.BorrowerEmail");
        Assert.DoesNotContain(column.Findings, f => f.Code == "PF003");
    }

    [Fact]
    public void Non_delegable_functions_on_a_data_source_are_a_warning()
    {
        var r = Samples.Review("Items", "FirstN(Sort(Filter(Loans, Len(Borrower) > 2), DueDate), 10)");
        var f = Assert.Single(r.Findings, x => x.Code == "PF004");
        Assert.Equal(Severity.Warning, f.Severity);
        Assert.Contains("FirstN", f.Message);
        Assert.Contains("Len", f.Message);
        Assert.Contains("500", f.Message);
    }

    [Fact]
    public void Delegable_query_is_not_flagged()
    {
        var r = Samples.Review("Items", "Sort(Filter(Loans, IsBlank(ReturnedOn) && DueDate < Today()), DueDate)");
        Assert.DoesNotContain(r.Findings, f => f.Code == "PF004");
    }

    [Fact]
    public void Non_delegable_function_on_a_local_value_is_not_flagged()
    {
        var r = Samples.Review("Text", "Len(txtSearch.Text) & \" characters\"");
        Assert.DoesNotContain(r.Findings, f => f.Code == "PF004");
    }

    [Fact]
    public void Patch_without_error_handling_is_flagged_and_with_IfError_is_not()
    {
        var bad = Samples.Review("OnSelect", "Patch(Loans, galLoans.Selected, {Status: \"Reminded\"})");
        Assert.Contains(bad.Findings, f => f.Code == "PF005");
        Assert.Equal("partial", bad.Status);

        var good = Samples.Review("OnSelect",
            "IfError(Patch(Loans, galLoans.Selected, {Status: \"Returned\"}), Notify(\"Could not save\", NotificationType.Error))");
        Assert.DoesNotContain(good.Findings, f => f.Code == "PF005");
        Assert.False(good.HasErrors);
    }

    [Fact]
    public void Error_handling_rule_only_applies_to_behavior_properties()
    {
        var r = Samples.Review("Text", "Patch(Loans, galLoans.Selected, {Status: \"x\"})");
        Assert.DoesNotContain(r.Findings, f => f.Code == "PF005");
    }

    [Fact]
    public void Host_functions_are_partly_checked_not_rejected()
    {
        var r = Samples.Review("OnSelect", "Navigate(ListScreen, ScreenTransition.Fade)");
        Assert.Equal("partial", r.Status);
        Assert.False(r.HasErrors);
        Assert.Contains(r.Findings, f => f.Code == "PF006" && f.Message.Contains("Navigate"));
    }

    [Fact]
    public void A_typo_is_still_caught_inside_a_formula_that_uses_host_functions()
    {
        var r = Samples.Review("OnSelect", "Notify(galLoans.Selected.Borrowr, NotificationType.Error)");
        Assert.True(r.HasErrors);
        Assert.Contains(r.Findings, f => f.Code == "PF001" && f.Message.Contains("Borrowr"));
    }

    [Fact]
    public void Set_declares_its_variable_so_it_is_not_reported_as_unknown()
    {
        var r = Samples.Review("OnStart", "Set(varNew, 5)");
        Assert.False(r.HasErrors);
    }

    [Fact]
    public void Connector_calls_are_recognised_as_host_functions()
    {
        var r = Samples.Review("OnSelect", "Office365Outlook.SendEmailV2(galLoans.Selected.BorrowerEmail, \"Overdue\", \"Please return it\")");
        Assert.Equal("partial", r.Status);
        Assert.Contains(r.Findings, f => f.Code == "PF006" && f.Message.Contains("Office365Outlook.SendEmailV2"));
    }

    [Fact]
    public void Several_filter_predicates_are_an_engine_difference_not_an_error()
    {
        // Learn: "If you supply more than one formula, the results of all formulas are combined with the And function."
        // The standalone engine rejects it. Reported as info, never as an error.
        var r = Samples.Review("Items", "Filter(Loans, IsBlank(ReturnedOn), StartsWith(Borrower, txtSearch.Text))");
        Assert.False(r.HasErrors);
        Assert.Equal("partial", r.Status);
        Assert.Contains(r.Findings, f => f.Code == "PF007");
    }

    [Fact]
    public void String_helper_ignores_text_inside_literals_and_handles_doubled_quotes()
    {
        Assert.Equal("Len(\"\")", Reviewer_Strip("Len(\"a(b)\")"));
        Assert.Equal("F(\"\")", Reviewer_Strip("F(\"say \"\"hi\"\"\")"));
    }

    [Fact]
    public void Display_names_with_spaces_work_in_single_quotes_like_in_a_Dataverse_app()
    {
        var ctx = ReviewContext.Parse("""
            { "tables": { "Equipment Loans": { "datasource": true,
                "columns": { "Item": "string", "Due Date": "date", "Returned On": "date" } } } }
            """);
        var reviewer = new Reviewer(ctx, Array.Empty<string>());
        FormulaReview Review(string f) => reviewer.Review(new FormulaItem("t", "S", "gal", "Items", f));

        var good = Review("Filter('Equipment Loans', IsBlank('Returned On') && 'Due Date' < Today())");
        Assert.Equal("ok", good.Status);
        Assert.Empty(good.Findings);

        var bad = Review("Filter('Equipment Loans', 'Due Dat' < Today())");
        Assert.True(bad.HasErrors);

        var firstN = Review("FirstN('Equipment Loans', 5)");
        Assert.Contains(firstN.Findings, f => f.Code == "PF004");
    }

    static string Reviewer_Strip(string s) => (string)typeof(Reviewer)
        .GetMethod("StripStrings", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Static)!
        .Invoke(null, new object[] { s })!;
}
