using System.Net;
using Microsoft.Extensions.Time.Testing;

namespace Contoso.Approvals.Tests;

public class ResilienceTests
{
    /// <summary>
    /// The retry loop resumes on the thread pool, so a test must not advance the clock before the next
    /// Task.Delay timer exists (a timer created "late" would never fire). Counting CreateTimer calls fixes that race.
    /// </summary>
    private sealed class TimerCountingTimeProvider : FakeTimeProvider
    {
        private int _timers;
        public int TimersCreated => Volatile.Read(ref _timers);

        public override ITimer CreateTimer(TimerCallback callback, object? state, TimeSpan dueTime, TimeSpan period)
        {
            Interlocked.Increment(ref _timers);
            return base.CreateTimer(callback, state, dueTime, period);
        }
    }

    [Fact]
    public async Task Retry_backs_off_200_then_400_ms_and_the_test_takes_no_real_time()
    {
        var time = new TimerCountingTimeProvider();
        var attempts = 0;
        var task = Resilience.RetryAsync<string>(_ =>
        {
            attempts++;
            return attempts < 3 ? throw Data.Http(HttpStatusCode.ServiceUnavailable) : Task.FromResult("ok");
        }, maxAttempts: 3, baseDelay: TimeSpan.FromMilliseconds(200), time, CancellationToken.None);

        Assert.Equal(1, attempts);
        time.Advance(TimeSpan.FromMilliseconds(199));
        Assert.Equal(1, attempts);                       // not yet: backoff is 200 ms
        time.Advance(TimeSpan.FromMilliseconds(1));
        await Wait.UntilAsync(() => attempts == 2 && time.TimersCreated == 2);   // second backoff is scheduled
        time.Advance(TimeSpan.FromMilliseconds(399));
        Assert.Equal(2, attempts);                       // second backoff is 400 ms
        time.Advance(TimeSpan.FromMilliseconds(1));
        Assert.Equal("ok", await task);
        Assert.Equal(3, attempts);
    }

    [Fact]
    public async Task Retry_gives_up_after_max_attempts_with_the_last_error()
    {
        var time = new FakeTimeProvider();
        var attempts = 0;
        var task = Resilience.RetryAsync<string>(_ =>
        {
            attempts++;
            throw Data.Http(HttpStatusCode.ServiceUnavailable);
        }, 2, TimeSpan.FromMilliseconds(100), time, CancellationToken.None);

        time.Advance(TimeSpan.FromMilliseconds(100));
        var error = await Assert.ThrowsAsync<HttpRequestException>(() => task);
        Assert.Equal(HttpStatusCode.ServiceUnavailable, error.StatusCode);
        Assert.Equal(2, attempts);
    }

    [Theory]
    [InlineData(HttpStatusCode.NotFound)]
    [InlineData(HttpStatusCode.BadRequest)]
    public async Task Retry_does_not_retry_errors_that_will_not_go_away(HttpStatusCode code)
    {
        var attempts = 0;
        await Assert.ThrowsAsync<HttpRequestException>(() => Resilience.RetryAsync<string>(_ =>
        {
            attempts++;
            throw Data.Http(code);
        }, 3, TimeSpan.FromMilliseconds(100), new FakeTimeProvider(), CancellationToken.None));
        Assert.Equal(1, attempts);
    }

    [Fact]
    public async Task Cancelling_during_the_backoff_stops_retrying()
    {
        var time = new FakeTimeProvider();
        using var cts = new CancellationTokenSource();
        var attempts = 0;
        var task = Resilience.RetryAsync<string>(_ =>
        {
            attempts++;
            throw Data.Http(HttpStatusCode.ServiceUnavailable);
        }, 5, TimeSpan.FromSeconds(1), time, cts.Token);

        await cts.CancelAsync();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => task);
        Assert.Equal(1, attempts);
    }

    [Fact]
    public async Task Timeout_throws_TimeoutException_and_cancels_the_token_the_operation_got()
    {
        var time = new FakeTimeProvider();
        CancellationToken seen = default;
        var task = Resilience.WithTimeoutAsync(async ct =>
        {
            seen = ct;
            await Task.Delay(Timeout.InfiniteTimeSpan, ct);
            return 0;
        }, TimeSpan.FromMilliseconds(500), time, CancellationToken.None);

        time.Advance(TimeSpan.FromMilliseconds(500));
        var error = await Assert.ThrowsAsync<TimeoutException>(() => task);
        Assert.Contains("500 ms", error.Message, StringComparison.Ordinal);
        Assert.True(seen.IsCancellationRequested);   // the HTTP call would have been aborted
    }

    [Fact]
    public async Task Caller_cancellation_is_not_reported_as_a_timeout()
    {
        using var cts = new CancellationTokenSource();
        var task = Resilience.WithTimeoutAsync(async ct =>
        {
            await Task.Delay(Timeout.InfiniteTimeSpan, ct);
            return 0;
        }, TimeSpan.FromSeconds(5), new FakeTimeProvider(), cts.Token);

        await cts.CancelAsync();
        var error = await Assert.ThrowsAnyAsync<OperationCanceledException>(() => task);
        Assert.IsNotType<TimeoutException>(error);
    }

    [Fact]
    public void Transient_means_503_429_502_504_and_timeouts()
    {
        Assert.True(Resilience.IsTransient(Data.Http(HttpStatusCode.ServiceUnavailable)));
        Assert.True(Resilience.IsTransient(Data.Http(HttpStatusCode.TooManyRequests)));
        Assert.True(Resilience.IsTransient(new TimeoutException()));
        Assert.False(Resilience.IsTransient(Data.Http(HttpStatusCode.Unauthorized)));
        Assert.False(Resilience.IsTransient(new InvalidOperationException()));
    }
}
