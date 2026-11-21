using Microsoft.PowerFx.Types;
using Xunit;

namespace ContosoInspections.Canvas.Tests;

/// <summary>The screens' behavior: what the buttons do to the data and where they navigate, on in-memory Dataverse-shaped tables.</summary>
public class FlowTests
{
    private static Harness NewHarness() => SourceTests.NewHarness();
    private const string Photo = "appres://blobmanager/abc/1";

    // ---- list --------------------------------------------------------------------------------------------------------

    private static string[] Numbers(Harness h) =>
        ((TableValue)h.Eval(SourceTests.AppSource.Formula("galInspections", "Items"))).Rows
            .Select(r => Harness.Field(r.Value, "cin_name")).ToArray();

    [Fact]
    public void The_list_shows_the_inspectors_inspections_newest_first_whatever_their_status()
    {
        var h = NewHarness();
        Assert.Equal(new[] { "INS-00004", "INS-00003", "INS-00002", "INS-00001" }, Numbers(h));   // the Approved one is there too
    }

    [Fact]
    public void The_status_chips_filter_by_choice()
    {
        var h = NewHarness();
        h.Run("btnDraft", "OnSelect");
        Assert.Equal(new[] { "INS-00004" }, Numbers(h));
        h.Run("btnInProgress", "OnSelect");
        Assert.Equal(new[] { "INS-00003" }, Numbers(h));
        h.Run("btnSubmitted", "OnSelect");
        Assert.Equal(new[] { "INS-00002" }, Numbers(h));
        h.Run("btnAll", "OnSelect");
        Assert.Equal(4, Numbers(h).Length);
    }

    [Fact]
    public void Search_matches_the_start_of_the_number()
    {
        var h = NewHarness();
        h.SetControl("txtSearch", ("Text", FormulaValue.New("INS-00003")));
        Assert.Equal(new[] { "INS-00003" }, Numbers(h));
        h.SetControl("txtSearch", ("Text", FormulaValue.New("00003"))); // StartsWith, not Search: delegable, so not "contains"
        Assert.Empty(Numbers(h));
    }

    [Fact]
    public void Tapping_a_row_selects_it_and_opens_the_inspection()
    {
        var h = NewHarness();
        h.SetThisItem(h.InspectionRow("INS-00003"));
        h.Run("galInspections", "OnSelect");
        Assert.Equal("INS-00003", h.Text("selectedInspection.'Inspection number'"));
        Assert.Equal(new[] { "Navigate(InspectionScreen, Cover)" }, h.Calls);
    }

    [Fact]
    public void The_summary_line_says_open_inspections_and_unresolved_items_in_words()
    {
        var h = NewHarness();
        Assert.Equal("2 open · 3 items are unresolved", h.Text(SourceTests.AppSource.Formula("lblSummary", "Text")));
    }

    [Theory]
    [InlineData("INS-00004", "● Draft · Mon 30 Nov")]
    [InlineData("INS-00003", "● In progress · Fri 27 Nov")]
    [InlineData("INS-00002", "✓ Submitted · Wed 25 Nov")]
    [InlineData("INS-00001", "✓ Approved · Fri 20 Nov")]
    public void Each_row_writes_its_status_out_with_a_mark_for_open_and_done(string number, string expected)
    {
        var h = NewHarness();
        h.SetThisItem(h.InspectionRow(number));
        Assert.Equal(expected, h.Text(SourceTests.AppSource.Formula("lblMeta", "Text")));
    }

    [Fact]
    public void A_row_the_back_office_rejected_shows_a_cross_not_a_tick()
    {
        var h = NewHarness();
        h.Do("Patch(Inspections, LookUp(Inspections, 'Inspection number' = \"INS-00002\"), {cin_status: 'Status (Inspections)'.Rejected})");
        h.SetThisItem(h.InspectionRow("INS-00002"));
        Assert.Equal("✕ Rejected · Wed 25 Nov", h.Text(SourceTests.AppSource.Formula("lblMeta", "Text")));
    }

    // ---- start an inspection --------------------------------------------------------------------------------------------

