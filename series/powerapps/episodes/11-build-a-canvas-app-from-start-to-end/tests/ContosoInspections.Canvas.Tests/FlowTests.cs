using Microsoft.PowerFx.Types;
using Xunit;

namespace ContosoInspections.Canvas.Tests;

/// <summary>The screens' behavior: what the buttons do to the data and where they navigate, on in-memory Dataverse-shaped tables.</summary>
public class FlowTests
{
    private static Harness NewHarness() => SourceTests.NewHarness();

    // ---- list --------------------------------------------------------------------------------------------------------

    private static string[] Refs(Harness h) =>
        ((TableValue)h.Eval(SourceTests.AppSource.Formula("galInspections", "Items"))).Rows
            .Select(r => Harness.Field(r.Value, "cin_reference")).ToArray();

    [Fact]
    public void The_list_shows_the_inspectors_inspections_newest_first()
    {
        var h = NewHarness();
        Assert.Equal(new[] { "CDS-03-20261130-AD-001", "CPE-02-20261127-AD-001", "CWN-01-20261125-AD-001" }, Refs(h));
    }

    [Fact]
    public void The_status_chips_filter_by_choice()
    {
        var h = NewHarness();
        h.Run("btnDraft", "OnSelect");
        Assert.Equal(new[] { "CDS-03-20261130-AD-001", "CPE-02-20261127-AD-001" }, Refs(h));
        h.Run("btnSubmitted", "OnSelect");
        Assert.Equal(new[] { "CWN-01-20261125-AD-001" }, Refs(h));
        h.Run("btnAll", "OnSelect");
        Assert.Equal(3, Refs(h).Length);
    }

    [Fact]
    public void Search_matches_the_start_of_the_reference()
    {
        var h = NewHarness();
        h.SetControl("txtSearch", ("Text", FormulaValue.New("CPE")));
        Assert.Equal(new[] { "CPE-02-20261127-AD-001" }, Refs(h));
        h.SetControl("txtSearch", ("Text", FormulaValue.New("PE"))); // StartsWith, not Search: delegable, so not "contains"
        Assert.Empty(Refs(h));
    }

    [Fact]
    public void Tapping_a_row_selects_it_and_opens_the_inspection()
    {
        var h = NewHarness();
        h.SetThisItem(h.InspectionRow("CPE-02-20261127-AD-001"));
        h.Run("galInspections", "OnSelect");
        Assert.Equal("CPE-02-20261127-AD-001", h.Text("selectedInspection.Reference"));
        Assert.Equal(new[] { "Navigate(InspectionScreen, Cover)" }, h.Calls);
    }

    [Fact]
    public void The_summary_line_says_drafts_and_overdue_findings_in_words()
    {
        var h = NewHarness();
        h.SetThisItem(h.InspectionRow("CPE-02-20261127-AD-001"));
        Assert.Equal("2 drafts · 1 finding is overdue", h.Text(SourceTests.AppSource.Formula("lblSummary", "Text")));
    }

    // ---- start an inspection --------------------------------------------------------------------------------------------

    [Fact]
    public void Start_inspection_creates_a_draft_for_the_signed_in_inspector_and_opens_it()
    {
        var h = NewHarness();
        h.SetControl("drpSite", ("Selected", h.SiteRow("CPE-02")));
        h.Run("btnStart", "OnSelect");

        Assert.Equal(4, h.Count("cin_inspection"));
        var row = h.InspectionRow("CPE-02-20261130-AD-001");
        Assert.Equal("Draft", Harness.Field(row, "cin_status"));
        Assert.Equal("2026-11-30", Harness.Field(row, "cin_inspectiondate"));
        Assert.Equal("Alex Demo", Harness.Field((RecordValue)row.GetField("cin_inspectorid"), "cin_name"));
        Assert.Equal("Contoso Plant East", Harness.Field((RecordValue)row.GetField("cin_siteid"), "cin_name"));
        Assert.NotEqual("", Harness.Field(row, "cin_inspectionid")); // Dataverse assigned an id
        Assert.Equal("CPE-02-20261130-AD-001", h.Text("selectedInspection.Reference"));
        Assert.Equal(new[] { "Navigate(InspectionScreen, Cover)" }, h.Calls);
        Assert.Equal(3m, h.Number("DraftCount"));
    }

