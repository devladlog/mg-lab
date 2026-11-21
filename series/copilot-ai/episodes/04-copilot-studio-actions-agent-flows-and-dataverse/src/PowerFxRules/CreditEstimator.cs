namespace Contoso.VendorDesk;

/// <summary>
/// Copilot Credit estimate for a published agent, with the rates of the Learn page
/// "Billing rates and management" (standard harness), checked 21 Nov 2026:
///   classic answer 1, generative answer 2, agent action 5, tenant graph grounding 10, agent flow actions 13 per 100 actions.
/// Usage in the test chat is not billed. A user who holds a Microsoft 365 Copilot licence and chats with the agent
/// under their own identity is not charged for these items (Learn, footnote 1; for agent flows only the runs started
/// by the "When an agent calls the flow" trigger).
/// </summary>
public static class CreditEstimator
{
    public const double ClassicAnswer = 1;
    public const double GenerativeAnswer = 2;
    public const double AgentAction = 5;
    public const double TenantGraphGrounding = 10;
    public const double AgentFlowActionsPer100 = 13;
    public const double UsdPerCredit = 0.01;   // pay-as-you-go meter, see series episode 1 for the source

    public sealed record Usage(
        int ClassicAnswers = 0,
        int GenerativeAnswers = 0,
        int AgentActions = 0,
        int TenantGraphGroundedMessages = 0,
        int AgentFlowActions = 0);

    public static double Credits(Usage u, bool microsoft365CopilotLicensedUser = false)
    {
        if (microsoft365CopilotLicensedUser) return 0;
        return u.ClassicAnswers * ClassicAnswer
             + u.GenerativeAnswers * GenerativeAnswer
             + u.AgentActions * AgentAction
             + u.TenantGraphGroundedMessages * TenantGraphGrounding
             + u.AgentFlowActions * AgentFlowActionsPer100 / 100.0;
    }

    public static double Usd(double credits) => Math.Round(credits * UsdPerCredit, 4);

    /// <summary>
    /// One vendor request filed through the agent flow tool: the agent calls one tool (one agent action) and the flow runs
    /// the trigger, "Add a new row" and "Respond to the agent" (each flow trigger execution is billed like one action).
    /// </summary>
    public static Usage OneVendorRequest(int flowActionsIncludingTrigger = 3)
        => new(AgentActions: 1, AgentFlowActions: flowActionsIncludingTrigger);
}
