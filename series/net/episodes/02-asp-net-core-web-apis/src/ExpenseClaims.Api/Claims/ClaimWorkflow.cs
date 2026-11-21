using System.Collections.Concurrent;

namespace ExpenseClaims.Api.Claims;

/// <summary>Domain errors carry their own HTTP status; <c>DomainExceptionHandler</c> turns them into problem details.</summary>
public abstract class DomainException(string title, string detail, int statusCode) : Exception(detail)
{
    public string Title { get; } = title;
    public int StatusCode { get; } = statusCode;
}

public sealed class ClaimNotFoundException(int id)
    : DomainException("Claim not found.", $"There is no claim {id}.", StatusCodes.Status404NotFound);

public sealed class ClaimConflictException(string title, string detail)
    : DomainException(title, detail, StatusCodes.Status409Conflict);

/// <summary>In-memory store and the approval rules. Entity Framework Core replaces the dictionary in episode 3.</summary>
public sealed class ClaimWorkflow(TimeProvider clock)
{
    private readonly ConcurrentDictionary<int, ExpenseClaim> _claims = new();
    private int _nextId;

    public ExpenseClaim Submit(SubmitClaimRequest input, string userId)
    {
        var id = Interlocked.Increment(ref _nextId);
        var claim = new ExpenseClaim(id, input.Description.Trim(), input.Amount, input.Currency,
            input.IncurredOn!.Value, input.Category, userId, ClaimStatus.Submitted, clock.GetUtcNow());
        _claims[id] = claim;
        return claim;
    }

    public ExpenseClaim? Find(int id) => _claims.GetValueOrDefault(id);

    public IReadOnlyList<ExpenseClaim> List(string? submittedBy, ClaimStatus? status) =>
        _claims.Values
            .Where(c => submittedBy is null || c.SubmittedBy == submittedBy)
            .Where(c => status is null || c.Status == status)
            .OrderBy(c => c.Id)
            .ToList();

    public ExpenseClaim Approve(int id, string approverId)
    {
        var claim = Find(id) ?? throw new ClaimNotFoundException(id);

        if (claim.SubmittedBy == approverId)
            throw new ClaimConflictException("You can't approve your own claim.",
                "Ask another approver to review it.");

        if (claim.Status != ClaimStatus.Submitted)
            throw new ClaimConflictException("Claim already approved.", $"Claim {id} was approved by {claim.ApprovedBy}.");

        var approved = claim with { Status = ClaimStatus.Approved, ApprovedBy = approverId };
        if (!_claims.TryUpdate(id, approved, claim))
            throw new ClaimConflictException("Claim changed.", "Read the claim again and retry.");
        return approved;
    }
}
