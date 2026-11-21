using Contoso.Requests.Legacy;

namespace Contoso.Requests.Clean.Tests;

/// <summary>
/// Characterization tests: the approved file is what the legacy code did before anybody touched it.
/// The clean code must produce the same lines, except the changes we decided on and listed here.
/// </summary>
public class GoldenMasterTests
{
    /// <summary>Line 7, budget exactly 50,000: legacy said Normal ("&gt; 50000"), the rule says High.</summary>
    private static readonly string[] IntentionalChanges = ["07 plain", "07 mail"];

    [Fact]
    public void The_legacy_code_still_produces_the_approved_master() =>
        Assert.Equal(GoldenMaster.Approved, GoldenMaster.Record(new RequestProcessor2()));

    [Fact]
    public void The_master_covers_every_input_line_in_both_modes() =>
        Assert.Equal(GoldenMaster.Inputs.Length * 2, GoldenMaster.Approved.Length);

    [Fact]
    public void Clean_code_matches_the_master_except_the_intentional_changes() =>
        Assert.Equal(IntentionalChanges, GoldenMaster.DifferencesFrom(GoldenMaster.Record(new RequestProcessor())));

    [Fact]
    public void Gotcha_rounding_away_from_zero_changes_an_amount_people_already_approved()
    {
        var differences = GoldenMaster.DifferencesFrom(GoldenMaster.Record(new RequestProcessor(MidpointRounding.AwayFromZero)));

        Assert.Equal(["07 plain", "07 mail", "09 plain", "09 mail"], differences); // 10,870 * 1.15 = 12,500.5
    }

    [Fact]
    public void The_master_pins_the_order_of_the_checks()
    {
        // Line 18: Board budget, no justification AND unknown department. Legacy checks the justification first.
        Assert.Equal("18 plain ERR4", GoldenMaster.Approved[34]);
        Assert.Equal(new Rejected(Rejection.MissingJustification), new RequestProcessor().Process(GoldenMaster.Inputs[17]));
    }
}
