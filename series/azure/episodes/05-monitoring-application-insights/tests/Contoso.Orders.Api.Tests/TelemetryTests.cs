using System.Diagnostics;
using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Contoso.Orders.Api.Orders;

namespace Contoso.Orders.Api.Tests;

public class TelemetryTests
{
    private const string Customer = "CUST-4711-alex.demo@contoso.com"; // must never appear in telemetry

    private static object Order(string sku = "MON-270", string channel = "web") => new
    {
        customerId = Customer,
        channel,
        lines = new[] { new { sku, quantity = 2 }, new { sku = "KEY-010", quantity = 2 } },
    };

    [Fact]
    public async Task Created_order_emits_request_price_span_and_metrics()
    {
        await using var app = new TelemetryApp();
        var response = await app.CreateClient().PostAsJsonAsync("/orders", Order());

        Assert.Equal(HttpStatusCode.Created, response.StatusCode);
        var server = await app.ServerSpanAsync("/orders");
        var price = Assert.Single(app.Spans, s => s.DisplayName == "orders.price");

        // Same trace, and the custom span is a child of the request: one end-to-end transaction
        Assert.Equal(server.TraceId, price.TraceId);
        Assert.Equal(server.SpanId, price.ParentSpanId);
        Assert.Equal(ActivityKind.Internal, price.Kind);
        Assert.Equal("web", price.GetTagItem("order.channel"));
        Assert.Equal(2, price.GetTagItem("order.line_count"));
        Assert.Equal(538.98, (double)price.GetTagItem("order.total")!, 2);

        var created = Assert.Single(app.Points("contoso.orders.created"));
        Assert.Equal(1, created.GetSumLong());
        Assert.Equal("web", created.Tag("order.channel"));
        var value = Assert.Single(app.Points("contoso.orders.value"));
        Assert.Equal(538.98, value.GetHistogramSum(), 2);
    }

    [Fact]
    public async Task Customer_id_is_not_in_any_span_tag()
    {
        await using var app = new TelemetryApp();
        await app.CreateClient().PostAsJsonAsync("/orders", Order());
        await app.ServerSpanAsync("/orders");

        var leaked = app.Spans.SelectMany(s => s.TagObjects)
            .Where(t => t.Value?.ToString()?.Contains("CUST-4711") == true)
            .Select(t => t.Key).ToList();
        Assert.Empty(leaked);
    }

    [Fact]
    public async Task Invalid_order_is_400_but_not_a_failed_request()
    {
        await using var app = new TelemetryApp();
        var response = await app.CreateClient().PostAsJsonAsync("/orders", new { channel = "fax" });

        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        var server = await app.ServerSpanAsync("/orders");
        Assert.Equal(400, server.GetTagItem("http.response.status_code"));
        Assert.Equal(ActivityStatusCode.Ok, server.Status);          // success = true in Application Insights
        var rejected = Assert.Single(app.Points("contoso.orders.rejected"));
        Assert.Equal("invalid", rejected.Tag("order.reject_reason"));
    }

    [Fact]
    public async Task Unknown_sku_is_422_with_an_error_on_the_price_span()
    {
        await using var app = new TelemetryApp();
        var response = await app.CreateClient().PostAsJsonAsync("/orders", Order(sku: "ZZZ-999"));

        Assert.Equal(HttpStatusCode.UnprocessableEntity, response.StatusCode);
        var server = await app.ServerSpanAsync("/orders");
        Assert.Equal(ActivityStatusCode.Ok, server.Status);
        var price = Assert.Single(app.Spans, s => s.DisplayName == "orders.price");
        Assert.Equal(ActivityStatusCode.Error, price.Status);
        Assert.Equal("unknown SKU", price.StatusDescription);
        Assert.Equal("unknown_sku", Assert.Single(app.Points("contoso.orders.rejected")).Tag("order.reject_reason"));
    }

    [Fact]
    public async Task Unknown_order_id_is_404_and_not_a_failure()
    {
        await using var app = new TelemetryApp();
        var response = await app.CreateClient().GetAsync("/orders/does-not-exist");

        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
        Assert.Equal(ActivityStatusCode.Ok, (await app.ServerSpanAsync("/orders/{orderId}")).Status);
    }

    [Fact]
    public async Task Injected_fault_is_a_500_failed_request_and_no_order_is_counted()
    {
        await using var app = new TelemetryApp(failurePercent: 20, diceRoll: 5); // 5 < 20: this save fails
        var response = await app.CreateClient().PostAsJsonAsync("/orders", Order());

        Assert.Equal(HttpStatusCode.InternalServerError, response.StatusCode);
        var server = await app.ServerSpanAsync("/orders");
        Assert.Equal(500, server.GetTagItem("http.response.status_code"));
        Assert.Equal(ActivityStatusCode.Error, server.Status);       // success = false: the alert counts this
        // The exception reaches Application Insights as a log record (exceptions table), in the same
        // trace as the request, so the end-to-end view shows both together
        var logged = Assert.Single(app.Logs, l => l.Exception is InjectedFaultException);
        Assert.Equal(server.TraceId, logged.TraceId);
        Assert.Empty(app.Points("contoso.orders.created"));
    }

    [Fact]
    public async Task Healthz_and_a_stored_order_round_trip()
    {
        await using var app = new TelemetryApp();
        var client = app.CreateClient();
        Assert.Equal(HttpStatusCode.OK, (await client.GetAsync("/healthz")).StatusCode);

        var created = await (await client.PostAsJsonAsync("/orders", Order())).Content.ReadFromJsonAsync<JsonElement>();
        var id = created.GetProperty("orderId").GetString();
        var stored = await client.GetFromJsonAsync<JsonElement>($"/orders/{id}");
        Assert.Equal(538.98m, stored.GetProperty("total").GetDecimal());
    }
}
