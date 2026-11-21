using Contoso.Requests;

namespace Contoso.Requests.Tests;

public class ValueTypeTests
{
    [Theory]
    [InlineData("PR-2026-0042", 2026, 42)]
    [InlineData("PR-2099-9999", 2099, 9999)]
    public void RequestCode_parses_from_a_span(string text, int year, int number)
    {
        Assert.True(RequestCode.TryParse(text.AsSpan(), out var code));
        Assert.Equal(new RequestCode(year, number), code);
        Assert.Equal(text, code.ToString());
    }

    [Theory]
    [InlineData("PR-26-42")]
    [InlineData("PR-2026-0000")]
    [InlineData("PR-1999-0001")]
    [InlineData("XX-2026-0001")]
    [InlineData("PR-2026_0001")]
    [InlineData("PR-2026-00a1")]
    [InlineData("PR-2026-+001")]
    [InlineData("")]
    public void RequestCode_rejects_bad_input(string text) => Assert.False(RequestCode.TryParse(text, null, out _));

    [Fact]
    public void RequestCode_Parse_throws_FormatException() =>
        Assert.Throws<FormatException>(() => RequestCode.Parse("nope", null));

    [Fact]
    public void Parsing_a_slice_of_a_larger_string_allocates_nothing()
    {
        var text = "PR-2026-0042,PR-2026-0043,PR-2026-0044".AsSpan();
        Assert.True(RequestCode.TryParse(text[..12], out _)); // warm up (JIT) outside the measurement

        var before = GC.GetAllocatedBytesForCurrentThread();
        var found = 0;
        foreach (var range in text.Split(','))
            if (RequestCode.TryParse(text[range], out _)) found++;
        var allocated = GC.GetAllocatedBytesForCurrentThread() - before;

        Assert.Equal(3, found);
        Assert.Equal(0, allocated);
    }

    [Fact]
    public void Email_is_normalised_and_validated()
    {
        Assert.Equal("alex.demo@contoso.com", EmailAddress.Parse("  Alex.Demo@Contoso.COM ").Value);
        Assert.False(EmailAddress.TryParse("alex.demo", out _));
        Assert.False(EmailAddress.TryParse(null, out _));
        Assert.Throws<FormatException>(() => EmailAddress.Parse("not an email"));
    }

    [Fact]
    public void Generic_math_Sum_works_for_int_decimal_and_Euros()
    {
        Assert.Equal(6, Totals.Sum<int>([1, 2, 3]));
        Assert.Equal(1.5m, Totals.Sum<decimal>([1m, 0.5m]));
        Assert.Equal(new Euros(93_000m), Totals.Sum<Euros>([new(18_000m), new(75_000m)]));
        Assert.Equal(Euros.Zero, Totals.Sum<Euros>([]));
    }

    [Fact]
    public void Euros_formats_with_invariant_culture() => Assert.Equal("75,000 EUR", new Euros(75_000m).ToString());
}
