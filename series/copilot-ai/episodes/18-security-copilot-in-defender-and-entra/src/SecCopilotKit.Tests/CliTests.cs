using Contoso.SecCopilotKit.Cli;
using Xunit;

namespace Contoso.SecCopilotKit.Tests;

public class CliTests
{
    private static (int Code, string Out, string Err) Run(params string[] args)
    {
        var o = new StringWriter(); var e = new StringWriter();
        var code = Program.Run(args, o, e);
        return (code, o.ToString().Replace("\r\n", "\n"), e.ToString());
    }

    [Fact] public void CheckPassesOnTheShippedPlugin()
    {
        var r = Run("check", TestPaths.File("plugin", "contoso-soc-hunting.yaml"));
        Assert.Equal(0, r.Code);
        Assert.Contains("0 error(s), 0 warning(s)", r.Out);
    }

    [Fact] public void CheckFailsOnTheBrokenSample()
    {
        var r = Run("check", TestPaths.File("samples", "broken-plugin.yaml"));
        Assert.Equal(1, r.Code);
        Assert.Contains("ERROR", r.Out);
    }

    [Fact] public void RenderEscapesAndAnalyses()
    {
        var r = Run("render", TestPaths.File("plugin", "contoso-soc-hunting.yaml"), "GetEmailFromSenderDomain", "domain=o'brien.example");
        Assert.Equal(0, r.Code);
        Assert.Contains("'o\\'brien.example'", r.Out);
        Assert.Contains("parses and analyses without errors", r.Out);
    }

    [Fact] public void RenderUnknownSkillIsAUsageError()
    {
        var r = Run("render", TestPaths.File("plugin", "contoso-soc-hunting.yaml"), "Nope", "x=y");
        Assert.Equal(2, r.Code);
        Assert.Contains("No KQL skill named 'Nope'", r.Err);
    }

    [Fact] public void ScuProvisionedPrintsTheArithmetic()
    {
        var r = Run("scu", "provisioned", "--scus", "3", "--hours", "730", "--overage-used", "10");
        Assert.Equal(0, r.Code);
        Assert.Contains("8760.00 USD", r.Out);   // 3 x 730 x 4
        Assert.Contains("60.00 USD", r.Out);     // 10 x 6
        Assert.Contains("total:       8820.00 USD", r.Out);
    }

    [Fact] public void ScuInclusionPrintsTheAllocation()
    {
        var r = Run("scu", "inclusion", "--licences", "4000", "--used", "1700");
        Assert.Equal(0, r.Code);
        Assert.Contains("1600 SCU a month", r.Out);
        Assert.Contains("beyond 100", r.Out);
        Assert.Contains("600.00 USD", r.Out);
    }

    [Fact] public void ScuNeedsNumbers() => Assert.Equal(2, Run("scu", "provisioned", "--scus", "x", "--hours", "1").Code);

    [Fact] public void PreflightExitCodeFollowsReadiness()
    {
        Assert.Equal(0, Run("preflight", "conditional-access-optimization", TestPaths.File("samples", "tenant-profile.contoso-ready.json")).Code);
        var r = Run("preflight", "phishing-triage", TestPaths.File("samples", "tenant-profile.contoso-lab.json"));
        Assert.Equal(1, r.Code);
        Assert.Contains("MISSING", r.Out);
        Assert.Contains("not ready", r.Out);
    }

    [Fact] public void NoArgumentsPrintsUsage() { var r = Run(); Assert.Equal(2, r.Code); Assert.Contains("seckit check", r.Out); }
    [Fact] public void UnknownCommandFails() => Assert.Equal(2, Run("deploy").Code);
}
