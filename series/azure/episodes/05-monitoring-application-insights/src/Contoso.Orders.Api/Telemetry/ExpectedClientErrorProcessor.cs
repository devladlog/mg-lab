using System.Diagnostics;
using OpenTelemetry;

namespace Contoso.Orders.Api.Telemetry;

/// <summary>
/// The Azure Monitor exporter counts every HTTP 4xx request as failed when the span status is
/// Unset. A 400 for a bad order or a 404 for an unknown id is the API working as designed, so we
/// mark those as successful. The result code stays 400/404 in the requests table; only the
/// success field changes. 401, 403, 409, 429 and anything else still count as failures.
/// Pattern from Microsoft Learn: "Override request error status for HTTP 4xx responses".
/// </summary>
public sealed class ExpectedClientErrorProcessor : BaseProcessor<Activity>
{
    public static readonly IReadOnlySet<int> ExpectedStatusCodes = new HashSet<int> { 400, 404, 422 };

    public override void OnEnd(Activity activity)
    {
        if (activity.Kind == ActivityKind.Server
            && activity.Status == ActivityStatusCode.Unset
            && activity.GetTagItem("http.response.status_code") is int status
            && ExpectedStatusCodes.Contains(status))
        {
            activity.SetStatus(ActivityStatusCode.Ok);
        }

        base.OnEnd(activity);
    }
}
