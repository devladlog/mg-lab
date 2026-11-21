using Contoso.VendorDesk;
using Xunit;

namespace PowerFxRules.Tests;

public class RuleTests
{
    private readonly RuleEngine _engine = new();

    private static Dictionary<string, object?> Request(
        string vendor = "Fabrikam Cloud", string category = "hosting", object? cost = null,
        string justification = "Replace the current hosting contract.", string number = "VR-0001", string tier = "Team lead")
        => new()
        {
            ["VendorName"] = vendor, ["Category"] = category, ["EstimatedAnnualCost"] = cost ?? 18400,
            ["Justification"] = justification, ["RequestNumber"] = number, ["ApprovalTier"] = tier,
        };

    // ---- approval tiers: same thresholds as the Contoso Vendor Onboarding Policy of episode 3 ----
    [Theory]
    [InlineData(0.01, "Team lead")]
    [InlineData(4200, "Team lead")]
    [InlineData(4999.99, "Team lead")]
    [InlineData(5000, "Procurement manager")]
    [InlineData(18400, "Procurement manager")]
    [InlineData(24999, "Procurement manager")]
    [InlineData(25000, "Finance director, after a security review")]
    [InlineData(120000, "Finance director, after a security review")]
    public void ApprovalTier_follows_the_policy_thresholds(double cost, string expected)
        => Assert.Equal(expected, _engine.EvaluateText("ApprovalTier", Request(cost: cost)));

    [Theory]
    [InlineData("Fabrikam Cloud", "hosting", 18400, "Replace the current hosting contract.", "")]
    [InlineData("Fabrikam Cloud", "HOSTING", 18400, "Replace the current hosting contract.", "")]
    [InlineData("", "hosting", 18400, "Replace the current hosting contract.", "Tell me the vendor name.")]
    [InlineData("F", "hosting", 18400, "Replace the current hosting contract.", "Tell me the vendor name.")]
    [InlineData("Fabrikam Cloud", "catering", 18400, "Replace the current hosting contract.",
        "The category must be hosting, printing, travel, security or other.")]
    [InlineData("Fabrikam Cloud", "hosting", 0, "Replace the current hosting contract.",
        "The estimated yearly cost must be a positive amount in euros.")]
    [InlineData("Fabrikam Cloud", "hosting", -5, "Replace the current hosting contract.",
        "The estimated yearly cost must be a positive amount in euros.")]
    [InlineData("Fabrikam Cloud", "hosting", 18400, "too short", "Give a short business justification (at least a sentence).")]
    public void ValidateRequest_returns_the_first_problem_or_empty_text(
        string vendor, string category, double cost, string justification, string expected)
        => Assert.Equal(expected, _engine.EvaluateText("ValidateRequest", Request(vendor, category, cost, justification)));

    [Fact]
    public void ValidateRequest_treats_a_missing_cost_as_invalid()
    {
        var t = Request();
        t["EstimatedAnnualCost"] = null;
        Assert.Equal("The estimated yearly cost must be a positive amount in euros.",
                     _engine.EvaluateText("ValidateRequest", t));
    }

    [Fact]
    public void ValidateRequest_reports_problems_in_a_fixed_order()
    {
        // everything is wrong: the vendor name is reported first, so the agent asks one thing at a time
        var t = Request(vendor: "", category: "x", cost: -1, justification: "");
        Assert.Equal("Tell me the vendor name.", _engine.EvaluateText("ValidateRequest", t));
    }

    [Fact]
    public void ConfirmationMessage_formats_money_with_US_separators_and_names_the_approver()
    {
        var msg = _engine.EvaluateText("ConfirmationMessage",
            Request(vendor: "northwind print", cost: 4200, number: "VR-0007", tier: "Team lead"));
        Assert.Equal("Request VR-0007 for Northwind Print (4,200 EUR a year) is waiting for: Team lead.", msg);
    }

    [Fact]
    public void ConfirmationMessage_uses_the_cost_as_typed_not_rounded_text()
    {
        var msg = _engine.EvaluateText("ConfirmationMessage", Request(cost: 12500.4));
        Assert.Contains("(12,500 EUR a year)", msg);
    }

    [Fact]
    public void The_formula_files_use_only_Topic_variables()
    {
        foreach (var rule in new[] { "ApprovalTier", "ValidateRequest", "ConfirmationMessage" })
        {
            var f = _engine.Formula(rule);
            Assert.DoesNotContain("Global.", f);
            Assert.DoesNotContain("System.", f);
            Assert.Contains("Topic.", f);
        }
    }

    [Fact]
    public void A_formula_that_does_not_compile_is_reported_with_its_rule_name()
    {
        var dir = Directory.CreateTempSubdirectory().FullName;
        File.WriteAllText(Path.Combine(dir, "Broken.fx"), "If(Topic.Missing > 1, \"a\")");
        var ex = Assert.Throws<InvalidOperationException>(() => new RuleEngine(dir).Evaluate("Broken", Request()));
        Assert.StartsWith("Broken:", ex.Message);
    }

    // ---- credits: the three worked examples of the Learn page, then our own flow ----
    [Fact]
    public void Credits_match_the_customer_support_example_of_Learn()
        // [(4x1)+(2x2)] x 900 customers = 7200 Copilot Credits
        => Assert.Equal(7200, 900 * CreditEstimator.Credits(new CreditEstimator.Usage(ClassicAnswers: 4, GenerativeAnswers: 2)));

    [Fact]
    public void Credits_match_the_tenant_graph_example_of_Learn()
        // [(4x2)+(4x10)] x 100 unlicensed users = 4800; licensed users are not charged
    {
        var u = new CreditEstimator.Usage(GenerativeAnswers: 4, TenantGraphGroundedMessages: 4);
        Assert.Equal(4800, 100 * CreditEstimator.Credits(u));
        Assert.Equal(0, CreditEstimator.Credits(u, microsoft365CopilotLicensedUser: true));
    }

    [Fact]
    public void Credits_match_the_order_processing_example_of_Learn()
        // 4 agent action calls = 20 Copilot Credits
        => Assert.Equal(20, CreditEstimator.Credits(new CreditEstimator.Usage(AgentActions: 4)));

    [Fact]
    public void One_vendor_request_costs_about_five_credits()
    {
        var c = CreditEstimator.Credits(CreditEstimator.OneVendorRequest());
        Assert.Equal(5.39, c, 2);                       // 5 for the agent action + 3 x 0.13 for the flow actions
        Assert.Equal(0.0539, CreditEstimator.Usd(c), 4);
    }

    [Fact]
    public void Agent_flow_actions_are_priced_per_hundred()
        => Assert.Equal(13, CreditEstimator.Credits(new CreditEstimator.Usage(AgentFlowActions: 100)));
}
