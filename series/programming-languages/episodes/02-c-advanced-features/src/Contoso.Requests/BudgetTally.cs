namespace Contoso.Requests;

/// <summary>
/// A mutable accumulator. C# 14 user-defined compound assignment: `tally += request` updates this
/// instance in place instead of allocating a new tally for every addition.
/// </summary>
public sealed class BudgetTally
{
    public int Count { get; private set; }
    public Euros Total { get; private set; } = Euros.Zero;
    public Euros Largest { get; private set; } = Euros.Zero;

    public void operator +=(ProjectRequest request)
    {
        Count++;
        Total += request.Budget;
        if (request.Budget > Largest) Largest = request.Budget;
    }
}
