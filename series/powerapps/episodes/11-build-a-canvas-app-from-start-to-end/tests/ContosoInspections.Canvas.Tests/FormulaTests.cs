using Microsoft.PowerFx.Types;
using Xunit;

namespace ContosoInspections.Canvas.Tests;

/// <summary>The pure rules: named formulas and pure UDFs, with Today() fixed to Monday 30 November 2026.</summary>
public class FormulaTests
{
    private static Harness NewHarness() => SourceTests.NewHarness();

    [Fact]
    public void Named_formulas_follow_the_data()
    {
        var h = NewHarness();
        Assert.Equal(88m, h.Number("TapTarget"));
        Assert.Equal(2m, h.Number("DraftCount"));
        Assert.Equal(1m, h.Number("OverdueFindingCount")); // "Extinguisher tag out of date" was due on the 28th
        Assert.Equal("Alex Demo", h.Text("CurrentInspector.'Full name'"));
    }

    [Fact]
    public void A_user_who_is_not_an_inspector_has_no_CurrentInspector()
    {
        var h = NewHarness();
        h.UserEmail = "stranger@contoso.com";
        h.Recalc();
        Assert.True(h.Bool("IsBlank(CurrentInspector)"));
    }

    [Theory]
    [InlineData("Critical", 4, true)]
    [InlineData("Major", 3, true)]
    [InlineData("Minor", 2, false)]
    [InlineData("Observation", 1, false)]
    [InlineData("anything else", 1, false)]
    public void Severity_ranks_and_which_are_serious(string severity, int rank, bool serious)
    {
        var h = NewHarness();
        Assert.Equal(rank, h.Number($"SeverityRank(\"{severity}\")"));
        Assert.Equal(serious, h.Bool($"IsSerious(\"{severity}\")"));
    }

    [Theory]
    [InlineData("Critical", "2026-12-01")]
    [InlineData("Major", "2026-12-07")]
    [InlineData("Minor", "2026-12-30")]
    [InlineData("Observation", "2027-02-28")]
    public void Resolve_by_comes_from_the_severity(string severity, string due)
    {
        Assert.Equal(due, NewHarness().DateText($"ResolveByFor(\"{severity}\")"));
    }

    [Theory]
    [InlineData("Alex Demo", "AD")]
    [InlineData("  sam   demo ", "SD")]
    [InlineData("Madonna", "M")]
    public void Initials_come_from_each_word_of_the_name(string name, string initials)
    {
        Assert.Equal(initials, NewHarness().Text($"Initials(\"{name}\")"));
    }

    [Fact]
    public void A_reference_is_site_date_initials_and_a_three_digit_sequence()
    {
        var h = NewHarness();
        Assert.Equal("CPE-02-20261130-AD-", h.Text("RefPrefix(\"CPE-02\", \"Alex Demo\")"));
        Assert.Equal("CPE-02-20261130-AD-001", h.Text("InspectionRef(RefPrefix(\"CPE-02\", \"Alex Demo\"), 0)"));
        Assert.Equal("CPE-02-20261130-AD-013", h.Text("InspectionRef(RefPrefix(\"CPE-02\", \"Alex Demo\"), 12)"));
    }

    [Theory]
    [InlineData(0, 0, 0, "Pass")]
    [InlineData(0, 0, 2, "Pass")]
    [InlineData(0, 0, 3, "Needs follow-up")]
    [InlineData(0, 1, 0, "Needs follow-up")]
    [InlineData(0, 2, 0, "Fail")]
    [InlineData(1, 0, 0, "Fail")]
    public void The_suggested_result_comes_from_the_severity_counts(int critical, int major, int minor, string expected)
    {
        Assert.Equal(expected, NewHarness().Text($"SuggestResult({critical}, {major}, {minor})"));
    }

    [Theory]
    [InlineData("", "", "Observation", false, "Give the finding a title of at least 3 characters.")]
    [InlineData("  ab ", "", "Minor", false, "Give the finding a title of at least 3 characters.")]
    [InlineData("Loose cable", "", "Observation", false, "")]
    [InlineData("Loose cable", "", "Minor", false, "")]
    [InlineData("Fire door", "short", "Major", true, "Major and critical findings need details (at least 10 characters).")]
    [InlineData("Fire door", "wedged open with a bin", "Major", false, "Major and critical findings need a photo.")]
    [InlineData("Fire door", "wedged open with a bin", "Critical", true, "")]
    public void A_finding_is_validated_before_it_is_saved(string title, string details, string severity, bool photo, string expected)
    {
        Assert.Equal(expected, NewHarness().Text($"ValidateFinding(\"{title}\", \"{details}\", \"{severity}\", {photo.ToString().ToLowerInvariant()})"));
    }

    [Theory]
    [InlineData(0, "", "", "Choose a result before submitting.")]
    [InlineData(0, "Pass", "", "")]
    [InlineData(0, "Needs follow-up", "", "A result other than Pass needs at least one finding.")]
    [InlineData(2, "Needs follow-up", "", "")]
    [InlineData(1, "Fail", "too short", "A failed inspection needs a summary (at least 10 characters).")]
    [InlineData(1, "Fail", "Exit blocked on the east side.", "")]
    public void An_inspection_is_validated_before_it_is_submitted(int findings, string result, string summary, string expected)
    {
        Assert.Equal(expected, NewHarness().Text($"ValidateSubmit({findings}, \"{result}\", \"{summary}\")"));
    }

    [Fact]
    public void Findings_are_counted_per_inspection_id()
    {
        var h = NewHarness();
        Assert.Equal(3m, h.Number($"FindingCount(GUID(\"{Harness.Id(302)}\"))"));
        Assert.Equal(1m, h.Number($"FindingCount(GUID(\"{Harness.Id(301)}\"))"));
        Assert.Equal(0m, h.Number($"FindingCount(GUID(\"{Harness.Id(303)}\"))"));
    }
}
