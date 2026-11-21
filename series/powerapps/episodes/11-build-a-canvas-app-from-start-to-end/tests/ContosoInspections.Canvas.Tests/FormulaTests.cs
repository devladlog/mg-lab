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
        Assert.Equal(2m, h.Number("OpenCount"));              // one Draft, one In progress; Submitted and Approved are not open
        Assert.Equal(3m, h.Number("UnresolvedItemCount"));    // failed and not resolved: the fire door, the tag, the cable
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
    [InlineData("Info", 1, false)]
    [InlineData("anything else", 1, false)]
    public void Severity_ranks_and_which_are_serious(string severity, int rank, bool serious)
    {
        var h = NewHarness();
        Assert.Equal(rank, h.Number($"SeverityRank(\"{severity}\")"));
        Assert.Equal(serious, h.Bool($"IsSerious(\"{severity}\")"));
    }

    [Theory]
    [InlineData("Draft", true)]
    [InlineData("In progress", true)]
    [InlineData("Submitted", false)]
    [InlineData("Approved", false)]
    [InlineData("Rejected", false)]
    public void Only_a_draft_or_an_inspection_in_progress_can_be_edited(string status, bool editable)
    {
        Assert.Equal(editable, NewHarness().Bool($"IsEditable(\"{status}\")"));
    }

    [Theory]
    [InlineData(0, 0, 0, 100)]
    [InlineData(0, 0, 2, 90)]
    [InlineData(0, 1, 0, 85)]
    [InlineData(1, 0, 0, 70)]
    [InlineData(1, 2, 3, 25)]
    [InlineData(3, 3, 3, 0)]   // never below zero
    public void The_suggested_score_comes_from_the_failed_item_counts(int critical, int major, int minor, int score)
    {
        Assert.Equal(score, NewHarness().Number($"SuggestScore({critical}, {major}, {minor})"));
    }

    [Theory]
    [InlineData(0, 0, false)]
    [InlineData(0, 1, true)]
    [InlineData(1, 0, true)]
    public void A_critical_or_major_failure_suggests_a_follow_up(int critical, int major, bool followUp)
    {
        Assert.Equal(followUp, NewHarness().Bool($"SuggestFollowUp({critical}, {major})"));
    }

    [Theory]
    [InlineData(1, 0, "2026-12-01")]
    [InlineData(0, 1, "2026-12-07")]
    [InlineData(0, 0, "2026-12-30")]
    public void The_follow_up_date_comes_from_the_worst_failure(int critical, int major, string due)
    {
        Assert.Equal(due, NewHarness().DateText($"FollowUpDateFor({critical}, {major})"));
    }

    [Theory]
    [InlineData("", "", "Info", true, false, "Give the item a name of at least 3 characters.")]
    [InlineData("  ab ", "", "Minor", true, false, "Give the item a name of at least 3 characters.")]
    [InlineData("Aisle clear", "", "Info", true, false, "")]
    [InlineData("Loose cable", "", "Minor", false, false, "")]
    [InlineData("Fire door", "short", "Major", false, true, "A failed Major or Critical item needs notes (at least 10 characters).")]
    [InlineData("Fire door", "wedged open with a bin", "Major", false, false, "A failed Major or Critical item needs a photo.")]
    [InlineData("Fire door", "wedged open with a bin", "Critical", false, true, "")]
    // A critical item cannot be passed: episode 12's table-scope business rule, mirrored. A passed Major needs neither notes nor photo.
    [InlineData("Fire door", "", "Critical", true, true, "A critical item cannot be marked as passed.")]
    [InlineData("Fire door", "", "Major", true, false, "")]
    public void An_item_is_validated_before_it_is_saved(string name, string notes, string severity, bool passed, bool photo, string expected)
    {
        Assert.Equal(expected, NewHarness().Text(
            $"ValidateItem(\"{name}\", \"{notes}\", \"{severity}\", {passed.ToString().ToLowerInvariant()}, {photo.ToString().ToLowerInvariant()})"));
    }

    [Theory]
    [InlineData("Blank()", 3, false, "Blank()", "Fine.", "Enter a score from 0 to 100 before you submit.")]   // the same words as the server-side rule
    [InlineData("101", 3, false, "Blank()", "All fine here.", "The score must be between 0 and 100.")]
    [InlineData("-1", 3, false, "Blank()", "All fine here.", "The score must be between 0 and 100.")]
    [InlineData("80", 0, false, "Blank()", "All fine here.", "Add at least one item before you submit.")]
    [InlineData("80", 3, true, "Blank()", "All fine here.", "Pick a follow-up date or switch follow-up off.")]
    [InlineData("80", 3, false, "Blank()", "too short", "Write a summary of at least 10 characters.")]
    [InlineData("80", 3, false, "Blank()", "All fine here.", "")]
    [InlineData("64", 2, true, "Date(2026, 12, 7)", "Cable across the walkway.", "")]
    public void An_inspection_is_validated_before_it_is_submitted(string score, int items, bool followUp, string followUpDate, string summary, string expected)
    {
        Assert.Equal(expected, NewHarness().Text(
            $"ValidateSubmit({items}, {score}, {followUp.ToString().ToLowerInvariant()}, {followUpDate}, \"{summary}\")"));
    }

    [Fact]
    public void Items_are_counted_per_inspection_id()
    {
        var h = NewHarness();
        Assert.Equal(3m, h.Number($"ItemCount(GUID(\"{Harness.Id(303)}\"))"));
        Assert.Equal(1m, h.Number($"ItemCount(GUID(\"{Harness.Id(301)}\"))"));
        Assert.Equal(0m, h.Number($"ItemCount(GUID(\"{Harness.Id(304)}\"))"));
    }

    [Fact]
    public void Failed_items_are_counted_per_inspection_and_severity()
    {
        var h = NewHarness();
        Assert.Equal(1m, h.Number($"FailedCount(GUID(\"{Harness.Id(303)}\"), \"Major\")"));
        Assert.Equal(1m, h.Number($"FailedCount(GUID(\"{Harness.Id(303)}\"), \"Minor\")"));
        Assert.Equal(0m, h.Number($"FailedCount(GUID(\"{Harness.Id(303)}\"), \"Critical\")"));
        Assert.Equal(0m, h.Number($"FailedCount(GUID(\"{Harness.Id(303)}\"), \"Info\")"));   // the one Info item passed
        Assert.Equal(1m, h.Number($"FailedCount(GUID(\"{Harness.Id(302)}\"), \"Critical\")"));
    }
}
