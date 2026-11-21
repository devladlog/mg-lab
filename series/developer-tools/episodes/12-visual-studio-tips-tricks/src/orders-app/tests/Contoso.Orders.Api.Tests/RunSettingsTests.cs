namespace Contoso.Orders.Api.Tests;

/// <summary>
/// Passes only when the test host was started with the repository's .runsettings (Test Explorer in Visual Studio,
/// `dotnet test` and the pipeline all get it through RunSettingsFilePath in Directory.Build.props).
/// If someone runs the assembly with `dotnet vstest` or another runner that ignores the property, this test fails
/// with the reason in its message instead of letting the other settings be skipped silently.
/// </summary>
public class RunSettingsTests
{
    [Fact, Trait("Category", "Smoke")]
    public void The_repository_runsettings_reached_the_test_host()
    {
        var region = Environment.GetEnvironmentVariable("CONTOSO_REGION");

        Assert.True(region == "lab-west",
            $"CONTOSO_REGION is '{region ?? "(not set)"}': the .runsettings file did not reach the test host. " +
            "Run through the solution or project (RunSettingsFilePath), or pass --settings .runsettings.");
    }
}
