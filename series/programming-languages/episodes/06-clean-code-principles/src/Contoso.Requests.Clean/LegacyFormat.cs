using System.Diagnostics;
using System.Globalization;

namespace Contoso.Requests.Clean;

/// <summary>
/// Writes an outcome in the old "OK;..." / "ERRn" format, so downstream systems don't notice the rewrite.
/// Two methods instead of a bool flag: the call site says what it means.
/// </summary>
public static class LegacyFormat
{
    private const string MailMarker = ";MAIL";

    public static string Describe(Outcome outcome) => outcome switch
    {
        Routed routed => string.Join(';',
            "OK",
            routed.Code,
            PriorityCode(routed.Priority),
            string.Join(',', routed.Approvers),
            routed.TotalWithContingency.ToString(CultureInfo.InvariantCulture)),
        Rejected rejected => $"ERR{(int)rejected.Reason}",
        _ => throw new UnreachableException($"Unknown outcome {outcome.GetType().Name}"),
    };

    public static string DescribeAfterNotifying(Outcome outcome) =>
        outcome is Routed ? Describe(outcome) + MailMarker : Describe(outcome);

    private static string PriorityCode(Priority priority) => priority switch
    {
        Priority.Normal => "N",
        Priority.High => "H",
        Priority.Board => "B",
        _ => throw new UnreachableException($"Unknown priority {priority}"),
    };
}
