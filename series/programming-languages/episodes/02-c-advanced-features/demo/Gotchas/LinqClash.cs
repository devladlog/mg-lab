using SpanMath;

namespace SpanMath
{
    public static class SpanAverage
    {
        // Same name as LINQ's Enumerable.Average, but over a span. Returns -1 so we can see which one ran.
        public static double Average(this ReadOnlySpan<int> values) => -1;
    }
}

namespace Gotchas
{
    public static class LinqClash
    {
        // Compiles in C# 13 and C# 14 without a warning - but binds to a different method.
        // C# 13: Enumerable.Average (2).  C# 14: SpanAverage.Average (-1). See demo/CSharp13 and the unit test.
        public static double Which(int[] values) => values.Average();
    }
}
