using Xunit;

namespace Contoso.SecCopilotKit.Tests;

public class PreflightTests
{
    private static TenantProfile Load(string name) => TenantProfile.Parse(TestPaths.Read("samples", name));

    [Fact] public void ReadyProfileIsReadyForBothAgents()
    {
        var p = Load("tenant-profile.contoso-ready.json");
        Assert.True(Preflight.Ready(Preflight.Check(Preflight.CaAgent, p)));
        Assert.True(Preflight.Ready(Preflight.Check(Preflight.PhishingTriage, p)));
    }

    [Fact] public void LabProfileIsReadyForTheCaAgentOnly()
    {
        var p = Load("tenant-profile.contoso-lab.json");
        Assert.True(Preflight.Ready(Preflight.Check(Preflight.CaAgent, p)));
        var pt = Preflight.Check(Preflight.PhishingTriage, p);
        Assert.False(Preflight.Ready(pt));
        Assert.Contains(pt, i => i.State == CheckState.Missing && i.Requirement.Contains("Plan 2"));
        Assert.Contains(pt, i => i.State == CheckState.Missing && i.Requirement.Contains("Auto-Resolve"));
    }

    [Fact] public void EntraP2SatisfiesP1()
    {
        var p = new TenantProfile { Licences = { "EntraIdP2" }, ScuAvailable = true, OperatorRoles = { "Security Administrator" } };
        Assert.True(Preflight.Ready(Preflight.Check(Preflight.CaAgent, p)));
    }

    [Fact] public void NoScuMeansNotReady()
    {
        var p = new TenantProfile { Licences = { "EntraIdP1" }, OperatorRoles = { "Security Administrator" }, ScuAvailable = false };
        Assert.Contains(Preflight.Check(Preflight.CaAgent, p), i => i.State == CheckState.Missing && i.Requirement.Contains("Compute Units"));
    }

    [Fact] public void ConditionalAccessAdministratorCannotActivateTheAgent()
    {
        // Learn: a Security Administrator is required to activate the agent the first time.
        var p = new TenantProfile { Licences = { "EntraIdP1" }, ScuAvailable = true, OperatorRoles = { "Conditional Access Administrator" } };
        Assert.Contains(Preflight.Check(Preflight.CaAgent, p), i => i.State == CheckState.Missing && i.Requirement.Contains("Security Administrator"));
    }

    [Fact] public void UnansweredSettingsAreUnknownNotMet()
    {
        var p = new TenantProfile { Licences = { "DefenderForOffice365P2" }, ScuAvailable = true, OperatorRoles = { "Security Administrator" } };
        var items = Preflight.Check(Preflight.PhishingTriage, p);
        Assert.Equal(4, items.Count(i => i.State == CheckState.Unknown));
        Assert.False(Preflight.Ready(items));
    }

    [Fact] public void EveryRequirementCitesALearnPage() =>
        Assert.All(new[] { Preflight.CaAgent, Preflight.PhishingTriage }.SelectMany(Preflight.Requirements), r => Assert.StartsWith("learn.microsoft.com/", r.Source));

    [Fact] public void UnknownAgentIsRejected() => Assert.Throws<ArgumentException>(() => Preflight.Requirements("nope"));
}
