using Contoso.Requests;

namespace Contoso.Requests.Tests;

internal static class TestData
{
    public static readonly EmailAddress Alex = EmailAddress.Parse("alex.demo@contoso.com");
    public static readonly EmailAddress Sam = EmailAddress.Parse("sam.demo@contoso.com");
    public static readonly EmailAddress Kim = EmailAddress.Parse("kim.demo@contoso.com");
    public static readonly DateTimeOffset Now = new(2026, 11, 21, 10, 0, 0, TimeSpan.Zero);

    public static ProjectRequest Request(decimal budget, string? justification = null, int number = 1) => new()
    {
        Code = new RequestCode(2026, number),
        Title = "CRM rollout",
        Budget = new Euros(budget),
        RequestedBy = Alex,
        Justification = justification,
    };
}

internal sealed class FixedClock(DateTimeOffset now) : TimeProvider
{
    public override DateTimeOffset GetUtcNow() => now;
}
