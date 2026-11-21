namespace ProjectRequests.Api.Tests;

/// <summary>
/// xUnit v3 gives every test a cancellation token (cancelled on timeout or when the run is aborted).
/// Analyzer xUnit1051 flags every async call that could take it and doesn't: 50 call sites in the
/// 39 tests we migrated from v2. Imported with "using static" in the project file.
/// </summary>
internal static class TestCancellation
{
    public static CancellationToken Ct => TestContext.Current.CancellationToken;
}
