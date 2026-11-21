namespace Gotchas;

// Compiles without a single warning: primary constructor parameters are parameters, and parameters can be assigned.
public sealed class ReportService(TimeProvider time)
{
    public DateTimeOffset Stamp() => time.GetUtcNow();

    public void ResetForTests() => time = TimeProvider.System; // silently replaces the injected clock
}
