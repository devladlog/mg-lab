namespace Contoso.Requests;

public enum Priority { Standard, High }

/// <summary>
/// An immutable request. <c>required</c> + <c>init</c>: the object initializer must set them, nobody can change them later.
/// </summary>
public sealed record ProjectRequest
{
    public required RequestCode Code { get; init; }

    /// <summary>C# 14 <c>field</c>: validation in the accessor without declaring a backing field.</summary>
    public required string Title
    {
        get;
        init => field = string.IsNullOrWhiteSpace(value) || value.Trim().Length < 3
            ? throw new ArgumentException("Title must have at least 3 characters.", nameof(value))
            : value.Trim();
    }

    public required Euros Budget { get; init; }
    public required EmailAddress RequestedBy { get; init; }
    public string? Justification { get; init; }
    public RequestState State { get; init; } = new RequestState.Draft();

    /// <summary>
    /// Approvals so far. IReadOnlyList + collection expressions. Careful: `with` copies the reference,
    /// and record equality compares the list by reference (see the tests).
    /// </summary>
    public IReadOnlyList<Approval> Approvals { get; init; } = [];
}
