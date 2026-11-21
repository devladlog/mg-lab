using System.Net;
using System.Net.Http;
using Xunit;

namespace ContosoHolidays.Tests;

/// <summary>
/// The same script against the real date.nager.at (free, no key). Skipped unless LIVE_HOLIDAYS=1, so the normal test
/// run never depends on the internet: LIVE_HOLIDAYS=1 dotnet test --filter Category=Live
/// </summary>
[Trait("Category", "Live")]
public class LiveTests
{
    private static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(30) };

    public sealed class LiveFact : FactAttribute
    {
        public LiveFact()
        {
            if (Environment.GetEnvironmentVariable("LIVE_HOLIDAYS") != "1") Skip = "set LIVE_HOLIDAYS=1 to call date.nager.at";
        }
    }

    [LiveFact]
    public async Task The_real_source_gives_Portuguese_days_off_for_this_year_and_next()
    {
        var year = DateTime.UtcNow.Year;
        var (response, body) = await ScriptRunner.RunAsync("GetDaysOff",
            $"https://date.nager.at/api/v3/DaysOff/PT?fromYear={year}&toYear={year + 1}", (r, ct) => Http.SendAsync(r, ct));

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var dates = body!["days"]!.Select(d => (string)d["date"]!).ToList();
        Assert.Contains($"{year}-12-25", dates);
        Assert.Contains($"{year + 1}-01-01", dates);
        Assert.InRange((int)body["count"]!, 20, 40);
        Assert.Contains(body["excluded"]!, e => (string)e["name"]! == "Carnival");
    }

    [LiveFact]
    public async Task The_real_source_says_404_for_an_unknown_country()
    {
        var (response, body) = await ScriptRunner.RunAsync("GetDaysOff",
            "https://date.nager.at/api/v3/DaysOff/XX?fromYear=2026", (r, ct) => Http.SendAsync(r, ct));

        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
        Assert.StartsWith("The holiday source returned 404 for XX 2026", (string)body!["message"]!);
    }
}
