using Microsoft.Maui.Dispatching;

namespace Contoso.Mobile.Tests;

/// <summary>
/// MAUI controls insist on a dispatcher when a binding updates them from another thread. A device has the UI thread; the tests
/// have none, so this one says "no dispatch needed" and runs the action right away.
/// </summary>
public sealed class TestDispatcherProvider : IDispatcherProvider
{
    private static readonly TestDispatcher Instance = new();
    public IDispatcher? GetForCurrentThread() => Instance;

    private sealed class TestDispatcher : IDispatcher
    {
        public bool IsDispatchRequired => false;
        public bool Dispatch(Action action) { action(); return true; }
        public bool DispatchDelayed(TimeSpan delay, Action action) { Task.Delay(delay).ContinueWith(_ => action()); return true; }
        public IDispatcherTimer CreateTimer() => new TestTimer();
    }

    private sealed class TestTimer : IDispatcherTimer
    {
        public TimeSpan Interval { get; set; }
        public bool IsRepeating { get; set; }
        public bool IsRunning { get; private set; }
        public event EventHandler? Tick;
        public void Start() { IsRunning = true; }
        public void Stop() { IsRunning = false; }
    }
}
