using System.Globalization;
using Contoso.Requests.Legacy;

namespace Contoso.Requests.Clean.Tests;

public class CleanCodeTests
{
    [Theory]
    [InlineData("49999.99", Priority.Normal)]
    [InlineData("50000", Priority.High)]
    [InlineData("249999.99", Priority.High)]
    [InlineData("250000", Priority.Board)]
    public void Priority_follows_the_named_thresholds(string budget, Priority expected) =>
        Assert.Equal(expected, ApprovalPolicy.PriorityFor(decimal.Parse(budget, CultureInfo.InvariantCulture)));

    [Fact]
    public void Contingency_uses_bankers_rounding_like_Math_Round_does_by_default()
    {
        Assert.Equal(12_500m, ApprovalPolicy.WithContingency(10_870m));                                   // 12,500.5 -> even
        Assert.Equal(12_501m, ApprovalPolicy.WithContingency(10_870m, MidpointRounding.AwayFromZero));
        Assert.Equal(Math.Round(10_870m * 1.15m), ApprovalPolicy.WithContingency(10_870m));                 // the legacy expression
    }

    [Theory]
    [InlineData("PR-1;t;IT; 75,000 ;", true)]
    [InlineData("PR-1;t;IT;-500;", false)]
    [InlineData("PR-1;t;IT;0;", false)]
    [InlineData("PR-1;t;IT;abc;", false)]
    public void Budget_parsing_keeps_the_legacy_number_styles(string line, bool valid)
    {
        Assert.True(RequestFields.TrySplit(line, out var fields));
        Assert.Equal(valid, fields.TryGetBudget(out _));
    }

    [Fact]
    public void Approvers_are_built_from_the_priority()
    {
        var outcome = new RequestProcessor().Process("PR-2026-0300;Upgrade;mkt;300000;Board approved the plan");

        Assert.Equal(["riley.demo", "sam.demo", "board"], Assert.IsType<Routed>(outcome).Approvers);
    }

    [Fact]
    public void The_bool_flag_became_two_methods_and_rejections_never_get_the_mail_marker()
    {
        var routed = new RequestProcessor().Process("PR-2026-0301;Chairs;HR;1000;");
        var rejected = new RequestProcessor().Process("PR-2026-0302;Chairs;LEGAL;1000;");

        Assert.Equal("OK;PR-2026-0301;N;riley.demo;1150;MAIL", LegacyFormat.DescribeAfterNotifying(routed));
        Assert.Equal("ERR3", LegacyFormat.DescribeAfterNotifying(rejected));
    }

    [Fact]
    public void Gotcha_the_catch_all_turned_a_null_line_into_a_normal_looking_error()
    {
        Assert.Equal("ERR", new RequestProcessor2().Process(null!, false));                       // swallowed
        Assert.Throws<ArgumentNullException>(() => new RequestProcessor().Process(null!));       // a bug is a bug
    }

    [Fact]
    public void Gotcha_a_culture_bug_the_golden_master_could_not_see()
    {
        var original = CultureInfo.CurrentCulture;
        try
        {
            CultureInfo.CurrentCulture = new CultureInfo("tr-TR");

            // "it".ToUpper(tr-TR) is "İT" (dotted capital I), so the legacy lookup misses IT.
            Assert.Equal("ERR3", new RequestProcessor2().Process("PR-2026-0303;Laptops;it;1000;", false));
            Assert.IsType<Routed>(new RequestProcessor().Process("PR-2026-0303;Laptops;it;1000;"));
        }
        finally
        {
            CultureInfo.CurrentCulture = original;
        }
    }
}
