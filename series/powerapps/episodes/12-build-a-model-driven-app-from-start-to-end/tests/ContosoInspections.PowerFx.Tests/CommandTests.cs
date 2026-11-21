using Microsoft.PowerFx.Types;
using Xunit;

namespace ContosoInspections.PowerFx.Tests;

public class CommandTests
{
    private readonly Harness h = new();

    private bool Visible(string id) => h.Bool(Commands.Get(id).Visible);
    private void Run(string id) => h.Eval(Commands.Get(id).OnSelect);

    [Fact]
    public void Every_command_formula_binds_against_the_Dataverse_shaped_tables()
    {
        h.SelectOne("INS-01002");
        foreach (var c in Commands.Load())
            foreach (var f in new[] { c.Visible, c.OnSelect })
            {
                var check = h.Check(f);
                Assert.True(check.IsSuccess, $"{c.Id}: {string.Join("; ", check.Errors.Select(e => e.Message))}");
            }
    }

    [Fact]
    public void Seed_data_has_three_submitted_inspections_with_the_autonumbers_INS_01002_to_01004()
    {
        Assert.Equal("Submitted", h.Status("INS-01002"));
        Assert.Equal("Submitted", h.Status("INS-01003"));
        Assert.Equal("Submitted", h.Status("INS-01004"));
        Assert.Equal("Approved", h.Status("INS-01000"));
        Assert.Equal("Rejected", h.Status("INS-01001"));
    }

    // ---------------------------------------------------------------------------------------------- visibility
    [Theory]
    [InlineData("INS-01000", false)]   // Approved
    [InlineData("INS-01001", false)]   // Rejected
    [InlineData("INS-01002", true)]    // Submitted
    [InlineData("INS-01005", false)]   // In progress
    [InlineData("INS-01006", false)]   // Draft
    public void Approve_and_Reject_show_only_for_a_submitted_inspection(string number, bool shown)
    {
        h.SelectOne(number);
        Assert.Equal(shown, Visible("approve"));
        Assert.Equal(shown, Visible("reject"));
    }

    [Fact]
    public void With_several_rows_selected_Item_is_blank_so_the_single_record_commands_do_not_guess()
    {
        h.SelectMany("INS-01002", "INS-01003");
        Assert.True(h.Bool("IsBlank(Self.Selected.Item)"));
        Assert.False(Visible("approve"));          // Learn: Item is always blank if SelectionMax <> 1
        Assert.True(Visible("flagfollowup"));
    }

    [Fact]
    public void Flag_for_follow_up_needs_at_least_one_selected_row()
    {
        h.SelectNothing();
        Assert.False(Visible("flagfollowup"));
        h.SelectOne("INS-01005");
        Assert.True(Visible("flagfollowup"));
    }

    [Theory]
    [InlineData("View", true)]
    [InlineData("Edit", true)]
    [InlineData("New", false)]
    public void Review_board_is_hidden_on_a_new_unsaved_record(string state, bool shown)
    {
        h.SelectOne("INS-01002", state);
        Assert.Equal(shown, Visible("reviewboard"));
    }

    // ---------------------------------------------------------------------------------------------- approve
    [Fact]
    public void Approve_asks_first_then_sets_the_status_and_tells_the_user()
    {
        h.SelectOne("INS-01002");
        Run("approve");
        Assert.Equal("Approved", h.Status("INS-01002"));
        Assert.Equal(new[] { "Confirm: Approve INS-01002? [Approve/Keep in review]", "Notify(Information): Approved INS-01002." }, h.Calls);
    }

    [Fact]
    public void Approve_does_nothing_when_the_user_cancels()
    {
        h.ConfirmAnswer = false;
        h.SelectOne("INS-01002");
        Run("approve");
        Assert.Equal("Submitted", h.Status("INS-01002"));
        Assert.Equal(new[] { "Confirm: Approve INS-01002? [Approve/Keep in review]" }, h.Calls);
    }

