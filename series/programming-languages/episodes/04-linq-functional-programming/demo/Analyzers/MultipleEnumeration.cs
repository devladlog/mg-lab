namespace Demo;

public static class MultipleEnumeration
{
    // CA1851: Count() runs the query once, the foreach runs it again.
    // If 'budgets' is a database query or reads a file, that is two round trips.
    public static string Summarize(IEnumerable<decimal> budgets)
    {
        var count = budgets.Count();
        var total = 0m;
        foreach (var budget in budgets) total += budget;
        return $"{count} requests, {total:N0} EUR";
    }
}
