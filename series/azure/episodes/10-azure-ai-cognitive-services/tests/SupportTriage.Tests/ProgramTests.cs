using Xunit;

namespace Contoso.SupportTriage.Tests;

[Collection("console")]
public class ProgramTests
{
    private static (int Exit, string Err) RunMain(params string[] args)
    {
        var original = Console.Error;
        var origEnv = Environment.GetEnvironmentVariable("LANGUAGE_ENDPOINT");
        Environment.SetEnvironmentVariable("LANGUAGE_ENDPOINT", null);
        using var err = new StringWriter();
        Console.SetError(err);
        try
        {
            var entry = typeof(Ticket).Assembly.EntryPoint!;
            var exit = (int)entry.Invoke(null, [args])!;
            return (exit, err.ToString());
        }
        finally
        {
            Console.SetError(original);
            Environment.SetEnvironmentVariable("LANGUAGE_ENDPOINT", origEnv);
        }
    }

    [Fact]
    public void Dry_run_estimates_the_free_tier_use_without_any_network_call()
    {
        var (exit, err) = RunMain("--dry-run");
        Assert.Equal(0, exit);
        Assert.Contains("text records (estimate): 21 = language 7, pii 7, sentiment 7", err);
        Assert.Contains("238 such runs per month", err);
    }

    [Fact]
    public void Without_an_endpoint_it_stops_with_exit_code_two()
    {
        var (exit, err) = RunMain();
        Assert.Equal(2, exit);
        Assert.Contains("LANGUAGE_ENDPOINT", err);
    }
}

[CollectionDefinition("console", DisableParallelization = true)]
public class ConsoleCollection;