    [Fact]
    public void Approve_reports_the_error_when_the_write_is_refused_and_does_not_claim_success()
    {
        h.MakeReadOnly("Inspections", "Principal user is missing prvWritecin_inspection privilege.");
        h.SelectOne("INS-01002");
        Run("approve");
        Assert.Equal("Submitted", h.Status("INS-01002"));
        Assert.Equal(new[]
        {
            "Confirm: Approve INS-01002? [Approve/Keep in review]",
            "Notify(Error): Could not approve: Principal user is missing prvWritecin_inspection privilege.",
        }, h.Calls);
    }

    // ---------------------------------------------------------------------------------------------- reject
    [Fact]
    public void Reject_without_reviewer_notes_warns_and_changes_nothing()
    {
        h.SelectOne("INS-01002");
        Run("reject");
        Assert.Equal("Submitted", h.Status("INS-01002"));
        Assert.Equal(new[] { "Notify(Warning): Add reviewer notes on the Review tab before you reject." }, h.Calls);   // no Confirm: the check comes first
    }

    [Fact]
    public void Reject_with_notes_asks_then_rejects()
    {
        h.SelectOne("INS-01002");
        h.Eval("Patch(Inspections, Self.Selected.Item, {'Reviewer notes': \"Re-check the exits.\"})");
        h.SelectOne("INS-01002");   // the form is saved and the selection refreshed before a command runs
        Run("reject");
        Assert.Equal("Rejected", h.Status("INS-01002"));
        Assert.Equal(new[]
        {
            "Confirm: Reject INS-01002? [Reject/Keep in review]",
            "Notify(Information): Rejected INS-01002. The inspector can correct and resubmit.",
        }, h.Calls);
    }

    [Fact]
    public void Reject_treats_notes_made_of_spaces_as_missing()
    {
        // Our first version used IsBlank(notes). IsBlank("  ") is false in Power Fx, so a reviewer could "reject" with a space.
        h.SelectOne("INS-01003");
        h.Eval("Patch(Inspections, Self.Selected.Item, {'Reviewer notes': \"   \"})");
        h.SelectOne("INS-01003");
        Assert.False(h.Bool("IsBlank(Self.Selected.Item.'Reviewer notes')"));
        Run("reject");
        Assert.Equal("Submitted", h.Status("INS-01003"));
        Assert.Equal(new[] { "Notify(Warning): Add reviewer notes on the Review tab before you reject." }, h.Calls);
    }

    // ---------------------------------------------------------------------------------------------- flag for follow-up
    [Fact]
    public void Flag_for_follow_up_marks_every_selected_inspection_and_dates_it_two_weeks_out()
    {
        h.SelectMany("INS-01005", "INS-01006");
        Run("flagfollowup");
        foreach (var n in new[] { "INS-01005", "INS-01006" })
        {
            var r = h.Inspection(n);
            Assert.True(((BooleanValue)r.GetField("cin_requiresfollowup")).Value);
            Assert.Equal(DateTime.Today.AddDays(14), ((DateValue)r.GetField("cin_followupdate")).GetConvertedValue(TimeZoneInfo.Local).Date);
        }
        Assert.False(((BooleanValue)h.Inspection("INS-01004").GetField("cin_requiresfollowup")).Value);     // not selected: untouched
        Assert.Equal(new[] { "Notify(Information): 2 inspection(s) flagged for follow-up." }, h.Calls);
    }

    [Fact]
    public void Flag_for_follow_up_reports_a_failed_write_instead_of_the_success_message()
    {
        h.MakeReadOnly("Inspections", "Principal user is missing prvWritecin_inspection privilege.");
        h.SelectMany("INS-01005");
        Run("flagfollowup");
        Assert.Equal(new[] { "Notify(Error): Could not flag the selected inspections: Principal user is missing prvWritecin_inspection privilege." }, h.Calls);
    }

    // ---------------------------------------------------------------------------------------------- review board
    [Fact]
    public void Review_board_opens_the_custom_page_with_the_selected_record()
    {
        h.SelectOne("INS-01002");
        Run("reviewboard");
        Assert.Equal(new[] { "Navigate(INS-01002, Page=Inspection review board)" }, h.Calls);
    }
}
