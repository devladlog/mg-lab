namespace Contoso.Requests;

public sealed class ApprovalMetrics
{
    public int Approved { get; set; }
    public int Rejected { get; set; }
    public DateTimeOffset? LastDecisionAt { get; set; }
}

public interface IRequestStore
{
    ProjectRequest? Find(RequestCode code);
    void Save(ProjectRequest request);
}

public sealed class InMemoryRequestStore : IRequestStore
{
    private readonly Dictionary<RequestCode, ProjectRequest> _items = [];
    public ProjectRequest? Find(RequestCode code) => _items.GetValueOrDefault(code);
    public void Save(ProjectRequest request) => _items[request.Code] = request;
}

public abstract record DecisionResult
{
    private DecisionResult() { }
    public sealed record Ok(ProjectRequest Request) : DecisionResult;
    public sealed record NotFound(RequestCode Code) : DecisionResult;
    public sealed record Refused(string Reason) : DecisionResult;
}

/// <summary>
/// Primary constructor for dependencies. Gotcha: `time`, `store` and `metrics` are *parameters*, not readonly
/// fields - any method could reassign them. We copy `store` into a readonly field to show the safe pattern.
/// </summary>
public sealed class ApprovalService(TimeProvider time, IRequestStore store, ApprovalMetrics? metrics = null)
{
    private readonly IRequestStore _store = store;

    public DecisionResult Submit(RequestCode code)
    {
        if (_store.Find(code) is not { } request) return new DecisionResult.NotFound(code);
        if (request.State is not RequestState.Draft) return new DecisionResult.Refused("Only drafts can be submitted.");
        if (request.Budget >= Rules.JustificationFrom && string.IsNullOrWhiteSpace(request.Justification))
            return new DecisionResult.Refused("Budgets of 250,000 EUR or more need a justification.");

        var submitted = request with { State = new RequestState.Submitted(time.GetUtcNow()) };
        _store.Save(submitted);
        return new DecisionResult.Ok(submitted);
    }

    public DecisionResult Approve(RequestCode code, EmailAddress approver, string role)
    {
        if (_store.Find(code) is not { } request) return new DecisionResult.NotFound(code);
        if (request.State is not RequestState.Submitted) return new DecisionResult.Refused("Only submitted requests can be approved.");
        if (approver == request.RequestedBy) return new DecisionResult.Refused("You can't approve your own request.");

        var now = time.GetUtcNow();
        // Collection expression with a spread: a new list, the old one is untouched.
        var withApproval = request with { Approvals = [.. request.Approvals, new Approval(approver.Value, role, now)] };
        var final = Rules.IsFullyApproved(withApproval)
            ? withApproval with { State = new RequestState.Approved(approver.Value, now) }
            : withApproval;
        _store.Save(final);

        // C# 14 null-conditional assignment: metrics is optional, no if-block needed.
        if (final.State is RequestState.Approved) metrics?.Approved += 1;
        metrics?.LastDecisionAt = now;
        return new DecisionResult.Ok(final);
    }

    public DecisionResult Reject(RequestCode code, EmailAddress approver, string reason)
    {
        if (_store.Find(code) is not { } request) return new DecisionResult.NotFound(code);
        if (request.State is not RequestState.Submitted) return new DecisionResult.Refused("Only submitted requests can be rejected.");
        if (string.IsNullOrWhiteSpace(reason)) return new DecisionResult.Refused("A rejection needs a reason.");

        var rejected = request with { State = new RequestState.Rejected(approver.Value, reason.Trim()) };
        _store.Save(rejected);
        metrics?.Rejected += 1;
        metrics?.LastDecisionAt = time.GetUtcNow();
        return new DecisionResult.Ok(rejected);
    }
}