    [Fact]
    public void Start_inspection_creates_a_draft_for_the_signed_in_inspector_and_opens_it()
    {
        var h = NewHarness();
        h.SetControl("drpSite", ("Selected", h.SiteRow("RP-02")));
        h.Run("btnStart", "OnSelect");

        Assert.Equal(5, h.Count("cin_inspection"));
        var row = h.Inspections.Rows.Last().Value;
        Assert.Equal("Draft", Harness.Field(row, "cin_status"));
        Assert.Equal("2026-11-30", Harness.Field(row, "cin_inspectiondate"));
        Assert.Equal("Alex Demo", Harness.Field((RecordValue)row.GetField("cin_inspectorid"), "cin_name"));
        Assert.Equal("Riverside Plant", Harness.Field((RecordValue)row.GetField("cin_siteid"), "cin_name"));
        Assert.NotEqual("", Harness.Field(row, "cin_inspectionid")); // Dataverse assigned an id
        Assert.Equal("", Harness.Field(row, "cin_name"));            // ... but the auto number INS-xxxxx is assigned by the server, not by the app
        Assert.Equal("Draft", h.Text("Text(selectedInspection.cin_status)"));
        Assert.Equal("New inspection", h.Text(SourceTests.AppSource.Formula("lblInspectionTitle", "Text")));
        Assert.Equal(new[] { "Navigate(InspectionScreen, Cover)" }, h.Calls);
        Assert.Equal(3m, h.Number("OpenCount"));
    }

    [Fact]
    public void Start_is_disabled_for_someone_who_is_not_an_inspector()
    {
        var h = NewHarness();
        Assert.Equal("Edit", h.Text(SourceTests.AppSource.Formula("btnStart", "DisplayMode")));
        h.UserEmail = "stranger@contoso.com";
        h.Recalc();
        Assert.Equal("Disabled", h.Text(SourceTests.AppSource.Formula("btnStart", "DisplayMode")));
        Assert.Contains("not set up as an inspector", h.Text(SourceTests.AppSource.Formula("lblWho", "Text")));
    }

    [Fact]
    public void A_failed_save_says_why_and_does_not_navigate()
    {
        var h = NewHarness();
        h.MakeReadOnly("cin_inspection", "You don't have permission to create Inspections.");
        h.SetControl("drpSite", ("Selected", h.SiteRow("RP-02")));
        Assert.False(h.Bool("StartInspection(\"RP-02\", Today())"));
        Assert.Equal(new[] { "Notify(Error): Couldn't start the inspection: You don't have permission to create Inspections." }, h.Calls);
        Assert.Equal(4, h.Count("cin_inspection"));
    }

    // ---- add an item ----------------------------------------------------------------------------------------------------

    private static Harness DraftOpen()
    {
        var h = NewHarness();
        h.Select("INS-00004");
        return h;
    }

    private static void FillItem(Harness h, string name, string severity, bool passed, string notes = "", string category = "Safety")
    {
        h.SetControl("txtItemName", ("Text", FormulaValue.New(name)));
        h.SetControl("txtItemNotes", ("Text", FormulaValue.New(notes)));
        h.SetControl("tglPassed", ("Value", FormulaValue.New(passed)));
        h.PickText("drpSeverity", severity);
        h.PickText("drpCategory", category);
    }

    [Fact]
    public void The_camera_keeps_the_photo_in_a_variable_until_the_item_is_saved()
    {
        var h = DraftOpen();
        h.SetControl("camItem", ("Photo", FormulaValue.New(Photo)));
        h.SetSelf(photo: Photo);
        h.Run("camItem", "OnSelect");
        Assert.Equal(Photo, h.Text("itemPhoto"));
        Assert.Equal("Photo attached", h.Text(SourceTests.AppSource.Formula("lblPhotoState", "Text")));
    }

    [Fact]
    public void The_first_item_moves_a_draft_to_in_progress_and_the_screen_goes_back()
    {
        var h = DraftOpen();
        FillItem(h, "  Cracked tile  ", "Minor", passed: false, category: "Structural");
        h.Run("btnSave", "OnSelect");

        Assert.Equal(new[] { "Notify(Success): Item added", "Back()" }, h.Calls);
        var row = h.ItemRow("Cracked tile");
        Assert.Equal("Minor", Harness.Field(row, "cin_severity"));
        Assert.Equal("Structural", Harness.Field(row, "cin_category"));
        Assert.Equal("false", Harness.Field(row, "cin_passed"));
        Assert.Equal("", Harness.Field(row, "cin_resolvedon"));
        Assert.Equal("INS-00004", Harness.Field((RecordValue)row.GetField("cin_inspectionid"), "cin_name"));
        Assert.IsType<BlankValue>(row.GetField("cin_photo"));
        Assert.Equal("In progress", Harness.Field(h.InspectionRow("INS-00004"), "cin_status"));
        Assert.Equal("In progress", h.Text("Text(selectedInspection.cin_status)"));   // the open inspection follows
        Assert.Equal(1m, h.Number($"ItemCount(GUID(\"{Harness.Id(304)}\"))"));
        Assert.Equal(2m, h.Number("OpenCount"));                                       // Draft and In progress both count as open
    }

