using System.Collections.Concurrent;

namespace Contoso.Approvals;

/// <summary>
/// A tiny single-threaded SynchronizationContext, like a UI thread (WinForms, WPF) or classic ASP.NET request:
/// continuations are queued and run only when this thread pumps the queue.
/// Used to reproduce the sync-over-async deadlock on purpose. Console apps and ASP.NET Core have no such context.
/// </summary>
public sealed class SingleThreadContext : SynchronizationContext, IDisposable
{
    private readonly BlockingCollection<(SendOrPostCallback Callback, object? State)> _queue = [];
    private readonly Lock _gate = new();
    private bool _closed;

    /// <summary>
    /// Queues a continuation. After the thread is gone, late posts are dropped: an exception thrown here runs on a
    /// thread-pool thread and would crash the whole process (it crashed our test host once, before this check).
    /// </summary>
    public override void Post(SendOrPostCallback d, object? state)
    {
        lock (_gate)
        {
            if (!_closed) _queue.Add((d, state));
        }
    }

    public override void Send(SendOrPostCallback d, object? state) =>
        throw new NotSupportedException("Synchronous Send is not supported in this demo context.");

    /// <summary>Runs <paramref name="body"/> on a new thread that owns this context and returns what it returns.</summary>
    public static T RunOnNewThread<T>(Func<SingleThreadContext, T> body)
    {
        T result = default!;
        Exception? error = null;
        var thread = new Thread(() =>
        {
            using var context = new SingleThreadContext();
            SetSynchronizationContext(context);
            try { result = body(context); }
            catch (Exception ex) { error = ex; }
        }) { IsBackground = true, Name = "ui-like thread" };
        thread.Start();
        thread.Join();
        if (error is not null) throw new InvalidOperationException("The body failed.", error);
        return result;
    }

    /// <summary>The right way on a UI-like thread: keep pumping queued continuations until the task is done.</summary>
    public void PumpUntil(Task task)
    {
        _ = task.ContinueWith(_ => Close(), TaskScheduler.Default);
        foreach (var (callback, state) in _queue.GetConsumingEnumerable())
            callback(state);
    }

    private void Close()
    {
        lock (_gate)
        {
            if (_closed) return;
            _closed = true;
            _queue.CompleteAdding();
        }
    }

    public void Dispose()
    {
        Close();
        _queue.Dispose();
    }
}
