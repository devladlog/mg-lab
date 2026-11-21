using Xunit;

namespace Contoso.SecCopilotKit.Tests;

public class ManifestCheckerTests
{
    private static IReadOnlyList<Finding> Check(string yaml) => ManifestChecker.CheckText(yaml);
    private static IReadOnlyList<Finding> File(params string[] p) => Check(TestPaths.Read(p));

    private const string Minimal = """
        Descriptor:
          Name: Contoso.Test
          DisplayName: Test
          Description: A test skill set
        SkillGroups:
          - Format: KQL
            Skills:
              - Name: One
                DisplayName: One
                Description: Returns mail
                Inputs:
                  - Name: domain
                    Description: The domain
                    Required: true
                Settings:
                  Target: Defender
                  Template: |-
                    EmailEvents
                    | where Timestamp > ago(1d)
                    | where SenderFromDomain =~ '{{domain}}'
                    | take 5
        """;

    private static string Edit(string from, string to) => Minimal.Replace(from, to);

    [Fact] public void MinimalManifestIsClean() => Assert.Empty(Check(Minimal));
    [Fact] public void ShippedPluginIsClean() => Assert.DoesNotContain(File("plugin", "contoso-soc-hunting.yaml"), f => f.Severity != Severity.Info);
    [Fact] public void ShippedAgentHasNoErrorsOrWarnings() => Assert.DoesNotContain(File("agent", "contoso-signin-triage-agent.yaml"), f => f.Severity != Severity.Info);

    [Fact] public void ShippedAgentExplainsItsExternalChildSkills() =>
        Assert.Equal(2, File("agent", "contoso-signin-triage-agent.yaml").Count(f => f.Severity == Severity.Info && f.Message.Contains("Contoso.SocHunting")));

    [Fact] public void NotYamlIsReported() => Assert.Contains(Check("a: [unclosed"), f => f.Message.StartsWith("not valid YAML"));
    [Fact] public void ScalarRootIsReported() => Assert.Contains(Check("just text"), f => f.Severity == Severity.Error);

    [Fact] public void DescriptorAndSkillGroupsAreRequired()
    {
        var r = Check("Other: 1");
        Assert.Contains(r, f => f.Path == "Descriptor");
        Assert.Contains(r, f => f.Path == "SkillGroups");
        Assert.Contains(r, f => f.Path == "Other" && f.Severity == Severity.Warning);
    }

    [Theory]
    [InlineData("Contoso Test")]
    [InlineData("Contoso/Test")]
    [InlineData("Contoso,Test")]
    [InlineData("Contoso?Test")]
    [InlineData("Contoso#Test")]
    [InlineData("Contoso@Test")]
    [InlineData("Contoso\\\\Test")]
    public void DescriptorNameRulesFromLearn(string name) =>
        Assert.Contains(Check(Edit("Contoso.Test", name)), f => f.Path == "Descriptor.Name" && f.Severity == Severity.Error);

    [Fact] public void DescriptorNameMayContainAPeriodAndHyphen() => Assert.Empty(Check(Edit("Contoso.Test", "Contoso.SecOps.Samples-090925")));
    [Fact] public void EmptyDescriptorDescriptionIsAnError() => Assert.Contains(Check(Edit("A test skill set", "\"\"")), f => f.Path == "Descriptor.Description");
    [Fact] public void MissingDisplayNameIsAWarning() => Assert.Contains(Check(Edit("  DisplayName: Test\n", "")), f => f.Path == "Descriptor.DisplayName" && f.Severity == Severity.Warning);
    [Fact] public void UnknownFormatIsAnError() => Assert.Contains(Check(Edit("Format: KQL", "Format: SQL")), f => f.Path == "SkillGroups[0].Format");

    [Theory]
    [InlineData("Get One")]
    [InlineData("Get.One")]
    public void SkillNameCannotHaveWhitespaceOrPeriod(string name) =>
        Assert.Contains(Check(Edit("Name: One", "Name: " + name)), f => f.Path.EndsWith("Skills[0].Name") && f.Severity == Severity.Error);

