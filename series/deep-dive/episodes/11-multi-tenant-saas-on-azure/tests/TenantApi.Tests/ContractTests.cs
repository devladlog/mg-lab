using System.Text.RegularExpressions;

namespace TenantApi.Tests;

/// <summary>Source and infrastructure rules that are cheap to check and expensive to get wrong.</summary>
public class ContractTests
{
    static IEnumerable<string> SourceFiles() =>
        Directory.EnumerateFiles(Paths.Of("src", "TenantApi"), "*.cs", SearchOption.AllDirectories)
            .Where(f => !f.Contains($"{Path.DirectorySeparatorChar}obj{Path.DirectorySeparatorChar}") && !f.Contains($"{Path.DirectorySeparatorChar}bin{Path.DirectorySeparatorChar}"));

    [Fact]
    public void The_application_never_bypasses_the_query_filter_or_runs_raw_sql()
    {
        foreach (var f in SourceFiles())
        {
            var text = File.ReadAllText(f);
            Assert.DoesNotContain("IgnoreQueryFilters", text);
            Assert.DoesNotMatch(new Regex(@"FromSql|ExecuteSql|SqlQuery"), text.Replace("sp_set_session_context", ""));
        }
    }

    [Fact]
    public void No_tenant_is_ever_read_from_a_header_a_route_or_a_name_claim()
    {
        foreach (var f in SourceFiles())
        {
            var text = File.ReadAllText(f);
            Assert.DoesNotMatch(new Regex(@"Headers\[|GetValueOrDefault\(""(X-)?Tenant|""X-Tenant", RegexOptions.IgnoreCase), text);
            // Learn: email, preferred_username, unique_name and upn are not safe to authorize with.
            Assert.DoesNotMatch(new Regex(@"FindFirst\(""(email|preferred_username|unique_name|upn)""\)"), text);
        }
    }

    [Fact]
    public void The_only_tenant_source_is_the_tid_claim()
    {
        var uses = SourceFiles().SelectMany(f => Regex.Matches(File.ReadAllText(f), @"FindFirst\(""tid""\)").Select(_ => Path.GetFileName(f))).ToList();
        Assert.Contains("TenantContext.cs", uses);
    }

    static string Bicep => File.ReadAllText(Paths.Of("infra", "main.bicep"));

    [Fact]
    public void Infrastructure_has_no_passwords_and_uses_the_free_database_offer()
    {
        Assert.Contains("azureADOnlyAuthentication: true", Bicep);
        Assert.DoesNotContain("administratorLoginPassword", Bicep);
        Assert.DoesNotMatch(new Regex(@"Password\s*=", RegexOptions.IgnoreCase), Bicep);
        Assert.Contains("useFreeLimit: true", Bicep);
        Assert.Contains("freeLimitExhaustionBehavior: 'AutoPause'", Bicep);
        Assert.Contains("minimalTlsVersion: '1.2'", Bicep);
        Assert.Contains("httpsOnly: true", Bicep);
        Assert.Contains("ftpsState: 'Disabled'", Bicep);
    }

    [Fact]
    public void The_app_receives_exactly_the_settings_the_code_reads()
    {
        foreach (var setting in new[] { "Entra__ClientId", "Entra__HomeTenantId" })
            Assert.Contains(setting, Bicep);
        Assert.Contains("Active Directory Default", Bicep);   // managed identity, no secret
        var code = string.Join("\n", SourceFiles().Select(File.ReadAllText));
        Assert.Contains("ClientId", code);
        Assert.Contains("HomeTenantId", code);
    }
}
