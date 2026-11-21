using static ModernizationScan.Tests.Fixtures;

namespace ModernizationScan.Tests;

public class ScannerTests
{
    private static Report Legacy() => Scanner.Scan(Fixtures.Legacy);

    [Fact]
    public void Legacy_fixture_has_three_legacy_projects_with_packages_config()
    {
        var r = Legacy();
        Assert.Equal(3, r.Projects.Count);
        Assert.All(r.Projects, p => { Assert.False(p.IsSdkStyle); Assert.True(p.UsesPackagesConfig); Assert.Equal("net472", p.TargetFramework); });
        Assert.Contains(r.Projects.Single(p => p.Name == "Contoso.Pricing").Packages, p => p.Id == "Newtonsoft.Json" && p.Version == "12.0.3");
    }

    [Fact]
    public void Only_the_web_project_is_a_web_application()
    {
        var web = Legacy().Projects.Where(p => p.IsWebApplication).Select(p => p.Name);
        Assert.Equal(["Contoso.Orders.Web"], web);
    }

    [Fact]
    public void Upgrade_order_puts_the_library_before_its_consumers()
    {
        var order = Legacy().UpgradeOrder;
        Assert.Equal("Contoso.Pricing", order[0]);
        Assert.Equal(3, order.Count);
    }

    [Fact]
    public void Findings_name_the_learn_scenarios_and_skills_for_the_fixture()
    {
        var caps = Legacy().Findings.Select(f => f.LearnCapability).Where(c => c is not null).Cast<string>().ToHashSet();
        Assert.Contains("SDK-style conversion (scenario)", caps);
        Assert.Contains("Newtonsoft.Json upgrade (scenario) / Upgrading Newtonsoft to System.Text.Json (skill)", caps);
        Assert.Contains("Upgrading to Microsoft.Data.SqlClient (skill)", caps);
        Assert.Contains("Upgrading MVC HttpContext (skill)", caps);
        Assert.Contains("Upgrading Global.asax (skill)", caps);
        Assert.Contains("Upgrading MVC session state (skill)", caps);
        Assert.Contains("Upgrading ASP.NET Framework to Core (skill)", caps);
    }

    [Fact]
    public void Sql_client_code_is_found_in_the_library_not_the_web_project()
    {
        var f = Legacy().Findings.Where(f => f.What == "using System.Data.SqlClient").Select(f => f.Project).Distinct();
        Assert.Equal(["Contoso.Pricing"], f);
    }

    [Fact]
    public void Evidence_points_at_a_real_file_and_line()
    {
        var f = Legacy().Findings.First(f => f.What == "HttpContext.Current");
        var (file, line) = (f.Evidence[..f.Evidence.LastIndexOf(':')], int.Parse(f.Evidence[(f.Evidence.LastIndexOf(':') + 1)..]));
        var text = File.ReadAllLines(Path.Combine(Fixtures.Legacy, file))[line - 1];
        Assert.Contains("HttpContext.Current", text);
    }

    [Fact]
    public void Strategy_is_bottom_up_when_there_is_a_web_app()
    {
        Assert.StartsWith("bottom-up", Legacy().SuggestedStrategy);
    }

    [Fact]
    public void Expected_after_tree_is_sdk_style_net10_and_has_no_findings()
    {
        var r = Scanner.Scan(Fixtures.ExpectedAfter);
        Assert.Equal(2, r.Projects.Count);
        Assert.All(r.Projects, p => { Assert.True(p.IsSdkStyle); Assert.Equal("net10.0", p.TargetFramework); Assert.False(p.UsesPackagesConfig); });
        Assert.Empty(r.Findings);
        Assert.Equal(0, r.Score);
    }

    [Fact]
    public void Sdk_project_reads_package_versions_from_attribute_and_child_element()
    {
        using var t = new Temp();
        t.Write("a/a.csproj", Sdk("""<ItemGroup><PackageReference Include="Newtonsoft.Json" Version="13.0.3" /><PackageReference Include="Autofac"><Version>7.1.0</Version></PackageReference></ItemGroup>"""));
        var p = Scanner.Scan(t.Path).Projects.Single();
        Assert.True(p.IsSdkStyle);
        Assert.Equal([new PackageRef("Autofac", "7.1.0"), new PackageRef("Newtonsoft.Json", "13.0.3")], p.Packages);
    }

    [Fact]
    public void Multi_targeting_is_read_as_one_string()
    {
        using var t = new Temp();
        t.Write("a/a.csproj", """<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><TargetFrameworks>net48;net10.0</TargetFrameworks></PropertyGroup></Project>""");
        Assert.Equal("net48;net10.0", Scanner.Scan(t.Path).Projects.Single().TargetFramework);
    }

    [Theory]
    [InlineData("v4.5", true)]
    [InlineData("v4.6.1", true)]
    [InlineData("v4.6.2", false)]
    [InlineData("v4.7.2", false)]
    [InlineData("v4.8", false)]
    public void Old_framework_targets_are_flagged(string version, bool flagged)
    {
        using var t = new Temp();
        t.Write("a/a.csproj", LegacyProject(tfv: version));
        var found = Scanner.Scan(t.Path).Findings.Any(f => f.What.Contains("an old .NET Framework"));
        Assert.Equal(flagged, found);
    }