    [Fact]
    public void A_second_inspection_at_the_same_site_the_same_day_gets_the_next_sequence_number()
    {
        var h = NewHarness();
        h.SetControl("drpSite", ("Selected", h.SiteRow("CPE-02")));
        h.Run("btnStart", "OnSelect");
        h.Run("btnStart", "OnSelect");
        Assert.Equal("CPE-02-20261130-AD-002", h.Text("selectedInspection.Reference"));
        Assert.Equal(5, h.Count("cin_inspection"));
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
        h.SetControl("drpSite", ("Selected", h.SiteRow("CPE-02")));
        Assert.False(h.Bool("StartInspection(\"CPE-02\", Today())"));
        Assert.Equal(new[] { "Notify(Error): Couldn't start the inspection: You don't have permission to create Inspections." }, h.Calls);
        Assert.Equal(3, h.Count("cin_inspection"));
    }

    // ---- add a finding --------------------------------------------------------------------------------------------------

    private static Harness DraftOpen()
    {
        var h = NewHarness();
        h.Select("CDS-03-20261130-AD-001");
        return h;
    }

    private static void FillFinding(Harness h, string title, string severity, string details = "", string category = "Safety")
    {
        h.SetControl("txtFindingTitle", ("Text", FormulaValue.New(title)));
        h.SetControl("txtFindingDetails", ("Text", FormulaValue.New(details)));
        h.PickText("drpSeverity", severity);
        h.PickText("drpCategory", category);
    }

    [Fact]
    public void The_camera_keeps_the_photo_in_a_variable_until_the_finding_is_saved()
    {
        var h = DraftOpen();
        h.SetControl("camFinding", ("Photo", FormulaValue.New("appres://blobmanager/abc/1")));
        h.SetSelf(photo: "appres://blobmanager/abc/1");
        h.Run("camFinding", "OnSelect");
        Assert.Equal("appres://blobmanager/abc/1", h.Text("findingPhoto"));
        Assert.Equal("Photo attached", h.Text(SourceTests.AppSource.Formula("lblPhotoState", "Text")));
    }

    [Fact]
    public void A_minor_finding_saves_with_a_resolve_by_date_and_goes_back()
    {
        var h = DraftOpen();
        FillFinding(h, "  Cracked tile  ", "Minor", category: "Housekeeping");
        h.Run("btnSave", "OnSelect");

        Assert.Equal(new[] { "Notify(Success): Finding added", "Back()" }, h.Calls);
        var row = h.FindingRow("Cracked tile");
        Assert.Equal("Minor", Harness.Field(row, "cin_severity"));
        Assert.Equal("Housekeeping", Harness.Field(row, "cin_category"));
        Assert.Equal("2026-12-30", Harness.Field(row, "cin_resolveby"));
        Assert.Equal("false", Harness.Field(row, "cin_resolved"));
        Assert.Equal("Draft", Harness.Field((RecordValue)row.GetField("cin_inspectionid"), "cin_status"));
        Assert.Equal(1m, h.Number($"FindingCount(GUID(\"{Harness.Id(303)}\"))"));
        Assert.IsType<BlankValue>(row.GetField("cin_photo"));
    }

    [Fact]
    public void A_major_finding_without_a_photo_is_refused_and_nothing_is_saved()
    {
        var h = DraftOpen();
        FillFinding(h, "Fire door wedged", "Major", "Wedged open with a bin");
        h.Run("btnSave", "OnSelect");
        Assert.Equal(new[] { "Notify(Warning): Major and critical findings need a photo." }, h.Calls);
        Assert.Equal(4, h.Count("cin_finding"));
        Assert.Equal("Major and critical findings need a photo.", h.Text(SourceTests.AppSource.Formula("lblProblem", "Text")));
    }

