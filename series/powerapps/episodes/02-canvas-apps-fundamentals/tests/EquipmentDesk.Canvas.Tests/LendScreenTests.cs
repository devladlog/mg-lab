using Microsoft.PowerFx.Types;
using Xunit;

namespace EquipmentDesk.Canvas.Tests;

public class LendScreenTests
{
    private static readonly CanvasSource Source = new();
    private readonly Harness h = new(Source);

    private string Error(string email, DateTime loan, DateTime due)
    {
        h.SetControl("txtEmail", ("Text", FormulaValue.New(email)));
        h.SetControl("dpLoan", ("SelectedDate", FormulaValue.NewDateOnly(loan)));
        h.SetControl("dpDue", ("SelectedDate", FormulaValue.NewDateOnly(due)));
        return ((StringValue)h.Eval(Source.Formula("lblError", "Text"))).Value;
    }

    private static readonly DateTime Nov21 = new(2026, 11, 21);

    private string StatusOf(string tag) =>
        h.Column(h.Equipment, "contoso_status").ElementAt(h.Column(h.Equipment, "contoso_assettag").ToList().IndexOf(tag));

    [Fact]
    public void Valid_loan_has_no_error() =>
        Assert.Equal("", Error("alex.demo@contoso.com", Nov21, new DateTime(2026, 12, 5)));

    [Fact]
    public void Missing_email() =>
        Assert.Equal("Enter the borrower's email.", Error("", Nov21, new DateTime(2026, 12, 5)));

    [Fact]
    public void Malformed_email() =>
        Assert.Equal("That doesn't look like an email address.", Error("alex.demo@", Nov21, new DateTime(2026, 12, 5)));

    [Fact]
    public void Due_before_loan_date() =>
        Assert.Equal("The due date can't be before the loan date.", Error("alex.demo@contoso.com", Nov21, new DateTime(2026, 11, 20)));

    [Fact]
    public void Ninety_days_is_allowed_ninety_one_is_not()
    {
        Assert.Equal("", Error("alex.demo@contoso.com", Nov21, Nov21.AddDays(90)));
        Assert.Equal("Loans are limited to 90 days.", Error("alex.demo@contoso.com", Nov21, Nov21.AddDays(91)));
    }

    [Fact]
    public void Device_that_is_not_available_wins_over_every_other_message()
    {
        h.SelectDevice("CT-0311"); // in repair
        Assert.Equal("This device is not available.", Error("", Nov21, Nov21));
    }

    [Fact]
    public void Lend_button_is_disabled_while_there_is_an_error()
    {
        h.SetControl("lblError", ("Text", FormulaValue.New("Enter the borrower's email.")));
        Assert.Equal("Disabled", ((StringValue)h.Eval(Source.Formula("btnLend", "DisplayMode"))).Value);
        h.SetControl("lblError", ("Text", FormulaValue.New("")));
        Assert.Equal("Edit", ((StringValue)h.Eval(Source.Formula("btnLend", "DisplayMode"))).Value);
    }

    [Fact]
    public void Due_date_defaults_to_today_plus_DefaultLoanDays()
    {
        var due = ((DateValue)h.Eval(Source.Formula("dpDue", "DefaultDate"))).GetConvertedValue(TimeZoneInfo.Local);
        Assert.Equal(DateTime.Today.AddDays(14), due.Date);
    }

    [Fact]
    public void Lend_saves_the_loan_marks_the_device_on_loan_and_goes_back()
    {
        Error("alex.demo@contoso.com", Nov21, new DateTime(2026, 12, 5));
        h.Eval(Source.Formula("btnLend", "OnSelect"));

        var loan = Assert.Single(h.Loans.Rows).Value;
        Assert.Equal("CT-0042 - alex.demo - 2026-11-21", ((StringValue)loan.GetField("contoso_name")).Value);
        Assert.Equal("alex.demo@contoso.com", ((StringValue)loan.GetField("contoso_borroweremail")).Value);
        Assert.Equal("CT-0042", ((StringValue)((RecordValue)loan.GetField("contoso_equipmentid")).GetField("contoso_assettag")).Value);

        Assert.Equal("On loan", StatusOf("CT-0042"));
        Assert.Equal(new[] { "Notify(Success): Loan saved: CT-0042", "Back()" }, h.Calls);
    }

    [Fact]
    public void If_the_loan_cannot_be_saved_the_device_is_not_touched()
    {
        h.MakeReadOnly("Loans", "Principal user is missing prvCreatecontoso_loan privilege.");
        Error("alex.demo@contoso.com", Nov21, new DateTime(2026, 12, 5));
        h.Eval(Source.Formula("btnLend", "OnSelect"));

        Assert.Equal(new[] { "Notify(Error): Could not save the loan: Principal user is missing prvCreatecontoso_loan privilege." }, h.Calls);
        Assert.Equal("Available", StatusOf("CT-0042"));
        Assert.Empty(h.Loans.Rows);
    }

    [Fact]
    public void Two_writes_are_not_a_transaction_when_the_second_fails_the_loan_is_already_saved()
    {
        // The user may create loans but can't update Equipment (no Write privilege on that table).
        h.MakeReadOnly("Equipment", "Principal user is missing prvWritecontoso_equipment privilege.");
        Error("alex.demo@contoso.com", Nov21, new DateTime(2026, 12, 5));
        h.Eval(Source.Formula("btnLend", "OnSelect"));

        Assert.Single(h.Loans.Rows);                                   // the first write is saved, and the user is told so
        Assert.Equal(new[] { "Notify(Warning): Loan saved, but the device status wasn't updated: Principal user is missing prvWritecontoso_equipment privilege." }, h.Calls);
    }

    [Fact]
    public void Chained_formulas_keep_going_after_an_error_which_is_why_OnSelect_uses_IfError_pairs()
    {
        // Our first version. Learn: "The second Patch ... will be attempted even if the Patch to DS1 fails."
        const string firstVersion = """
            IfError(
                Collect(Loans, { Loan: "x", Equipment: galEquipment.Selected, 'Borrower email': txtEmail.Text });
                Patch(Equipment, galEquipment.Selected, { Status: 'Status (Equipment)'.'On loan' });
                Notify("Loan saved", NotificationType.Success);
                Back(),
                Notify("Could not save the loan: " & FirstError.Message, NotificationType.Error)
            )
            """;
        h.MakeReadOnly("Equipment", "denied");
        h.Eval(firstVersion);
        Assert.Equal(new[] { "Notify(Success): Loan saved", "Back()", "Notify(Error): Could not save the loan: denied" }, h.Calls);
    }
}