    [Fact]
    public void A_later_item_leaves_the_status_alone()
    {
        var h = NewHarness();
        h.Select("INS-00003"); // already In progress
        FillItem(h, "Walkways marked", "Info", passed: true);
        h.Run("btnSave", "OnSelect");
        Assert.Equal(new[] { "Notify(Success): Item added", "Back()" }, h.Calls);
        Assert.Equal("In progress", Harness.Field(h.InspectionRow("INS-00003"), "cin_status"));
        Assert.Equal("true", Harness.Field(h.ItemRow("Walkways marked"), "cin_passed"));
    }

    [Fact]
    public void A_critical_item_cannot_be_saved_as_passed()
    {
        var h = DraftOpen();
        h.SetVariable("itemPhoto", FormulaValue.New(Photo));
        FillItem(h, "Fire door", "Critical", passed: true);
        h.Run("btnSave", "OnSelect");
        Assert.Equal(new[] { "Notify(Warning): A critical item cannot be marked as passed." }, h.Calls);
        Assert.Equal(5, h.Count("cin_inspectionitem"));
        Assert.Equal("Draft", Harness.Field(h.InspectionRow("INS-00004"), "cin_status"));   // nothing half done
    }

    [Fact]
    public void A_failed_major_item_without_a_photo_is_refused_and_nothing_is_saved()
    {
        var h = DraftOpen();
        FillItem(h, "Fire door wedged", "Major", passed: false, notes: "Wedged open with a bin");
        h.Run("btnSave", "OnSelect");
        Assert.Equal(new[] { "Notify(Warning): A failed Major or Critical item needs a photo." }, h.Calls);
        Assert.Equal(5, h.Count("cin_inspectionitem"));
        Assert.Equal("A failed Major or Critical item needs a photo.", h.Text(SourceTests.AppSource.Formula("lblProblem", "Text")));
    }

    [Fact]
    public void A_failed_major_item_with_a_photo_stores_the_image_as_Full_and_Value()
    {
        var h = DraftOpen();
        h.SetVariable("itemPhoto", FormulaValue.New(Photo));
        FillItem(h, "Fire door wedged", "Major", passed: false, notes: "Wedged open with a bin", category: "Fire");
        h.Run("btnSave", "OnSelect");

        Assert.Equal(new[] { "Notify(Success): Item added", "Back()" }, h.Calls);
        var photo = (RecordValue)h.ItemRow("Fire door wedged").GetField("cin_photo");
        Assert.Equal(Photo, Harness.Field(photo, "Full"));
        Assert.Equal(Photo, Harness.Field(photo, "Value"));
        Assert.Equal("Wedged open with a bin", Harness.Field(h.ItemRow("Fire door wedged"), "cin_notes"));
        Assert.True(h.Bool("IsBlank(itemPhoto)")); // the next item starts without the previous photo
    }

    [Fact]
    public void A_failed_item_save_keeps_the_photo_and_the_status_and_says_why()
    {
        var h = DraftOpen();
        h.SetVariable("itemPhoto", FormulaValue.New(Photo));
        h.MakeReadOnly("cin_inspectionitem", "The photo is larger than 10240 KB.");
        FillItem(h, "Fire door wedged", "Critical", passed: false, notes: "Wedged open with a bin");
        h.Run("btnSave", "OnSelect");
        Assert.Equal(new[] { "Notify(Error): Couldn't save the item: The photo is larger than 10240 KB." }, h.Calls);
        Assert.Equal(Photo, h.Text("itemPhoto"));
        Assert.Equal("Draft", Harness.Field(h.InspectionRow("INS-00004"), "cin_status"));
    }

    // ---- resolve ----------------------------------------------------------------------------------------------------------

