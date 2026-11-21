using Microsoft.Extensions.Http.Resilience;
using Polly;

namespace Contoso.ServiceDefaults;

public static class RetryPolicy
{
    /// <summary>
    /// The standard resilience handler retries every HTTP method (Learn: "retries for all HTTP methods" is the default).
    /// A retried POST can run twice. So: retry reads freely, retry writes only when the caller sent an Idempotency-Key.
    /// </summary>
    public static void ApplyIdempotencyRule(HttpRetryStrategyOptions retry)
    {
        var transient = retry.ShouldHandle;   // the default: 5xx, 408, 429, HttpRequestException, timeouts
        retry.ShouldHandle = async args =>
        {
            if (!await transient(args)) return false;
            var request = args.Context.GetRequestMessage();
            return request is null || IsSafeToRepeat(request);
        };
    }

    public static bool IsSafeToRepeat(HttpRequestMessage request) =>
        request.Method == HttpMethod.Get || request.Method == HttpMethod.Head || request.Method == HttpMethod.Options ||
        request.Headers.Contains(Idempotency.Header);
}
