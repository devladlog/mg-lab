using System.Reflection;

namespace ProjectRequests.Features.Tests;

public class CSharp12Tests
{
    private sealed class FixedClock(DateTimeOffset now) : TimeProvider
    {
        public override DateTimeOffset GetUtcNow() => now;
    }

    private static readonly DateTimeOffset Now = new(2026, 11, 21, 10, 0, 0, TimeSpan.Zero);

    [Fact]
    public void Primary_constructor_parameters_are_used_by_every_member()
    {
        var report = new RequestReport(SampleData.Requests, new FixedClock(Now));

        Assert.Equal(4, report.OpenCount);                                      // ids 2, 3, 6, 8 are Submitted
        Assert.Equal(Now.UtcDateTime, report.GeneratedAtUtc);
    }

    [Fact]
    public void Alias_any_type_and_default_parameter_give_a_named_tuple()
    {
        var report = new RequestReport(SampleData.Requests, TimeProvider.System);

        var (amount, currency) = report.Total();
        Assert.Equal(673_500m, amount);
        Assert.Equal("EUR", currency);
        Assert.Equal("USD", report.Total("USD").Currency);
    }

    [Fact]
    public void Collection_expressions_with_spread_put_high_priority_first_and_lose_nothing()
    {
        var report = new RequestReport(SampleData.Requests, TimeProvider.System);

        var ordered = report.HighThenStandard();

        Assert.Equal(SampleData.Requests.Count, ordered.Count);
        Assert.All(ordered.Take(4), r => Assert.Equal(Priority.High, r.Priority));
        Assert.All(ordered.Skip(4), r => Assert.Equal(Priority.Standard, r.Priority));
    }

    [Fact]
    public void Lambda_default_parameter_is_used_when_the_argument_is_left_out()
    {
        Assert.Equal(["1,234.50 EUR", "0.00 EUR"], RequestReport.FormatAll([1234.5m, 0m]));
    }

    [Fact]
    public void A_class_primary_constructor_parameter_is_mutable_captured_state_not_a_property()
    {
        var ticket = new Ticket(5);

        Assert.Equal([5, 6, 7], [ticket.Next(), ticket.Next(), ticket.Next()]);   // the parameter itself is incremented
        Assert.Null(typeof(Ticket).GetProperty("start", BindingFlags.Public | BindingFlags.Instance | BindingFlags.IgnoreCase));
        Assert.NotNull(typeof(TicketRange).GetProperty("Start"));                 // records do get a property
    }
}