    [Fact]
    public void A_major_finding_with_a_photo_stores_the_image_as_Full_and_Value()
    {
        var h = DraftOpen();
        h.SetVariable("findingPhoto", FormulaValue.New("appres://blobmanager/abc/1"));
        FillFinding(h, "Fire door wedged", "Major", "Wedged open with a bin");
        h.Run("btnSave", "OnSelect");

        Assert.Equal(new[] { "Notify(Success): Finding added", "Back()" }, h.Calls);
        var photo = (RecordValue)h.FindingRow("Fire door wedged").GetField("cin_photo");
        Assert.Equal("appres://blobmanager/abc/1", Harness.Field(photo, "Full"));
        Assert.Equal("appres://blobmanager/abc/1", Harness.Field(photo, "Value"));
        Assert.Equal("2026-12-07", Harness.Field(h.FindingRow("Fire door wedged"), "cin_resolveby"));
        Assert.True(h.Bool("IsBlank(findingPhoto)")); // the next finding starts without the previous photo
    }

    [Fact]
    public void A_failed_finding_save_keeps_the_photo_and_says_why()
    {
        var h = DraftOpen();
        h.SetVariable("findingPhoto", FormulaValue.New("appres://blobmanager/abc/1"));
        h.MakeReadOnly("cin_finding", "The photo is larger than 10240 KB.");
        FillFinding(h, "Fire door wedged", "Critical", "Wedged open with a bin");
        h.Run("btnSave", "OnSelect");
        Assert.Equal(new[] { "Notify(Error): Couldn't save the finding: The photo is larger than 10240 KB." }, h.Calls);
        Assert.Equal("appres://blobmanager/abc/1", h.Text("findingPhoto"));
    }

    // ---- resolve ----------------------------------------------------------------------------------------------------------

    [Fact]
    public void Resolving_a_finding_closes_it_and_the_overdue_count_follows()
    {
        var h = NewHarness();
        h.Select("CPE-02-20261127-AD-001");
        Assert.Equal("Disabled", h.Text(SourceTests.AppSource.Formula("btnResolve", "DisplayMode")));
        h.SelectFinding("Extinguisher tag out of date");
        Assert.Equal("Edit", h.Text(SourceTests.AppSource.Formula("btnResolve", "DisplayMode")));

        h.Run("btnResolve", "OnSelect");
        Assert.Equal("true", Harness.Field(h.FindingRow("Extinguisher tag out of date"), "cin_resolved"));
        Assert.Equal(new[] { "Notify(Success): Marked as resolved" }, h.Calls);
        Assert.Equal(0m, h.Number("OverdueFindingCount"));
        Assert.True(h.Bool("IsBlank(selectedFinding)"));
    }

    // ---- submit -----------------------------------------------------------------------------------------------------------

    [Fact]
    public void Submit_with_no_result_chosen_asks_for_one()
    {
        var h = NewHarness();
        h.Select("CDS-03-20261130-AD-001");
        h.SetControl("drpResult", ("Selected", FormulaValue.NewBlank(RecordType.Empty().Add("Value", FormulaType.String))));
        h.Run("btnSubmit", "OnSelect");
        Assert.Equal(new[] { "Notify(Warning): Choose a result before submitting." }, h.Calls);
        Assert.Equal("Draft", h.Text("Text(selectedInspection.'Inspection status')"));
    }

    [Fact]
    public void A_failing_inspection_without_findings_cannot_be_submitted()
    {
        var h = NewHarness();
        h.Select("CDS-03-20261130-AD-001");
        h.PickText("drpResult", "Needs follow-up");
        h.Run("btnSubmit", "OnSelect");
        Assert.Equal(new[] { "Notify(Warning): A result other than Pass needs at least one finding." }, h.Calls);
    }

