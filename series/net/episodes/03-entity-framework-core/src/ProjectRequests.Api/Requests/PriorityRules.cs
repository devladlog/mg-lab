using ProjectRequests.Api.Data;

namespace ProjectRequests.Api.Requests;

/// <summary>Pure business rules: no HTTP, no storage, easy to unit test. Same thresholds as episode 1.</summary>
public static class PriorityRules
{
    public const decimal HighThreshold = 50_000m;
    public const decimal JustificationThreshold = 250_000m;

    public static Priority Classify(decimal budget) =>
        budget >= HighThreshold ? Priority.High : Priority.Standard;

    public static bool NeedsJustification(decimal budget) => budget >= JustificationThreshold;
}