    [Fact]
    public void Order_is_leaves_first_and_ties_are_alphabetical()
    {
        using var t = new Temp();
        t.Write("App/App.csproj", LegacyProject(ProjectRef("Mid") + ProjectRef("Zed")));
        t.Write("Mid/Mid.csproj", LegacyProject(ProjectRef("Core")));
        t.Write("Core/Core.csproj", LegacyProject());
        t.Write("Zed/Zed.csproj", LegacyProject());
        Assert.Equal(["Core", "Zed", "Mid", "App"], Scanner.Scan(t.Path).UpgradeOrder);
    }

    [Fact]
    public void Reference_cycle_is_reported_not_looped()
    {
        using var t = new Temp();
        t.Write("A/A.csproj", LegacyProject(ProjectRef("B")));
        t.Write("B/B.csproj", LegacyProject(ProjectRef("A")));
        var r = Scanner.Scan(t.Path);
        Assert.Empty(r.UpgradeOrder);
        Assert.Contains(r.Warnings, w => w.Contains("cycle") && w.Contains("A") && w.Contains("B"));
    }

    [Fact]
    public void Small_solution_without_web_suggests_all_at_once()
    {
        using var t = new Temp();
        t.Write("A/A.csproj", Sdk());
        t.Write("B/B.csproj", Sdk());
        Assert.StartsWith("all-at-once", Scanner.Scan(t.Path).SuggestedStrategy);
    }

    [Fact]
    public void Build_output_and_package_folders_are_ignored()
    {
        using var t = new Temp();
        t.Write("A/A.csproj", Sdk());
        t.Write("A/obj/Other.csproj", LegacyProject());
        t.Write("packages/Some.1.0/lib/x.csproj", LegacyProject());
        t.Write("A/bin/Debug/leftover.cs", "using System.Data.SqlClient;");
        var r = Scanner.Scan(t.Path);
        Assert.Single(r.Projects);
        Assert.Empty(r.Findings);
    }

    [Fact]
    public void Code_without_a_listed_skill_still_produces_a_finding()
    {
        using var t = new Temp();
        t.Write("A/A.csproj", Sdk());
        t.Write("A/S.cs", "var f = new BinaryFormatter();");
        var f = Scanner.Scan(t.Path).Findings.Single();
        Assert.Equal("BinaryFormatter", f.What);
        Assert.Null(f.LearnCapability);
    }

    [Fact]
    public void Wcf_msmq_edmx_and_ef6_are_detected()
    {
        using var t = new Temp();
        t.Write("A/A.csproj", LegacyProject("""<Reference Include="System.Messaging" />"""));
        t.Write("A/packages.config", """<packages><package id="EntityFramework" version="6.4.4" targetFramework="net472" /></packages>""");
        t.Write("A/Svc.cs", "[ServiceContract]\npublic interface IX { }\nusing System.Messaging;");
        t.Write("A/Model.edmx", "<edmx />");
        var caps = Scanner.Scan(t.Path).Findings.Select(f => f.LearnCapability).ToHashSet();
        Assert.Contains("Upgrading WCF to CoreWCF (skill)", caps);
        Assert.Contains("Upgrading to MSMQ.Messaging (skill)", caps);
        Assert.Contains("Upgrading EDMX to Code-First (skill)", caps);
        Assert.Contains("Upgrading EF6 Code-First to EF Core (skill)", caps);
    }

    [Fact]
    public void Solution_entry_without_a_file_is_a_warning()
    {
        using var t = new Temp();
        t.Write("A/A.csproj", Sdk());
        t.Write("x.sln", "Project(\"{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}\") = \"Gone\", \"Gone\\Gone.csproj\", \"{00000000-0000-0000-0000-000000000009}\"\nEndProject\n");
        Assert.Contains(Scanner.Scan(t.Path).Warnings, w => w.Contains("Gone") && w.Contains("does not exist"));
    }

    [Fact]
    public void Bad_input_raises_clear_errors()
    {
        using var t = new Temp();
        Assert.Throws<InvalidOperationException>(() => Scanner.Scan(t.Path));
        Assert.Throws<DirectoryNotFoundException>(() => Scanner.Scan(Path.Combine(t.Path, "nope")));
    }

    [Fact]
    public void Markdown_and_json_reports_carry_the_same_facts()
    {
        var r = Legacy();
        var md = ReportWriter.ToMarkdown(r);
        Assert.Contains("| 1 | Contoso.Pricing |", md);
        Assert.Contains("Upgrading Global.asax (skill)", md);
        var json = System.Text.Json.JsonDocument.Parse(ReportWriter.ToJson(r)).RootElement;
        Assert.Equal(3, json.GetProperty("projects").GetArrayLength());
        Assert.Equal(r.Findings.Count, json.GetProperty("findings").GetArrayLength());
    }
}
