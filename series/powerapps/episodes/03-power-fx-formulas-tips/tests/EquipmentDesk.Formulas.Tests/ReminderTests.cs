using Xunit;

namespace EquipmentDesk.Formulas.Tests;

/// <summary>FirstName, ReminderText (string interpolation, Text with a language tag) and the behavior UDF CopyReminder.</summary>
public class ReminderTests
{
    private const string Expected =
        "Hi Alex, the CT-0043 Laptop 14 you borrowed was due back on Monday 16 November, 10 working days ago. " +
        "Please bring it to the Equipment Desk. Thank you!";

    [Theory]
    [InlineData("alex.demo@contoso.com", "Alex")]
    [InlineData("SAM@contoso.com", "Sam")]
    [InlineData("jordan.demo.smith@contoso.com", "Jordan")]
    public void First_name_from_a_work_email(string email, string expected) =>
        Assert.Equal(expected, new Harness(new CanvasSource()).Text($"FirstName(\"{email}\")"));

    [Fact]
    public void Reminder_text()
    {
        var h = new Harness(new CanvasSource());
        Assert.Equal(Expected, h.Text("ReminderText(\"CT-0043 Laptop 14\", \"alex.demo@contoso.com\", Date(2026, 11, 16))"));
    }

    [Fact]
    public void One_working_day_is_singular()
    {
        var h = new Harness(new CanvasSource());
        Assert.Contains("due back on Friday 27 November, 1 working day ago.",
            h.Text("ReminderText(\"CT-0107 Monitor 27\", \"jordan.demo@contoso.com\", Date(2026, 11, 27))"));
    }

    [Fact]
    public void The_reminder_is_English_even_when_the_user_runs_the_app_in_Portuguese()
    {
        // Text() uses the language of the user running the app unless you pass a language tag (Learn: Text, Global apps).
        var h = new Harness(new CanvasSource(), userLanguage: "pt-PT");
        Assert.Equal(Expected, h.Text("ReminderText(\"CT-0043 Laptop 14\", \"alex.demo@contoso.com\", Date(2026, 11, 16))"));
        // Without the third argument the same format string gives Portuguese day and month names.
        Assert.Equal("segunda-feira 16 novembro", h.Text("Text(Date(2026, 11, 16), \"dddd d mmmm\")"));
    }

    [Fact]
    public void Copy_reminder_copies_the_text_and_says_so()
    {
        var h = new Harness(new CanvasSource());
        h.Eval("CopyReminder(\"CT-0043 Laptop 14\", \"alex.demo@contoso.com\", Date(2026, 11, 16))");
        Assert.Equal(new[] { "Copy: " + Expected, "Notify(Success): Reminder for alex.demo@contoso.com copied" }, h.Calls);
    }

    [Fact]
    public void Copy_reminder_reports_a_clipboard_failure_instead_of_claiming_success()
    {
        // Learn (Copy): embedded hosts such as Teams, SharePoint and Power BI don't support Copy(); use IfError.
        var h = new Harness(new CanvasSource());
        h.ClipboardUnavailable("Clipboard not available in this host");
        h.Eval("CopyReminder(\"CT-0043 Laptop 14\", \"alex.demo@contoso.com\", Date(2026, 11, 16))");
        Assert.Equal(new[] { "Notify(Error): Couldn't copy the reminder: Clipboard not available in this host" }, h.Calls);
    }

    [Fact]
    public void A_behavior_function_cant_be_used_where_a_value_is_expected()
    {
        // Behavior UDFs (body in { }) return Void and belong in OnSelect-style properties.
        var h = new Harness(new CanvasSource());
        Assert.False(h.Check("Len(CopyReminder(\"x\", \"a@contoso.com\", Date(2026, 11, 16)))").IsSuccess);
    }
}