    [Fact]
    public void Resolving_a_failed_item_stamps_the_date_and_the_unresolved_count_follows()
    {
        var h = NewHarness();
        h.Select("INS-00003");
        Assert.Equal("Disabled", h.Text(SourceTests.AppSource.Formula("btnResolve", "DisplayMode")));   // nothing selected
        h.SelectItem("Aisle clear");
        Assert.Equal("Disabled", h.Text(SourceTests.AppSource.Formula("btnResolve", "DisplayMode")));   // it passed: nothing to resolve
        h.SelectItem("Extinguisher tag");
        Assert.Equal("Edit", h.Text(SourceTests.AppSource.Formula("btnResolve", "DisplayMode")));

        h.Run("btnResolve", "OnSelect");
        Assert.Equal("2026-11-30", Harness.Field(h.ItemRow("Extinguisher tag"), "cin_resolvedon"));
        Assert.Equal(new[] { "Notify(Success): Marked as resolved" }, h.Calls);
        Assert.Equal(2m, h.Number("UnresolvedItemCount"));
        Assert.True(h.Bool("IsBlank(selectedItem)"));
    }

    // ---- submit -----------------------------------------------------------------------------------------------------------

    private static void FillSubmit(Harness h, string score, bool followUp, string summary)
    {
        h.SetControl("txtScore", ("Text", FormulaValue.New(score)));
        h.SetControl("tglFollowUp", ("Value", FormulaValue.New(followUp)));
        h.SetControl("txtSummary", ("Text", FormulaValue.New(summary)));
    }

    [Fact]
    public void Submit_without_a_score_asks_for_one()
    {
        var h = NewHarness();
        h.Select("INS-00003");
        FillSubmit(h, "", false, "Everything checked.");
        h.Run("btnSubmit", "OnSelect");
        Assert.Equal(new[] { "Notify(Warning): Enter a score from 0 to 100 before you submit." }, h.Calls);
        Assert.Equal("In progress", Harness.Field(h.InspectionRow("INS-00003"), "cin_status"));
    }

    [Fact]
    public void Submit_without_a_summary_asks_for_one()
    {
        var h = NewHarness();
        h.Select("INS-00003");
        FillSubmit(h, "80", false, "short");
        h.Run("btnSubmit", "OnSelect");
        Assert.Equal(new[] { "Notify(Warning): Write a summary of at least 10 characters." }, h.Calls);
    }

    [Fact]
    public void An_inspection_with_no_items_cannot_be_submitted()
    {
        var h = NewHarness();
        h.Select("INS-00004");
        Assert.False(h.Bool("SubmitInspection(80, false, Blank(), \"Nothing recorded yet.\")"));
        Assert.Equal(new[] { "Notify(Warning): Add at least one item before you submit." }, h.Calls);
    }

    [Fact]
    public void A_draft_has_no_submit_button_until_its_first_item_makes_it_in_progress()
    {
        var h = NewHarness();
        h.Select("INS-00004");
        Assert.Equal("Disabled", h.Text(SourceTests.AppSource.Formula("btnSubmit", "DisplayMode")));
        h.Select("INS-00003");
        Assert.Equal("Edit", h.Text(SourceTests.AppSource.Formula("btnSubmit", "DisplayMode")));
    }

    [Fact]
    public void An_inspection_in_progress_is_submitted_with_score_follow_up_and_summary_and_the_screen_goes_back()
    {
        var h = NewHarness();
        h.Select("INS-00003");
        FillSubmit(h, "80", true, "  Fire door wedged open, tag expired.  ");
        h.SetControl("dpFollowUp", ("SelectedDate", FormulaValue.NewDateOnly(new DateTime(2026, 12, 7))));
        h.Run("btnSubmit", "OnSelect");

        Assert.Equal(new[] { "Notify(Success): Inspection submitted", "Back()" }, h.Calls);
        var row = h.InspectionRow("INS-00003");
        Assert.Equal("Submitted", Harness.Field(row, "cin_status"));
        Assert.Equal("80", Harness.Field(row, "cin_score"));
        Assert.Equal("true", Harness.Field(row, "cin_requiresfollowup"));
        Assert.Equal("2026-12-07", Harness.Field(row, "cin_followupdate"));
        Assert.Equal("Fire door wedged open, tag expired.", Harness.Field(row, "cin_summary"));
        Assert.Equal(1m, h.Number("OpenCount"));
    }

    [Fact]
    public void Switching_follow_up_off_clears_the_follow_up_date()
    {
        var h = NewHarness();
        h.Select("INS-00003");
        FillSubmit(h, "95", false, "All items checked on site.");
        h.SetControl("dpFollowUp", ("SelectedDate", FormulaValue.NewDateOnly(new DateTime(2026, 12, 7))));
        h.Run("btnSubmit", "OnSelect");
        var row = h.InspectionRow("INS-00003");
        Assert.Equal("false", Harness.Field(row, "cin_requiresfollowup"));
        Assert.Equal("", Harness.Field(row, "cin_followupdate"));
    }

