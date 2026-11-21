using System.Net;

namespace Contoso.Approvals;

/// <summary>Timeout and retry, written against TimeProvider so tests can move time instead of waiting for it.</summary>
public static class Resilience
{
    /// <summary>
    /// Runs <paramref name="operation"/> with a timeout that CANCELS it (the token reaches HttpClient), unlike
    /// Task.WaitAsync, which only stops waiting. Caller cancellation stays an OperationCanceledException.
    /// </summary>
    public static async Task<T> WithTimeoutAsync<T>(
        Func<CancellationToken, Task<T>> operation, TimeSpan timeout, TimeProvider time, CancellationToken ct)
    {
        using var timeoutCts = new CancellationTokenSource(timeout, time);
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(ct, timeoutCts.Token);
        try
        {
            return await operation(linked.Token).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (timeoutCts.IsCancellationRequested && !ct.IsCancellationRequested)
        {
            throw new TimeoutException($"Gave up after {timeout.TotalMilliseconds:N0} ms.");
        }
    }

    /// <summary>Retries transient failures with exponential backoff: baseDelay, 2x, 4x... The delay honours cancellation.</summary>
    public static async Task<T> RetryAsync<T>(
        Func<CancellationToken, Task<T>> operation, int maxAttempts, TimeSpan baseDelay, TimeProvider time,
        CancellationToken ct, Action<int, TimeSpan, Exception>? onRetry = null)
    {
        ArgumentOutOfRangeException.ThrowIfLessThan(maxAttempts, 1);
        for (var attempt = 1; ; attempt++)
        {
            try
            {
                return await operation(ct).ConfigureAwait(false);
            }
            catch (Exception ex) when (attempt < maxAttempts && IsTransient(ex) && !ct.IsCancellationRequested)
            {
                var delay = baseDelay * Math.Pow(2, attempt - 1);
                onRetry?.Invoke(attempt, delay, ex);
                await Task.Delay(delay, time, ct).ConfigureAwait(false);
            }
        }
    }

    public static bool IsTransient(Exception ex) => ex switch
    {
        TimeoutException => true,
        HttpRequestException { StatusCode: HttpStatusCode.ServiceUnavailable or HttpStatusCode.TooManyRequests
            or HttpStatusCode.BadGateway or HttpStatusCode.GatewayTimeout } => true,
        _ => false,
    };
}
