using Microsoft.Extensions.Time.Testing;

namespace Contoso.Approvals.Tests;

/// <summary>The traps from the video, pinned down so they can't quietly change.</summary>
public class GotchaTests
{
    [Fact]
    public async Task Gotcha_await_WhenAll_throws_only_one_exception_but_the_task_keeps_all()
    {
        var budget = Task.FromException<int>(new InvalidOperationException("budget service down"));
        var approver = Task.FromException<int>(new TimeoutException("directory timed out"));
        var all = Task.WhenAll(budget, approver);

        var thrown = await Record.ExceptionAsync(() => all);

        Assert.IsType<InvalidOperationException>(thrown);           // await rethrows only one
        Assert.Equal(2, all.Exception!.InnerExceptions.Count);       // the full list is on the task
    }

    [Fact]
    public async Task Gotcha_WaitAsync_stops_waiting_but_not_the_work()
    {
        var time = new FakeTimeProvider();
        var work = new TaskCompletionSource<string>();               // stands in for the HTTP call

        var waiting = work.Task.WaitAsync(TimeSpan.FromMilliseconds(200), time);
        time.Advance(TimeSpan.FromMilliseconds(200));

        await Assert.ThrowsAsync<TimeoutException>(() => waiting);
        Assert.False(work.Task.IsCompleted);                        // still running, nobody cancelled it
    }

    [Fact]
    public void Gotcha_blocking_on_async_code_deadlocks_on_a_single_threaded_context() =>
        Assert.False(SyncOverAsync.BlockOnUiThread(TimeSpan.FromMilliseconds(20), giveUpAfter: TimeSpan.FromMilliseconds(500)));

    [Fact]
    public void ConfigureAwait_false_avoids_that_deadlock_for_callers_who_block() =>
        Assert.True(SyncOverAsync.BlockOnUiThreadLibraryStyle(TimeSpan.FromMilliseconds(20), TimeSpan.FromSeconds(5)));

    [Fact]
    public void Awaiting_all_the_way_works_on_the_same_context() =>
        Assert.True(SyncOverAsync.AwaitOnUiThread(TimeSpan.FromMilliseconds(20)));

    [Fact]
    public async Task Gotcha_an_async_method_runs_synchronously_until_its_first_real_await()
    {
        var log = new List<string>();
        var io = new TaskCompletionSource();             // an operation that is not finished yet
        async Task WorkAsync()
        {
            log.Add("before await");                     // runs on the caller's thread, inside the call
            await io.Task;
            log.Add("after await");
        }

        var task = WorkAsync();                          // returns at the first incomplete await
        log.Add("caller continues");
        io.SetResult();
        await task;

        Assert.Equal(["before await", "caller continues", "after await"], log);
    }
}
