using System.Collections.Concurrent;

namespace ProjectRequests.Api.Requests;

public interface IRequestStore
{
    ProjectRequest Add(CreateProjectRequest input);
    ProjectRequest? Get(int id);
    IReadOnlyList<ProjectRequest> List(Priority? priority = null);
    bool TryUpdate(ProjectRequest updated, ProjectRequest expected);
}

/// <summary>
/// In-memory store, registered as a singleton. Good enough for this episode; Entity Framework Core is episode 3.
/// </summary>
public sealed class InMemoryRequestStore(TimeProvider clock) : IRequestStore
{
    private readonly ConcurrentDictionary<int, ProjectRequest> _items = new();
    private int _nextId;

    public ProjectRequest Add(CreateProjectRequest input)
    {
        var id = Interlocked.Increment(ref _nextId);
        var item = new ProjectRequest(
            id,
            input.Title.Trim(),
            input.Budget,
            input.RequestedBy.Trim().ToLowerInvariant(),
            string.IsNullOrWhiteSpace(input.Justification) ? null : input.Justification.Trim(),
            PriorityRules.Classify(input.Budget),
            RequestStatus.Submitted,
            clock.GetUtcNow());
        _items[id] = item;
        return item;
    }

    public ProjectRequest? Get(int id) => _items.GetValueOrDefault(id);

    public IReadOnlyList<ProjectRequest> List(Priority? priority = null) =>
        _items.Values
            .Where(r => priority is null || r.Priority == priority)
            .OrderBy(r => r.Id)
            .ToList();

    // Optimistic update: only succeeds if nobody changed the item since we read it.
    public bool TryUpdate(ProjectRequest updated, ProjectRequest expected) =>
        _items.TryUpdate(updated.Id, updated, expected);
}
