using ProjectRequests.Feed;

namespace ProjectRequests.Web.Tests;

/// <summary>Stand-in for the SignalR connection in component tests: the test plays the server.</summary>
public sealed class FakeRequestsFeed : IRequestsFeed, IRequestsFeedFactory
{
    public FeedState State { get; private set; }
    public string? Department { get; private set; }
    public List<string?> Watched { get; } = [];
    public int CreateCalls { get; private set; }
    public bool Disposed { get; private set; }
    public Exception? StartFailure { get; set; }

    public event Action<RequestDto>? Created;
    public event Action<RequestDto>? Updated;
    public event Action<FeedState>? StateChanged;
    public event Action? Resubscribed;

    public IRequestsFeed Create()
    {
        CreateCalls++;
        return this;
    }

    public Task StartAsync(string? department, CancellationToken ct = default)
    {
        if (StartFailure is not null)
            throw StartFailure;
        SetState(FeedState.Connected);
        return WatchAsync(department, ct);
    }

    public Task WatchAsync(string? department, CancellationToken ct = default)
    {
        Department = string.IsNullOrEmpty(department) ? null : department;
        Watched.Add(Department);
        return Task.CompletedTask;
    }

    public void PushCreated(RequestDto r) => Created?.Invoke(r);
    public void PushUpdated(RequestDto r) => Updated?.Invoke(r);
    public void SetState(FeedState s) { State = s; StateChanged?.Invoke(s); }
    public void Reconnect() { SetState(FeedState.Connected); Resubscribed?.Invoke(); }

    public ValueTask DisposeAsync()
    {
        Disposed = true;
        return ValueTask.CompletedTask;
    }
}
