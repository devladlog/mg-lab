using SpanMath;

// Kept identical to demo/Gotchas/LinqClash.cs so the test proves the same binding the demo shows.
namespace SpanMath
{
    public static class SpanAverage
    {
        public static double Average(this ReadOnlySpan<int> values) => -1;
    }
}
