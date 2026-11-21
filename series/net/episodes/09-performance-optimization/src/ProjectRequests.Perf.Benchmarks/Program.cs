using BenchmarkDotNet.Running;

namespace ProjectRequests.Perf.Benchmarks;

// Explicit Main (not top-level statements): the API assembly already exports a public 'Program' type.
internal static class Entry
{
    private static void Main(string[] args) =>
        BenchmarkSwitcher.FromAssembly(typeof(Entry).Assembly).Run(args);
}