    [Fact] public void DuplicateSkillNamesAreAnError()
    {
        var yaml = Minimal + "\n      - Name: One\n        DisplayName: Again\n        Description: x\n        Settings:\n          Target: Defender\n          Template: EmailEvents | where Timestamp > ago(1d) | take 1\n";
        Assert.Contains(Check(yaml), f => f.Message.Contains("used twice"));
    }

    [Fact] public void KqlTargetMustBeKnown() => Assert.Contains(Check(Edit("Target: Defender", "Target: Splunk")), f => f.Path.EndsWith("Settings.Target"));
    [Fact] public void KqlTargetIsRequired() => Assert.Contains(Check(Edit("          Target: Defender\n", "")), f => f.Path.EndsWith("Settings.Target"));

    [Fact] public void TemplateAndTemplateUrlTogetherAreAnError() =>
        Assert.Contains(Check(Edit("Target: Defender", "Target: Defender\n          TemplateUrl: https://example.invalid/q.kql")), f => f.Message.Contains("either Template or TemplateUrl"));

    [Fact] public void KqlSkillNeedsATemplateSource()
    {
        var yaml = """
            Descriptor: {Name: A, DisplayName: A, Description: d}
            SkillGroups:
              - Format: KQL
                Skills:
                  - Name: X
                    DisplayName: X
                    Description: d
                    Settings: {Target: Defender}
            """;
        Assert.Contains(Check(yaml), f => f.Path.EndsWith("Settings.Template"));
    }

    [Fact] public void KustoTargetNeedsClusterAndDatabase()
    {
        var r = Check(Edit("Target: Defender", "Target: Kusto"));
        Assert.Contains(r, f => f.Path.EndsWith("Settings.Cluster"));
        Assert.Contains(r, f => f.Path.EndsWith("Settings.Database"));
    }

    [Fact] public void SentinelTargetNeedsWorkspaceSettings() =>
        Assert.Equal(4, Check(Edit("Target: Defender", "Target: Sentinel")).Count(f => f.Message.Contains("required for Target Sentinel")));

    [Fact] public void PlaceholderWithoutInputIsAnError() =>
        Assert.Contains(Check(Edit("{{domain}}", "{{other}}")), f => f.Message.Contains("{{other}}") && f.Severity == Severity.Error);

    [Fact] public void UnusedInputIsAWarning() =>
        Assert.Contains(Check(Edit("'{{domain}}'", "'contoso.example'")), f => f.Severity == Severity.Warning && f.Message.Contains("never used"));

    [Fact] public void KqlErrorsSurfaceWithThePathOfTheTemplate() =>
        Assert.Contains(Check(Edit("SenderFromDomain", "SenderDomain")), f => f.Path.EndsWith("Settings.Template") && f.Message.Contains("SenderDomain"));

    [Fact] public void GptModelMustBeGpt41()
    {
        var yaml = """
            Descriptor: {Name: A, DisplayName: A, Description: d}
            SkillGroups:
              - Format: GPT
                Skills:
                  - Name: S
                    DisplayName: S
                    Description: d
                    Settings: {ModelName: gpt-4o, Template: Say hi}
            """;
        Assert.Contains(Check(yaml), f => f.Message.Contains("gpt-4.1"));
        Assert.DoesNotContain(Check(yaml.Replace("gpt-4o", "gpt-4.1")), f => f.Severity == Severity.Error);
    }

    [Fact] public void ApiGroupNeedsSupportedAuthTypes()
    {
        var yaml = """
            Descriptor: {Name: A, DisplayName: A, Description: d}
            SkillGroups:
              - Format: API
                Settings: {OpenApiSpecUrl: "https://example.invalid/openapi.yaml"}
            """;
        Assert.Contains(Check(yaml), f => f.Path == "Descriptor.SupportedAuthTypes");
        Assert.DoesNotContain(Check(yaml.Replace("d}\n", "d, SupportedAuthTypes: [None]}\n")), f => f.Severity == Severity.Error);
    }

