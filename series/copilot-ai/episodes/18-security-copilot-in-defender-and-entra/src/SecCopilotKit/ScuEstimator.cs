namespace Contoso.SecCopilotKit;

public sealed record ProvisionedEstimate(int Scus, double Hours, double ProvisionedUsd, double OverageScus, double OverageUsd)
{
    public double TotalUsd => ProvisionedUsd + OverageUsd;
}

public sealed record InclusionEstimate(double IncludedScus, double UsedScus, double CoveredScus, double BeyondScus, double BeyondUsdAtOverageRate);

/// <summary>
/// Security Copilot capacity arithmetic (Microsoft Learn, Security compute units and capacity; Security Copilot for
/// Microsoft 365 E5 and E7 included customers; and the Microsoft Security Copilot pricing page).
/// Prices are US dollars and can change: check the pricing page before you quote a number.
/// </summary>
public static class ScuEstimator
{
    public const double ProvisionedUsdPerScuHour = 4.00;   // pricing page, provisioned SCU per hour
    public const double OverageUsdPerScu = 6.00;           // Learn: pay-as-you-go beyond the allocation, and the pricing page
    public const int MinProvisionedScus = 1;               // Learn: a tenant provisions at least one SCU
    public const int MaxProvisionedScus = 100;             // Learn: up to a maximum of 100 SCUs
    public const int MaxOverageScus = 999;                 // Learn: overage can be set from 0 to 999
    public const double InclusionScusPer1000Licences = 400; // Learn: per month, per 1,000 paid user licences
    public const double InclusionCapScus = 10_000;          // Learn: up to 10,000 SCUs a month
    public const double HoursPerMonth = 730;                // average month: 8,760 / 12

    /// <summary>Provisioned capacity is billed per started hour, minimum one hour, whatever was used (Learn).</summary>
    public static ProvisionedEstimate Provisioned(int scus, double hours, double overageScusUsed = 0)
    {
        if (scus < MinProvisionedScus || scus > MaxProvisionedScus)
            throw new ArgumentOutOfRangeException(nameof(scus), $"Provision {MinProvisionedScus} to {MaxProvisionedScus} SCUs.");
        if (hours <= 0) throw new ArgumentOutOfRangeException(nameof(hours), "Hours must be positive.");
        if (overageScusUsed < 0) throw new ArgumentOutOfRangeException(nameof(overageScusUsed));
        var billedHours = Math.Ceiling(hours);
        // Overage is billed on exact use, to one decimal place (Learn).
        var overage = Math.Round(overageScusUsed, 1, MidpointRounding.AwayFromZero);
        return new ProvisionedEstimate(scus, billedHours, scus * billedHours * ProvisionedUsdPerScuHour, overage, overage * OverageUsdPerScu);
    }

    /// <summary>Monthly SCUs included with Microsoft 365 E5 and E7: 400 per 1,000 licences, capped at 10,000, scaled below 1,000.</summary>
    public static double IncludedScus(int paidLicences)
    {
        if (paidLicences < 0) throw new ArgumentOutOfRangeException(nameof(paidLicences));
        return Math.Min(paidLicences / 1000.0 * InclusionScusPer1000Licences, InclusionCapScus);
    }

    /// <summary>
    /// Compares a month of use against the inclusion. Learn says usage beyond it will be throttled "at a future date" and
    /// that scaling beyond will cost 6 USD per SCU at that time, so the dollar figure is what it would cost, not a charge today.
    /// </summary>
    public static InclusionEstimate Inclusion(int paidLicences, double monthlyScusUsed)
    {
        if (monthlyScusUsed < 0) throw new ArgumentOutOfRangeException(nameof(monthlyScusUsed));
        var included = IncludedScus(paidLicences);
        var covered = Math.Min(included, monthlyScusUsed);
        var beyond = Math.Max(0, monthlyScusUsed - included);
        return new InclusionEstimate(included, monthlyScusUsed, covered, beyond, beyond * OverageUsdPerScu);
    }

    /// <summary>SCUs a month from runs of an agent: Learn says the Conditional Access Optimization Agent uses less than one SCU per run on average.</summary>
    public static double MonthlyUse(double scusPerRun, double runsPerDay, double daysPerMonth = 30) => scusPerRun * runsPerDay * daysPerMonth;
}
