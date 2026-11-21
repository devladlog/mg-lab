namespace Contoso.SupportTriage;

/// <summary>
/// Counts the text records a run will bill, per feature. The free tier is 5,000 records a month and each feature
/// call counts, so one ticket sent to three features costs three records (or more when it is long).
/// </summary>
public sealed class UsageMeter
{
    private readonly Dictionary<string, int> byFeature = new();

    public void Add(string feature, string text) =>
        byFeature[feature] = byFeature.GetValueOrDefault(feature) + Limits.TextRecords(text);

    public IReadOnlyDictionary<string, int> ByFeature => byFeature;

    public int Total => byFeature.Values.Sum();

    public double FractionOfFreeTier => (double)Total / Limits.FreeTierTextRecordsPerMonth;

    public int RunsPerMonthBeforeFreeTierEnds => Total == 0 ? int.MaxValue : Limits.FreeTierTextRecordsPerMonth / Total;
}
