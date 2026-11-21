namespace ProjectRequests.Web.Tests;

/// <summary>
/// xUnit v3's per-test cancellation token (see episode 5). Spelled out as Xunit.TestContext because bUnit also
/// has a (legacy) Bunit.TestContext: with both namespaces imported, plain "TestContext" doesn't compile (CS0104).
/// </summary>
internal static class TestCancellation
{
    public static CancellationToken Ct => Xunit.TestContext.Current.CancellationToken;
}
