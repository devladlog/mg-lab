using Contoso.Orders.Api.Orders;

namespace Contoso.Orders.Tests;

public class RulesTests
{
    private static CreateOrderRequest Req(string? customer, params (string? Sku, int Qty)[] lines) =>
        new(customer, lines.Select(l => new OrderLineRequest(l.Sku, l.Qty)).ToList());

    [Fact]
    public void A_valid_order_has_no_errors() =>
        Assert.Empty(OrderRules.Validate(Req("alex-demo", ("MON-270", 2), ("DOC-100", 1))));

    [Theory]
    [InlineData(null, "MON-270", 1, "customerId")]
    [InlineData("alex-demo", "mon-270", 1, "sku")]
    [InlineData("alex-demo", "MON-270", 0, "quantity")]
    [InlineData("alex-demo", "MON-270", 101, "quantity")]
    public void Shape_errors_are_reported(string? customer, string sku, int qty, string field) =>
        Assert.Contains(OrderRules.Validate(Req(customer, (sku, qty))), e => e.StartsWith(field));

    [Fact]
    public void Duplicate_skus_and_empty_orders_are_rejected()
    {
        Assert.Contains("lines: duplicate SKU", OrderRules.Validate(Req("a", ("MON-270", 1), ("MON-270", 2))));
        Assert.Contains("lines: 1-20 lines", OrderRules.Validate(Req("a")));
        Assert.Equal(["body is required"], OrderRules.Validate(null));
    }

    [Fact]
    public void Request_hash_depends_on_content_not_line_order()
    {
        var a = OrderRules.RequestHash(Req("a", ("MON-270", 1), ("DOC-100", 2)));
        Assert.Equal(a, OrderRules.RequestHash(Req("a", ("DOC-100", 2), ("MON-270", 1))));
        Assert.NotEqual(a, OrderRules.RequestHash(Req("a", ("DOC-100", 3), ("MON-270", 1))));
        Assert.Equal(64, a.Length);
    }
}
