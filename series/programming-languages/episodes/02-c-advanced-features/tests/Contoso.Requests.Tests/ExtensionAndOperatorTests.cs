using SpanMath;
using Contoso.Requests;

namespace Contoso.Requests.Tests;

public class ExtensionAndOperatorTests
{
    private static readonly ProjectRequest[] Requests =
    [
        TestData.Request(18_000m, number: 1),
        TestData.Request(75_000m, number: 2),
        TestData.Request(300_000m, "Board level investment", number: 3) with { State = new RequestState.Submitted(TestData.Now) },
    ];

    [Fact]
    public void Extension_properties_on_IEnumerable()
    {
        Assert.Equal(new Euros(393_000m), Requests.TotalBudget);
        Assert.Equal([2, 3], Requests.HighPriority.Select(r => r.Code.Number));
        Assert.Single(Requests.InState<RequestState.Submitted>());
    }

    [Fact]
    public void Extension_property_on_a_framework_type() =>
        Assert.Equal(new DateOnly(2026, 11, 21), new FixedClock(TestData.Now).Today);

    [Fact]
    public void Static_extension_member_appears_on_the_type() =>
        Assert.Equal(new Euros(75_000m), Euros.FromThousands(75));

    [Fact]
    public void Span_extension_is_found_on_an_array_thanks_to_implicit_span_conversions()
    {
        int[] budgets = [18, 75, 300];
        decimal[] precise = [1m, 2m];
        Assert.Equal(131, budgets.Mean());
        Assert.Equal(1.5m, precise.Mean());
        Assert.Throws<InvalidOperationException>(() => Array.Empty<int>().Mean());
    }

    [Fact]
    public void User_defined_compound_assignment_mutates_in_place()
    {
        var tally = new BudgetTally();
        var same = tally;
        foreach (var r in Requests) tally += r;

        Assert.Same(same, tally); // no new instance was created
        Assert.Equal(3, tally.Count);
        Assert.Equal(new Euros(393_000m), tally.Total);
        Assert.Equal(new Euros(300_000m), tally.Largest);
    }
}

public class CSharp14BindingTests
{
    [Fact]
    public void Gotcha_a_span_extension_now_beats_LINQ_on_an_array()
    {
        int[] values = [1, 2, 3];
        // Same source as demo/Gotchas/LinqClash.cs. C# 13 called Enumerable.Average (2); C# 14 calls the span one.
        Assert.Equal(-1, SpanMath.SpanAverage.Average(values));
        Assert.Equal(-1, values.Average());
        Assert.Equal(2, Enumerable.Average(values)); // explicit static call: the safe way to mean LINQ
    }
}