    [Fact]
    public void A_passing_inspection_is_submitted_and_the_screen_goes_back()
    {
        var h = NewHarness();
        h.Select("CDS-03-20261130-AD-001");
        h.PickText("drpResult", "Pass");
        h.SetControl("txtSummary", ("Text", FormulaValue.New("  Nothing to report.  ")));
        h.Run("btnSubmit", "OnSelect");

        Assert.Equal(new[] { "Notify(Success): Inspection submitted", "Back()" }, h.Calls);
        var row = h.InspectionRow("CDS-03-20261130-AD-001");
        Assert.Equal("Submitted", Harness.Field(row, "cin_status"));
        Assert.Equal("Pass", Harness.Field(row, "cin_result"));
        Assert.Equal("Nothing to report.", Harness.Field(row, "cin_summary"));
        Assert.Equal(1m, h.Number("DraftCount"));
    }

    [Fact]
    public void A_failed_inspection_with_findings_and_a_summary_is_submitted()
    {
        var h = NewHarness();
        h.Select("CPE-02-20261127-AD-001");
        h.PickText("drpResult", "Fail");
        h.SetControl("txtSummary", ("Text", FormulaValue.New("Fire door wedged open, tag expired.")));
        h.Run("btnSubmit", "OnSelect");
        Assert.Equal("Fail", Harness.Field(h.InspectionRow("CPE-02-20261127-AD-001"), "cin_result"));
        Assert.Equal("Submitted", Harness.Field(h.InspectionRow("CPE-02-20261127-AD-001"), "cin_status"));
    }

    [Fact]
    public void A_submitted_inspection_is_read_only_on_the_screen()
    {
        var h = NewHarness();
        h.Select("CWN-01-20261125-AD-001");
        var app = SourceTests.AppSource;
        Assert.Equal("Disabled", h.Text(app.Formula("btnSubmit", "DisplayMode")));
        Assert.Equal("Disabled", h.Text(app.Formula("btnAddFinding", "DisplayMode")));
        Assert.Equal("View", h.Text(app.Formula("drpResult", "DisplayMode")));
        Assert.Equal("View", h.Text(app.Formula("txtSummary", "DisplayMode")));
    }

    [Fact]
    public void The_suggestion_counts_the_findings_of_this_inspection_only()
    {
        var h = NewHarness();
        h.Select("CPE-02-20261127-AD-001"); // one Major, one Minor, one Observation
        Assert.Equal("Suggested from the findings: Needs follow-up", h.Text(SourceTests.AppSource.Formula("lblSuggest", "Text")));
        h.Select("CDS-03-20261130-AD-001");
        Assert.Equal("Suggested from the findings: Pass", h.Text(SourceTests.AppSource.Formula("lblSuggest", "Text")));
    }

    [Fact]
    public void The_findings_gallery_shows_only_this_inspections_findings_and_says_open_or_resolved()
    {
        var h = NewHarness();
        h.Select("CPE-02-20261127-AD-001");
        var titles = ((TableValue)h.Eval(SourceTests.AppSource.Formula("galFindings", "Items"))).Rows
            .Select(r => Harness.Field(r.Value, "cin_title")).OrderBy(t => t).ToArray();
        Assert.Equal(new[] { "Extinguisher tag out of date", "Fire door wedged open", "Pallets blocking an aisle" }, titles);
        Assert.Equal("3 findings", h.Text(SourceTests.AppSource.Formula("lblFindings", "Text")));

        h.SetThisItem(h.FindingRow("Pallets blocking an aisle"));
        Assert.Equal("Observation · Resolved", h.Text(SourceTests.AppSource.Formula("lblFindingMeta", "Text")));
        h.SetThisItem(h.FindingRow("Extinguisher tag out of date"));
        Assert.Equal("Minor · Open, resolve by 28 Nov", h.Text(SourceTests.AppSource.Formula("lblFindingMeta", "Text")));
    }
}