    [Theory]
    [InlineData("INS-00002", "Submitted", "Waiting for the back office to review it.")]
    [InlineData("INS-00001", "Approved", "Approved by the back office.")]
    public void After_submit_the_inspection_is_read_only_and_shows_the_back_offices_decision(string number, string status, string banner)
    {
        var h = NewHarness();
        h.Select(number);
        var app = SourceTests.AppSource;
        Assert.Equal(status, h.Text("Text(selectedInspection.cin_status)"));
        Assert.Equal("Disabled", h.Text(app.Formula("btnSubmit", "DisplayMode")));
        Assert.Equal("Disabled", h.Text(app.Formula("btnAddItem", "DisplayMode")));
        Assert.Equal("View", h.Text(app.Formula("txtScore", "DisplayMode")));
        Assert.Equal("View", h.Text(app.Formula("tglFollowUp", "DisplayMode")));
        Assert.Equal("View", h.Text(app.Formula("txtSummary", "DisplayMode")));
        Assert.Equal(banner, h.Text(app.Formula("lblDecision", "Text")));
    }

    [Fact]
    public void A_rejected_inspection_says_so_and_stays_read_only()
    {
        var h = NewHarness();
        h.Do("Patch(Inspections, LookUp(Inspections, 'Inspection number' = \"INS-00002\"), {cin_status: 'Status (Inspections)'.Rejected})");
        h.Select("INS-00002");
        Assert.Equal("Rejected by the back office. Check their notes with your lead.", h.Text(SourceTests.AppSource.Formula("lblDecision", "Text")));
        Assert.Equal("Disabled", h.Text(SourceTests.AppSource.Formula("btnSubmit", "DisplayMode")));
    }

    [Fact]
    public void An_open_inspection_shows_no_decision_banner_and_the_banner_takes_no_room()
    {
        var h = NewHarness();
        h.Select("INS-00003");
        Assert.Equal("", h.Text(SourceTests.AppSource.Formula("lblDecision", "Text")));
    }

    [Fact]
    public void The_suggestion_counts_the_failed_items_of_this_inspection_only()
    {
        var h = NewHarness();
        h.Select("INS-00003"); // one failed Major, one failed Minor, one passed Info
        Assert.Equal("Suggested from the items: score 80, follow-up needed", h.Text(SourceTests.AppSource.Formula("lblSuggest", "Text")));
        h.Select("INS-00004");
        Assert.Equal("Suggested from the items: score 100, no follow-up needed", h.Text(SourceTests.AppSource.Formula("lblSuggest", "Text")));
    }

    [Fact]
    public void The_inputs_start_from_the_saved_values_or_sensible_defaults()
    {
        var h = NewHarness();
        var app = SourceTests.AppSource;
        h.Select("INS-00002");
        Assert.Equal("64", h.Text(app.Formula("txtScore", "Default")));
        Assert.Equal("Cable crosses the walkway at door 4.", h.Text(app.Formula("txtSummary", "Default")));
        Assert.Equal("2026-12-07", h.DateText(app.Formula("dpFollowUp", "DefaultDate")));
        h.Select("INS-00003");
        Assert.Equal("", h.Text(app.Formula("txtScore", "Default")));
        Assert.Equal("2026-12-07", h.DateText(app.Formula("dpFollowUp", "DefaultDate")));   // a failed Major: a week
    }

    [Fact]
    public void The_items_gallery_shows_only_this_inspections_items_and_says_passed_failed_open_or_resolved()
    {
        var h = NewHarness();
        h.Select("INS-00003");
        var names = ((TableValue)h.Eval(SourceTests.AppSource.Formula("galItems", "Items"))).Rows
            .Select(r => Harness.Field(r.Value, "cin_name")).OrderBy(t => t).ToArray();
        Assert.Equal(new[] { "Aisle clear", "Extinguisher tag", "Fire door" }, names);
        Assert.Equal("3 items", h.Text(SourceTests.AppSource.Formula("lblItems", "Text")));

        var meta = SourceTests.AppSource.Formula("lblItemMeta", "Text");
        h.SetThisItem(h.ItemRow("Aisle clear"));
        Assert.Equal("Info · Passed", h.Text(meta));
        h.SetThisItem(h.ItemRow("Extinguisher tag"));
        Assert.Equal("Minor · Failed, open", h.Text(meta));
        h.SetThisItem(h.ItemRow("Loose handrail"));
        Assert.Equal("Minor · Failed, resolved 24 Nov", h.Text(meta));
    }
}
