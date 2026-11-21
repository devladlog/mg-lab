using Microsoft.PowerFx.Types;
using Xunit;

namespace EquipmentDesk.Formulas.Tests;

/// <summary>The Loans screen: summary label, gallery Items, and the gallery template. Today is Mon 30 Nov 2026.</summary>
public class LoansScreenTests
{
    private static readonly CanvasSource Source = new();
    private readonly Harness h = new(Source);

    private IEnumerable<string> GalleryTags() => h.Tags((TableValue)h.Eval(Source.Formula("galLoans", "Items")));

    [Fact]
    public void Gallery_shows_open_loans_by_due_date_and_never_returned_ones()
    {
        Assert.Equal(new[] { "CT-0043", "CT-0107", "CT-0108", "CT-0311" }, GalleryTags());
    }

    [Fact]
    public void Overdue_only_keeps_the_loans_past_their_due_date()
    {
        h.SetControl("tglOverdueOnly", ("Value", FormulaValue.New(true)));
        Assert.Equal(new[] { "CT-0043", "CT-0107" }, GalleryTags());
    }

    [Fact]
    public void Overdue_only_follows_the_clock()
    {
        h.SetControl("tglOverdueOnly", ("Value", FormulaValue.New(true)));
        h.SetToday(new DateTime(2026, 12, 3));
        Assert.Equal(new[] { "CT-0043", "CT-0107", "CT-0108" }, GalleryTags());
    }

    [Fact]
    public void Summary_counts_overdue_loans()
    {
        Assert.Equal("2 loans are overdue", h.Text(Source.Formula("lblSummary", "Text")));
        h.SetToday(new DateTime(2026, 11, 16)); // CT-0043 is due today: not overdue yet
        Assert.Equal("Nothing overdue", h.Text(Source.Formula("lblSummary", "Text")));
        h.SetToday(new DateTime(2026, 11, 28));
        Assert.Equal("2 loans are overdue", h.Text(Source.Formula("lblSummary", "Text")));
    }

    [Fact]
    public void Summary_is_singular_for_one_overdue_loan()
    {
        h.SetToday(new DateTime(2026, 11, 18)); // only CT-0043 (due 16 Nov) is late
        Assert.Equal("1 loan is overdue", h.Text(Source.Formula("lblSummary", "Text")));
    }

    [Theory]
    [InlineData("CT-0043", "alex.demo@contoso.com · 10 working days late")]
    [InlineData("CT-0107", "jordan.demo@contoso.com · 1 working day late")]
    [InlineData("CT-0108", "sam.demo@contoso.com · due Wed 2 Dec (soon)")]
    [InlineData("CT-0311", "alex.demo@contoso.com · due Fri 18 Dec")]
    public void Row_detail(string tag, string expected)
    {
        h.SetThisItem(h.LoanFor(tag));
        Assert.Equal(expected, h.Text(Source.Formula("lblLoanDetail", "Text")));
    }

    [Theory]
    [InlineData("CT-0043", true)]
    [InlineData("CT-0108", false)]
    public void Reminder_button_only_on_overdue_rows(string tag, bool visible)
    {
        h.SetThisItem(h.LoanFor(tag));
        Assert.Equal(visible, h.Bool(Source.Formula("btnRemind", "Visible")));
    }

    [Theory]
    [InlineData("CT-0043", "Charger missing")]
    [InlineData("CT-0107", "No notes")] // blank
    [InlineData("CT-0108", "No notes")] // empty string: Coalesce treats "" like blank
    public void Notes_fall_back_with_Coalesce(string tag, string expected)
    {
        h.SetThisItem(h.LoanFor(tag));
        Assert.Equal(expected, h.Text(Source.Formula("lblLoanNotes", "Text")));
    }

    [Fact]
    public void Remind_button_copies_the_reminder_for_its_row()
    {
        h.SetThisItem(h.LoanFor("CT-0107"));
        h.Eval(Source.Formula("btnRemind", "OnSelect"));
        Assert.StartsWith("Copy: Hi Jordan, the CT-0107 Monitor 27 you borrowed was due back on Friday 27 November, 1 working day ago.", h.Calls[0]);
        Assert.Equal("Notify(Success): Reminder for jordan.demo@contoso.com copied", h.Calls[1]);
    }
}
