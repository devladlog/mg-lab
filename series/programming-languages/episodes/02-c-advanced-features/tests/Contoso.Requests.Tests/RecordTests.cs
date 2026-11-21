using Contoso.Requests;

namespace Contoso.Requests.Tests;

public class RecordTests
{
    [Fact]
    public void Field_keyword_setter_trims_the_title() =>
        Assert.Equal("Laptop refresh", (TestData.Request(1_000m) with { Title = "  Laptop refresh " }).Title);

    [Theory]
    [InlineData("")]
    [InlineData("  ")]
    [InlineData("ab")]
    public void Field_keyword_setter_rejects_short_titles(string title) =>
        Assert.Throws<ArgumentException>(() => TestData.Request(1_000m) with { Title = title });

    [Fact]
    public void With_creates_a_new_record_and_leaves_the_original_alone()
    {
        var draft = TestData.Request(75_000m);
        var submitted = draft with { State = new RequestState.Submitted(TestData.Now) };

        Assert.IsType<RequestState.Draft>(draft.State);
        Assert.IsType<RequestState.Submitted>(submitted.State);
        Assert.NotEqual(draft, submitted);
    }

    [Fact]
    public void Records_with_equal_scalars_are_equal() =>
        Assert.Equal(TestData.Request(75_000m), TestData.Request(75_000m));

    [Fact]
    public void Gotcha_record_equality_compares_collections_by_reference()
    {
        var approval = new Approval("sam.demo@contoso.com", "Finance", TestData.Now);
        var a = TestData.Request(75_000m) with { Approvals = [approval] };
        var b = TestData.Request(75_000m) with { Approvals = [approval] };

        Assert.Equal(a.Approvals, b.Approvals); // same contents...
        Assert.NotEqual(a, b);                  // ...but two different list instances, so the records differ
    }

    [Fact]
    public void Gotcha_with_is_a_shallow_copy()
    {
        var shared = new List<Approval>();
        var a = TestData.Request(75_000m) with { Approvals = shared };
        var b = a with { Title = "Another title" };

        shared.Add(new Approval("sam.demo@contoso.com", "Finance", TestData.Now));

        Assert.Same(a.Approvals, b.Approvals);
        Assert.Single(b.Approvals); // b "changed" although nobody touched b
    }
}
