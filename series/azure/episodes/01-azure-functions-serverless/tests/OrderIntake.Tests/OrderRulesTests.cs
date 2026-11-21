using OrderIntake.Core;

namespace OrderIntake.Tests;

public class OrderRulesTests
{
    private static OrderRequest Order(params OrderLine[] lines) => new("C-1001", lines);

    [Fact]
    public void A_valid_order_has_no_errors() =>
        Assert.Empty(OrderRules.Validate(Order(new OrderLine("DOC-100", 2), new("CBL-001", 3))));

    [Fact]
    public void Null_body_is_rejected() =>
        Assert.Equal(["Body must be a JSON order."], OrderRules.Validate(null));

    [Fact]
    public void Customer_is_required()
    {
        var errors = OrderRules.Validate(new OrderRequest(" ", [new("DOC-100", 1)]));
        Assert.Contains("customerId is required.", errors);
    }

    [Fact]
    public void At_least_one_line_is_required() =>
        Assert.Contains("At least one line is required.", OrderRules.Validate(Order()));

    [Theory]
    [InlineData("doc-100")]
    [InlineData("DOC100")]
    [InlineData("DOCK-100")]
    [InlineData("")]
    public void Sku_must_match_the_pattern(string sku) =>
        Assert.Contains("lines[0].sku must look like ABC-123.", OrderRules.Validate(Order(new OrderLine(sku, 1))));

    [Theory]
    [InlineData(0)]
    [InlineData(-1)]
    [InlineData(101)]
    public void Quantity_must_be_between_1_and_100(int qty) =>
        Assert.Contains("lines[0].quantity must be between 1 and 100.", OrderRules.Validate(Order(new OrderLine("DOC-100", qty))));

    [Theory]
    [InlineData(1)]
    [InlineData(100)]
    public void Quantity_boundaries_are_valid(int qty) =>
        Assert.Empty(OrderRules.Validate(Order(new OrderLine("DOC-100", qty))));

    [Fact]
    public void More_than_20_lines_is_rejected()
    {
        var lines = Enumerable.Range(0, 21).Select(i => new OrderLine($"ABC-{i:000}", 1)).ToArray();
        Assert.Contains("An order can have at most 20 lines.", OrderRules.Validate(Order(lines)));
    }

    [Fact]
    public void Duplicate_skus_must_be_merged() =>
        Assert.Contains("SKU DOC-100 appears more than once; merge the lines.",
            OrderRules.Validate(Order(new OrderLine("DOC-100", 1), new("DOC-100", 2))));

    [Fact]
    public void A_well_formed_but_unknown_sku_passes_validation() =>
        // Shape only. The catalogue check happens later, in the queue function.
        Assert.Empty(OrderRules.Validate(Order(new OrderLine("ZZZ-999", 1))));
}
