using Microsoft.PowerFx.Types;
using Xunit;

namespace EquipmentDesk.Formulas.Tests;

/// <summary>LoanState (Switch on true, first match wins) and StateColor (Switch on a value). Today is Mon 30 Nov 2026.</summary>
public class LoanStateTests
{
    private readonly Harness h = new(new CanvasSource());

    [Theory]
    [InlineData("Date(2026, 11, 16)", "Date(2026, 11, 20)", "Returned")] // returned wins, even though the due date has passed
    [InlineData("Date(2026, 11, 27)", "Blank()", "Overdue")]
    [InlineData("Date(2026, 11, 30)", "Blank()", "Due soon")]             // due today is not overdue yet
    [InlineData("Date(2026, 12, 2)", "Blank()", "Due soon")]              // 1 working day away (1 Dec is a holiday)
    [InlineData("Date(2026, 12, 3)", "Blank()", "Due soon")]              // 2 working days
    [InlineData("Date(2026, 12, 4)", "Blank()", "On loan")]               // 3 working days
    public void Loan_state(string due, string returned, string expected) =>
        Assert.Equal(expected, h.Text($"LoanState({due}, {returned})"));

    [Fact]
    public void The_same_loan_changes_state_as_the_days_pass()
    {
        Assert.Equal("On loan", h.Text("LoanState(Date(2026, 12, 4), Blank())"));
        h.SetToday(new DateTime(2026, 12, 2));
        Assert.Equal("Due soon", h.Text("LoanState(Date(2026, 12, 4), Blank())"));
        h.SetToday(new DateTime(2026, 12, 7));
        Assert.Equal("Overdue", h.Text("LoanState(Date(2026, 12, 4), Blank())"));
    }

    [Theory]
    [InlineData("Overdue", 168, 0, 0)]
    [InlineData("Due soon", 138, 90, 0)]
    [InlineData("Returned", 16, 124, 16)]
    [InlineData("On loan", 50, 49, 48)]
    [InlineData("anything else", 50, 49, 48)] // the last Switch argument is the default
    public void State_colour(string state, int r, int g, int b)
    {
        var color = ((ColorValue)h.Eval($"StateColor(\"{state}\")")).Value;
        Assert.Equal((r, g, b), (color.R, color.G, color.B));
    }
}
