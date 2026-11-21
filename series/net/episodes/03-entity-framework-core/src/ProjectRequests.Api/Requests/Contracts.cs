using System.ComponentModel.DataAnnotations;
using System.Globalization;
using ProjectRequests.Api.Data;

namespace ProjectRequests.Api.Requests;

/// <summary>What the API returns. <see cref="Version"/> goes back to the server on every write.</summary>
public sealed record RequestDto(
    int Id,
    string Title,
    decimal Budget,
    string Department,
    string RequestedBy,
    string? Justification,
    Priority Priority,
    RequestStatus Status,
    DateTime CreatedAtUtc,
    string? DecidedBy,
    DateTime? DecidedAtUtc,
    Guid Version);

public sealed record DepartmentSummary(string Department, int Requests, decimal TotalBudget, decimal ApprovedBudget);

/// <summary>Body of POST /api/requests.</summary>
public sealed class CreateProjectRequest : IValidatableObject
{
    [Required, StringLength(100, MinimumLength = 3)]
    public string Title { get; set; } = "";

    [Range(typeof(decimal), "1", "10000000")]
    public decimal Budget { get; set; }

    [Required, EmailAddress, StringLength(254)]
    public string RequestedBy { get; set; } = "";

    [Required, StringLength(8)]
    public string DepartmentCode { get; set; } = "";

    [StringLength(2000)]
    public string? Justification { get; set; }

    public IEnumerable<ValidationResult> Validate(ValidationContext validationContext) =>
        JustificationRule.Check(Budget, Justification);
}

/// <summary>Body of PUT /api/requests/{id}/budget. Only while the request is still Submitted.</summary>
public sealed class UpdateBudgetRequest : IValidatableObject
{
    [Range(typeof(decimal), "1", "10000000")]
    public decimal Budget { get; set; }

    [StringLength(2000)]
    public string? Justification { get; set; }

    /// <summary>The version the client read. A stale version means someone changed the request since.</summary>
    [Required]
    public Guid? Version { get; set; }

    public IEnumerable<ValidationResult> Validate(ValidationContext validationContext) =>
        JustificationRule.Check(Budget, Justification);
}

/// <summary>Body of POST /api/requests/{id}/decision.</summary>
public sealed class DecisionRequest
{
    [Required]
    public bool? Approve { get; set; }

    [Required, EmailAddress, StringLength(254)]
    public string DecidedBy { get; set; } = "";

    /// <summary>The version the approver looked at: you approve what you saw, or nothing.</summary>
    [Required]
    public Guid? Version { get; set; }
}

internal static class JustificationRule
{
    public static IEnumerable<ValidationResult> Check(decimal budget, string? justification)
    {
        if (PriorityRules.NeedsJustification(budget) && string.IsNullOrWhiteSpace(justification))
        {
            yield return new ValidationResult(
                string.Create(CultureInfo.InvariantCulture,
                    $"A justification is required for budgets of {PriorityRules.JustificationThreshold:N0} or more."),
                ["Justification"]);
        }
    }
}
