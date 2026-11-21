using ProjectRequests.Contracts;

namespace ProjectRequests.Web.Client.Services;

/// <summary>
/// What the live board shows. Events and the initial list can arrive in any order (we connect FIRST, then load
/// the list, so nothing falls in the gap between the two), so every write goes through <see cref="Apply"/>:
/// a decided request is never overwritten by an older "submitted" copy of itself.
/// </summary>
public sealed class BoardState
{
    private readonly Dictionary<int, RequestDto> _requests = [];

    /// <summary>Newest first.</summary>
    public IReadOnlyList<RequestDto> Requests => _requests.Values.OrderByDescending(r => r.Id).ToList();

    /// <summary>Ids changed by a live event, for the highlight.</summary>
    public HashSet<int> Highlighted { get; } = [];

    public void Load(IEnumerable<RequestDto> requests)
    {
        foreach (var r in requests)
            Apply(r, highlight: false);
    }

    /// <summary>Drop everything (after a reconnect we reload: events sent while we were away are gone).</summary>
    public void Clear()
    {
        _requests.Clear();
        Highlighted.Clear();
    }

    public bool Apply(RequestDto incoming, bool highlight = true)
    {
        if (_requests.TryGetValue(incoming.Id, out var current) && IsOlder(incoming, current))
            return false;

        _requests[incoming.Id] = incoming;
        if (highlight)
            Highlighted.Add(incoming.Id);
        return true;
    }

    /// <summary>
    /// Version is a Guid (not ordered), so order by what we know: a decision is final, and a newer decision time
    /// wins. Two Submitted copies: take the incoming one (a budget change).
    /// </summary>
    private static bool IsOlder(RequestDto incoming, RequestDto current) =>
        (current.Status != RequestStatus.Submitted && incoming.Status == RequestStatus.Submitted)
        || (current.DecidedAtUtc is { } a && incoming.DecidedAtUtc is { } b && b < a);
}
