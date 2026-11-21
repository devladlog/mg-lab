namespace Gotchas;

public class Legacy
{
#pragma warning disable IDE1006, CA1051 // old code really did name a field `field`
    public string field = "from the field member";
#pragma warning restore IDE1006, CA1051

    // Before C# 14 this returned the member above. In C# 14 `field` is the keyword: the synthesized backing field.
    public string Name
    {
        get => field;
        set => field = value;
    }
}
