namespace Contoso.Portfolio;

/// <summary>Deferred execution, observed. Each method returns what actually happened.</summary>
public static class Deferred
{
    /// <summary>A source that counts how often somebody starts enumerating it (think: a query or a file read).</summary>
    public sealed class CountingSource<T>(IEnumerable<T> items) : IEnumerable<T>
    {
        public int Enumerations { get; private set; }

        public IEnumerator<T> GetEnumerator()
        {
            Enumerations++;
            return items.GetEnumerator();
        }

        System.Collections.IEnumerator System.Collections.IEnumerable.GetEnumerator() => GetEnumerator();
    }

    /// <summary>A query used three times runs three times. Returns how many times the source was read.</summary>
    public static int EnumerationsWithoutMaterializing(IEnumerable<ProjectRequest> requests)
    {
        var source = new CountingSource<ProjectRequest>(requests);
#pragma warning disable CA1851 // on purpose: this is the bug the video shows
        var high = source.Where(r => Policy.PriorityFor(r.Budget) == Priority.High);

        var count = high.Count();
        var total = high.Sum(r => r.Budget);
        var first = high.First();
#pragma warning restore CA1851
        _ = (count, total, first);
        return source.Enumerations;
    }

    /// <summary>Same three questions after ToList(): the source is read once.</summary>
    public static int EnumerationsWithToList(IEnumerable<ProjectRequest> requests)
    {
        var source = new CountingSource<ProjectRequest>(requests);
        var high = source.Where(r => Policy.PriorityFor(r.Budget) == Priority.High).ToList();

        var count = high.Count;
        var total = high.Sum(r => r.Budget);
        var first = high[0];
        _ = (count, total, first);
        return source.Enumerations;
    }

    /// <summary>The lambda captures the variable, not its value. The query runs with the value at enumeration time.</summary>
    public static (int Before, int After) CapturedVariable(IEnumerable<ProjectRequest> requests)
    {
#pragma warning disable CA1851 // on purpose: the query runs twice
        var threshold = 50_000m;
        var big = requests.Where(r => r.Budget >= threshold);   // nothing runs here

        var before = big.Count();                                // runs now, threshold = 50,000
        threshold = 250_000m;
        var after = big.Count();                                 // runs again, threshold = 250,000
        return (before, after);
#pragma warning restore CA1851
    }
}
