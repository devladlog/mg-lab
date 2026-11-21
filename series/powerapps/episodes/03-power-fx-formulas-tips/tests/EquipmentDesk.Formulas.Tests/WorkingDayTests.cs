using Xunit;

namespace EquipmentDesk.Formulas.Tests;

/// <summary>IsWorkingDay and WorkingDaysBetween: user-defined functions in App.Formulas, called like built-in functions.</summary>
public class WorkingDayTests
{
    private readonly Harness h = new(new CanvasSource());

    [Theory]
    [InlineData("Date(2026, 11, 30)", true)]   // Monday
    [InlineData("Date(2026, 11, 27)", true)]   // Friday
    [InlineData("Date(2026, 11, 28)", false)]  // Saturday
    [InlineData("Date(2026, 11, 29)", false)]  // Sunday
    [InlineData("Date(2026, 12, 1)", false)]   // Tuesday, but a public holiday (in Holidays)
    [InlineData("Date(2026, 12, 25)", false)]  // Friday, Christmas
    public void IsWorking_day_knows_weekends_and_the_holiday_list(string date, bool expected) =>
        Assert.Equal(expected, h.Bool($"IsWorkingDay({date})"));

    [Theory]
    [InlineData("Date(2026, 11, 30)", "Date(2026, 11, 30)", 0)]  // same day
    [InlineData("Date(2026, 12, 4)", "Date(2026, 11, 30)", 0)]   // finish before start: 0, not negative
    [InlineData("Date(2026, 11, 27)", "Date(2026, 11, 30)", 1)]  // Friday -> Monday: the weekend doesn't count
    [InlineData("Date(2026, 11, 16)", "Date(2026, 11, 30)", 10)] // two full weeks
    [InlineData("Date(2026, 11, 27)", "Date(2026, 12, 9)", 6)]   // skips 1 and 8 December
    [InlineData("Date(2026, 12, 24)", "Date(2027, 1, 4)", 5)]    // Christmas and New Year both fall on a Friday
    public void Working_days_between_counts_the_days_after_start_up_to_and_including_finish(string start, string finish, int expected) =>
        Assert.Equal(expected, h.Number($"WorkingDaysBetween({start}, {finish})"));

    [Fact]
    public void Working_days_text_is_singular_for_one()
    {
        Assert.Equal("1 working day", h.Text("WorkingDays(1)"));
        Assert.Equal("0 working days", h.Text("WorkingDays(0)"));
        Assert.Equal("10 working days", h.Text("WorkingDays(10)"));
    }

    // The trap: Weekday() starts the week on SUNDAY unless you say otherwise (Learn: Weekday, default 1 = Sunday).
    [Fact]
    public void Weekday_without_StartOfWeek_counts_Sunday_as_day_1()
    {
        Assert.Equal(1m, h.Number("Weekday(Date(2026, 11, 29))"));                      // Sunday
        Assert.Equal(6m, h.Number("Weekday(Date(2026, 11, 27))"));                      // Friday
        Assert.Equal(7m, h.Number("Weekday(Date(2026, 11, 29), StartOfWeek.Monday)"));  // Sunday, Monday-based
    }

    [Fact]
    public void The_naive_working_day_test_gets_Sunday_and_Friday_wrong()
    {
        // "Weekday(d) <= 5" reads as "Monday to Friday" but means "Sunday to Thursday".
        Assert.True(h.Bool("Weekday(Date(2026, 11, 29)) <= 5"));   // Sunday counted as a working day
        Assert.False(h.Bool("Weekday(Date(2026, 11, 27)) <= 5"));  // Friday not counted
        Assert.False(h.Bool("IsWorkingDay(Date(2026, 11, 29))"));
        Assert.True(h.Bool("IsWorkingDay(Date(2026, 11, 27))"));
    }

    [Fact]
    public void A_function_is_checked_against_its_signature()
    {
        // Every UDF parameter is typed, so wrong calls are caught when the formula is written, not when it runs.
        Assert.False(h.Check("WorkingDaysBetween(Date(2026, 11, 27))").IsSuccess);                        // missing argument
        Assert.False(h.Check("IsWorkingDay({ day: Date(2026, 11, 30) })").IsSuccess);                     // record, not a Date
        Assert.True(h.Check("WorkingDaysBetween(Date(2026, 11, 27), Date(2026, 12, 9)) + 1").IsSuccess); // returns a Number
    }
}
