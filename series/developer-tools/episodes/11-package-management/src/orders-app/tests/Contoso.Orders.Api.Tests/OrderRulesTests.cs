namespace Contoso.Orders.Api.Tests;

public class OrderRulesTests
{
    [Fact]
    public void A_complete_order_has_no_errors() => Assert.Empty(OrderRules.Validate(new NewOrder("Alex Demo", 19.99m)));

    [Theory]
    [InlineData(null, 10, "customer")]
    [InlineData("   ", 10, "customer")]
    [InlineData("Fabrikam", 0, "total")]
    [InlineData("Fabrikam", -1, "total")]
    public void Each_broken_rule_is_reported_under_its_field(string? customer, decimal total, string field)
        => Assert.True(OrderRules.Validate(new NewOrder(customer, total)).ContainsKey(field));

    [Fact]
    public void The_customer_limit_is_the_same_one_the_database_column_uses()
    {
        Assert.Empty(OrderRules.Validate(new NewOrder(new string('x', OrderRules.MaxCustomerLength), 1m)));
        Assert.Contains("customer", OrderRules.Validate(new NewOrder(new string('x', OrderRules.MaxCustomerLength + 1), 1m)));
        // Order.Customer is [MaxLength(100)]: the two numbers must not drift apart.
        var max = typeof(Order).GetProperty(nameof(Order.Customer))!
            .GetCustomAttributes(typeof(System.ComponentModel.DataAnnotations.MaxLengthAttribute), false)
            .Cast<System.ComponentModel.DataAnnotations.MaxLengthAttribute>().Single().Length;
        Assert.Equal(OrderRules.MaxCustomerLength, max);
    }
}
