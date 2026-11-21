using Xunit;

namespace Contoso.SecCopilotKit.Tests;

public class ScuEstimatorTests
{
    [Fact] public void ProvisionedIsBilledPerStartedHour() =>
        Assert.Equal(4.00, ScuEstimator.Provisioned(1, 1).ProvisionedUsd);

    [Fact] public void PartHoursRoundUp() => Assert.Equal(2, ScuEstimator.Provisioned(1, 1.1).Hours);

    [Fact] public void LearnExampleFiveScusTwoHoursBillsTenScuHours()
    {
        // Learn: 5 provisioned SCUs for two hours, 3.5 SCUs used: "10 SCUs billed for two hours".
        var e = ScuEstimator.Provisioned(5, 2);
        Assert.Equal(5 * 2 * 4.00, e.ProvisionedUsd);
    }

    [Fact] public void FullMonthOfOneScu() => Assert.Equal(2920.00, ScuEstimator.Provisioned(1, ScuEstimator.HoursPerMonth).ProvisionedUsd);

    [Fact] public void OverageIsBilledOnExactUseToOneDecimal()
    {
        var e = ScuEstimator.Provisioned(1, 1, 2.26);
        Assert.Equal(2.3, e.OverageScus);
        Assert.Equal(2.3 * 6.00, e.OverageUsd, 6);
    }

    [Fact] public void TotalAddsProvisionedAndOverage() => Assert.Equal(3 * 24 * 4.0 + 1.5 * 6.0, ScuEstimator.Provisioned(3, 24, 1.5).TotalUsd, 6);

    [Theory] [InlineData(0)] [InlineData(101)] [InlineData(-1)]
    public void ProvisionedScusMustBeOneToHundred(int scus) =>
        Assert.Throws<ArgumentOutOfRangeException>(() => ScuEstimator.Provisioned(scus, 1));

    [Fact] public void HoursMustBePositive() => Assert.Throws<ArgumentOutOfRangeException>(() => ScuEstimator.Provisioned(1, 0));
    [Fact] public void NegativeOverageIsRejected() => Assert.Throws<ArgumentOutOfRangeException>(() => ScuEstimator.Provisioned(1, 1, -1));

    [Theory]
    [InlineData(400, 160)]      // Learn example 1
    [InlineData(4000, 1600)]    // Learn example 2
    [InlineData(1000, 400)]
    [InlineData(25000, 10000)]  // 25,000 licences would be 10,000: exactly the cap
    [InlineData(100000, 10000)] // capped
    [InlineData(0, 0)]
    public void InclusionFollowsLearn(int licences, double expected) => Assert.Equal(expected, ScuEstimator.IncludedScus(licences), 6);

    [Fact] public void InclusionCoversUseBelowTheAllocation()
    {
        var e = ScuEstimator.Inclusion(4000, 3.5);
        Assert.Equal(3.5, e.CoveredScus);
        Assert.Equal(0, e.BeyondScus);
        Assert.Equal(0, e.BeyondUsdAtOverageRate);
    }

    [Fact] public void UseBeyondTheAllocationIsPricedAtTheOverageRate()
    {
        var e = ScuEstimator.Inclusion(400, 200);   // 160 included
        Assert.Equal(40, e.BeyondScus, 6);
        Assert.Equal(240, e.BeyondUsdAtOverageRate, 6);
    }

    [Fact] public void NegativeInputsAreRejected()
    {
        Assert.Throws<ArgumentOutOfRangeException>(() => ScuEstimator.IncludedScus(-1));
        Assert.Throws<ArgumentOutOfRangeException>(() => ScuEstimator.Inclusion(10, -1));
    }

    [Fact] public void AgentRunsAddUpToAMonth() =>
        Assert.Equal(0.9 * 24 * 30, ScuEstimator.MonthlyUse(0.9, 24), 6);   // under one SCU per run (Learn: average), hourly agent

    [Fact] public void ConstantsMatchLearnAndThePricingPage()
    {
        Assert.Equal(4.00, ScuEstimator.ProvisionedUsdPerScuHour);
        Assert.Equal(6.00, ScuEstimator.OverageUsdPerScu);
        Assert.Equal(400, ScuEstimator.InclusionScusPer1000Licences);
        Assert.Equal(10_000, ScuEstimator.InclusionCapScus);
        Assert.Equal(100, ScuEstimator.MaxProvisionedScus);
    }
}
