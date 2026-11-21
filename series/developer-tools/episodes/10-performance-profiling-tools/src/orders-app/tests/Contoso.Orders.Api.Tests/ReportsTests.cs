using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Contoso.Orders.Api;

namespace Contoso.Orders.Api.Tests;

/// <summary>The monthly revenue report. The first test is the reproduction of the bug in the support ticket.</summary>
public class ReportsTests(ApiFactory factory) : IClassFixture<ApiFactory>
{
    private readonly HttpClient _client = factory.CreateClient();

    // The seed data has an order on every day of 2026-01-01 .. 2026-10-27, including the last day of January.
    private static IEnumerable<Order> Seed => OrdersDb.SeedData(237);

    [Fact]
    public async Task MonthEnd_orders_are_part_of_the_month()
    {
        var january = await _client.GetFromJsonAsync<MonthlyRevenue>("/reports/monthly?month=2026-01");

        var expected = Seed.Where(o => o.Created.Month == 1).ToList();
        Assert.Contains(expected, o => o.Created == new DateOnly(2026, 1, 31));   // the case that went missing
        Assert.Equal(expected.Count, january!.Orders);
        Assert.Equal(expected.Sum(o => o.Total), january.Total);
    }

    [Fact]
    public async Task Every_order_lands_in_exactly_one_month()
    {
        var orders = 0;
        var total = 0m;
        for (var month = 1; month <= 12; month++)
        {
            var report = await _client.GetFromJsonAsync<MonthlyRevenue>($"/reports/monthly?month=2026-{month:00}");
            orders += report!.Orders;
            total += report.Total;
        }

        Assert.Equal(237, orders);
        Assert.Equal(Seed.Sum(o => o.Total), total);
    }

    [Fact]
    public async Task Customers_are_sorted_by_revenue_and_add_up_to_the_total()
    {
        var report = await _client.GetFromJsonAsync<MonthlyRevenue>("/reports/monthly?month=2026-03");

        Assert.NotEmpty(report!.Customers);
        Assert.Equal(report.Customers.OrderByDescending(c => c.Revenue), report.Customers);
        Assert.Equal(report.Total, report.Customers.Sum(c => c.Revenue));
        Assert.Equal(report.Orders, report.Customers.Sum(c => c.Orders));
    }

    [Theory]
    [InlineData("2026-1")]
    [InlineData("2026-13")]
    [InlineData("March")]
    [InlineData("")]
    public async Task A_value_that_is_not_a_month_is_a_validation_problem(string month)
    {
        var response = await _client.GetAsync($"/reports/monthly?month={month}");
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        var body = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.True(body.GetProperty("errors").TryGetProperty("month", out _));
    }

    [Fact]
    public async Task The_second_request_for_a_month_comes_from_the_cache_until_it_is_invalidated()
    {
        using var own = new ApiFactory();
        var client = own.CreateClient();
        await client.GetAsync("/reports/monthly?month=2026-02");
        await client.GetAsync("/reports/monthly?month=2026-02");
        var stats = await client.GetFromJsonAsync<CacheStats>("/reports/cache");
        Assert.Equal(new CacheStats(1, 1, 1), stats);

        Assert.Equal(HttpStatusCode.NoContent, (await client.PostAsync("/reports/cache/invalidate", null)).StatusCode);
        Assert.Equal(new CacheStats(0, 0, 0), await client.GetFromJsonAsync<CacheStats>("/reports/cache"));
    }

    [Fact]
    public async Task Problem_details_carry_the_trace_id_support_asks_for()
    {
        // A caller that sends a W3C traceparent header gets its own trace id back, inside the "traceId" field.
        const string trace = "4bf92f3577b34da6a3ce929d0e0e4736";
        using var request = new HttpRequestMessage(HttpMethod.Get, "/reports/monthly?month=nope");
        request.Headers.Add("traceparent", $"00-{trace}-00f067aa0ba902b7-01");

        var body = await (await _client.SendAsync(request)).Content.ReadFromJsonAsync<JsonElement>();

        // The field holds Activity.Id (traceparent format: version-traceid-spanid-flags), not the bare trace id.
        // Logs carry the bare 32 characters as TraceId, so to search them take the middle part.
        var traceId = body.GetProperty("traceId").GetString();
        Assert.Matches("^00-[0-9a-f]{32}-[0-9a-f]{16}-0[01]$", traceId);
        Assert.Equal(trace, traceId!.Split('-')[1]);
    }
}
