namespace Contoso.Portfolio.Tests;

public class DeferredTests
{
    [Fact]
    public void Gotcha_a_query_used_three_times_runs_three_times() =>
        Assert.Equal(3, Deferred.EnumerationsWithoutMaterializing(SampleData.Requests));

    [Fact]
    public void ToList_runs_it_once() =>
        Assert.Equal(1, Deferred.EnumerationsWithToList(SampleData.Requests));

    [Fact]
    public void Gotcha_the_lambda_sees_the_variable_at_enumeration_time() =>
        Assert.Equal((5, 1), Deferred.CapturedVariable(SampleData.Requests));

    [Fact]
    public void Nothing_runs_until_you_enumerate()
    {
        var source = new Deferred.CountingSource<ProjectRequest>(SampleData.Requests);
        var query = source.Where(r => r.Budget > 0).Select(r => r.Code).OrderBy(c => c, StringComparer.Ordinal);

        Assert.Equal(0, source.Enumerations);
        _ = query.First();
        Assert.Equal(1, source.Enumerations);
    }

    [Fact]
    public void A_deferred_query_sees_items_added_after_it_was_defined()
    {
        List<ProjectRequest> list = [.. SampleData.Requests];
        var big = list.Where(r => r.Budget >= 250_000m);
        list.Add(SampleData.Requests[0] with { Id = 99, Budget = 900_000m });

        Assert.Equal(2, big.Count());
    }
}
