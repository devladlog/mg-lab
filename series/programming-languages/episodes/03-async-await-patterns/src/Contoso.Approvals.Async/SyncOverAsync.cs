namespace Contoso.Approvals;

/// <summary>The classic deadlock, reproduced deterministically. Each method returns true if the work completed.</summary>
public static class SyncOverAsync
{
    // Awaits WITHOUT ConfigureAwait(false): the continuation wants to come back to the captured context.
    public static async Task<string> GetStatusAsync(TimeSpan latency)
    {
        await Task.Delay(latency);
        return "ok";
    }

    // Library style: ConfigureAwait(false), the continuation runs on the thread pool.
    public static async Task<string> GetStatusLibraryStyleAsync(TimeSpan latency)
    {
        await Task.Delay(latency).ConfigureAwait(false);
        return "ok";
    }

    /// <summary>Blocks the UI-like thread on an async call. The continuation is queued to that same thread: deadlock.</summary>
    public static bool BlockOnUiThread(TimeSpan latency, TimeSpan giveUpAfter) =>
        SingleThreadContext.RunOnNewThread(_ => GetStatusAsync(latency).Wait(giveUpAfter));

    /// <summary>Same blocking call, but the async method used ConfigureAwait(false): no deadlock (still blocks a thread).</summary>
    public static bool BlockOnUiThreadLibraryStyle(TimeSpan latency, TimeSpan giveUpAfter) =>
        SingleThreadContext.RunOnNewThread(_ => GetStatusLibraryStyleAsync(latency).Wait(giveUpAfter));

    /// <summary>Async all the way: the thread keeps pumping, the continuation runs on it, nothing blocks.</summary>
    public static bool AwaitOnUiThread(TimeSpan latency) =>
        SingleThreadContext.RunOnNewThread(context =>
        {
            var task = GetStatusAsync(latency);
            context.PumpUntil(task);
            return task.IsCompletedSuccessfully;
        });
}