    [Fact] public void UnknownAuthTypeIsAnError() =>
        Assert.Contains(Check(Edit("Description: A test skill set", "Description: d\n  SupportedAuthTypes: [Kerberos]")), f => f.Path.StartsWith("Descriptor.SupportedAuthTypes"));

    private static string Agent(string edit = "") => File2("agent", "contoso-signin-triage-agent.yaml", edit);
    private static string File2(string a, string b, string edit) => TestPaths.Read(a, b) + edit;

    [Fact] public void AgentFetchMustReturnTheProcessInput()
    {
        var yaml = TestPaths.Read("agent", "contoso-signin-triage-agent.yaml").Replace("| project AccountUpn", "| project Failures");
        Assert.Contains(Check(yaml), f => f.Message.Contains("needs an input named 'AccountUpn'"));
    }

    [Fact] public void AgentTriggerMustNameARealProcessSkill()
    {
        var yaml = TestPaths.Read("agent", "contoso-signin-triage-agent.yaml").Replace("Contoso.SignInTriageAgent.TriageSignInFailures", "Contoso.SignInTriageAgent.Nope");
        Assert.Contains(Check(yaml), f => f.Path.EndsWith("ProcessSkill") && f.Severity == Severity.Error);
    }

    [Fact] public void AgentNeedsAtLeastOneTrigger()
    {
        var yaml = TestPaths.Read("agent", "contoso-signin-triage-agent.yaml");
        var cut = yaml[..yaml.IndexOf("    Triggers:", StringComparison.Ordinal)];
        Assert.Contains(Check(cut), f => f.Path.EndsWith("Triggers"));
    }

    [Fact] public void TriggerNameCannotContainWhitespace() =>
        Assert.Contains(Check(TestPaths.Read("agent", "contoso-signin-triage-agent.yaml").Replace("Name: Hourly", "Name: Every hour")), f => f.Path.EndsWith("Triggers[0].Name"));

    [Fact] public void NegativePeriodIsAnError() =>
        Assert.Contains(Check(TestPaths.Read("agent", "contoso-signin-triage-agent.yaml").Replace("3600", "-5")), f => f.Path.EndsWith("DefaultPeriodSeconds"));

    [Fact] public void ZeroPeriodIsAllowed() =>
        Assert.DoesNotContain(Check(TestPaths.Read("agent", "contoso-signin-triage-agent.yaml").Replace("3600", "0")), f => f.Severity == Severity.Error);

    [Fact] public void SingleInstanceConstraintIsValidated() =>
        Assert.Contains(Check(TestPaths.Read("agent", "contoso-signin-triage-agent.yaml").Replace("AgentSingleInstanceConstraint: None", "AgentSingleInstanceConstraint: Forest")), f => f.Path.EndsWith("AgentSingleInstanceConstraint"));

    [Fact] public void ChildSkillWithoutAProviderIsAnError()
    {
        var yaml = TestPaths.Read("agent", "contoso-signin-triage-agent.yaml").Replace("      - Contoso.SocHunting\n", "");
        Assert.Contains(Check(yaml), f => f.Path.Contains("ChildSkills") && f.Severity == Severity.Error);
    }

    [Fact] public void BrokenSampleReportsEveryPlantedMistake()
    {
        var r = File("samples", "broken-plugin.yaml");
        Assert.Contains(r, f => f.Path == "Descriptor.Name");
        Assert.Contains(r, f => f.Path == "Descriptor.Description");
        Assert.Contains(r, f => f.Path.EndsWith("Skills[0].Name"));
        Assert.Contains(r, f => f.Message.Contains("outside a string literal"));
        Assert.Contains(r, f => f.Message.Contains("AccountUPN"));
        Assert.Contains(r, f => f.Message.Contains("AADSignInEventsBeta"));
        Assert.Contains(r, f => f.Message.Contains("not bounded"));
        Assert.Contains(r, f => f.Message.Contains("time filter"));
        Assert.Contains(r, f => f.Message.Contains("gpt-4.1"));
        Assert.Contains(r, f => f.Message.Contains("{{Rows}}"));
        Assert.True(r.Errors() >= 8);
    }
}
