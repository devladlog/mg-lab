using System.Globalization;
using Xunit;

namespace ContosoPurchasing.Tests;

public class ValidatorTests
{
    private static readonly CultureInfo Pt = new("pt-PT");
    private static readonly CultureInfo En = new("en-US");

    [Fact]
    public void Valid_order_passes() =>
        Assert.True(OrderValidator.Validate("Contoso Office Supplies", "USB-C cables", "120", En).IsValid);

    [Fact]
    public void Amount_is_read_with_the_culture_of_the_machine()
    {
        Assert.Equal(1800.50m, OrderValidator.Validate("s", "d", "1800,50", Pt).Amount);
        Assert.Equal(1800.50m, OrderValidator.Validate("s", "d", "1800.50", En).Amount);
        // the trap: the same text means something else (en-US reads the comma as a thousands separator)
        // or nothing at all (pt-PT does not accept the dot)
        Assert.Equal(180050m, OrderValidator.Validate("s", "d", "1800,50", En).Amount);
        Assert.Contains("Amount is not a number", OrderValidator.Validate("s", "d", "1800.50", Pt).Errors);
    }

    [Theory]
    [InlineData("", "d", "10", "Supplier is required")]
    [InlineData("s", " ", "10", "Description is required")]
    [InlineData("s", "d", "abc", "Amount is not a number")]
    [InlineData("s", "d", "0", "Amount must be greater than zero")]
    [InlineData("s", "d", "100001", "Amount is above the limit of 100000")]
    public void Invalid_orders_say_why(string s, string d, string a, string expected) =>
        Assert.Contains(expected, OrderValidator.Validate(s, d, a, En).Errors);
}

public class LedgerTests : IDisposable
{
    private readonly string _dir = Path.Combine(Path.GetTempPath(), "contoso-ledger-" + Guid.NewGuid().ToString("N"));
    private string File_ => Path.Combine(_dir, "orders.csv");
    public void Dispose() { if (Directory.Exists(_dir)) Directory.Delete(_dir, true); }

    [Fact]
    public void Orders_are_numbered_per_year_and_round_trip_with_quotes_and_commas()
    {
        var ledger = new OrderLedger(File_);
        var t = new DateTimeOffset(2026, 1, 5, 9, 0, 0, TimeSpan.Zero);
        var a = ledger.Append("Contoso, Lda", "Chairs \"ergonomic\"", 1800.5m, "alex.demo", t);
        var b = ledger.Append("Fabrikam", "Laptops", 12500m, "alex.demo", t.AddMinutes(1));
        var c = ledger.Append("Fabrikam", "Docks", 300m, "alex.demo", t.AddYears(1));
        Assert.Equal(new[] { "PO-2026-0001", "PO-2026-0002", "PO-2027-0001" }, new[] { a.OrderNo, b.OrderNo, c.OrderNo });
        var all = ledger.ReadAll();
        Assert.Equal(3, all.Count);
        Assert.Equal("Contoso, Lda", all[0].Supplier);
        Assert.Equal("Chairs \"ergonomic\"", all[0].Description);
        Assert.Equal(1800.5m, all[0].Amount);
        Assert.StartsWith(OrderLedger.Header, System.IO.File.ReadAllText(File_));
        Assert.Contains("1800.50", System.IO.File.ReadAllText(File_));  // invariant format on disk
    }

    [Fact]
    public void A_missing_ledger_is_empty() => Assert.Empty(new OrderLedger(File_).ReadAll());
}
