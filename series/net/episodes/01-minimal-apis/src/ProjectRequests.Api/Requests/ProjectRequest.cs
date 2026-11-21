using System.ComponentModel.DataAnnotations;
using System.Globalization;

namespace ProjectRequests.Api.Requests;

public enum Priority { Standard, High }

public enum RequestStatus { Submitted, Approved, Rejected }

/// <summary>A stored project request, as returned by the API.</summary>
public sealed record ProjectRequest(
    int Id,
    string Title,
    decimal Budget,
    string RequestedBy,
    string? Justification,
    Priority Priority,
    RequestStatus Status,
    DateTimeOffset CreatedAt,
    string? DecidedBy = null);

/// <summary>
/// Body of POST /api/requests. Validated by the built-in Minimal API validation (.NET 10, AddValidation):
/// the attributes run first, then <see cref="Validate"/> for the cross-field rule.
/// </summary>
public sealed class CreateProjectRequest : IValidatableObject
{
    [Required, StringLength(100, MinimumLength = 3)]
    public string Title { get; set; } = "";

    [Range(typeof(decimal), "1", "10000000")]
    public decimal Budget { get; set; }

    [Required, EmailAddress]
    public string RequestedBy { get; set; } = "";

    [StringLength(2000)]
    public string? Justification { get; set; }

    public IEnumerable<ValidationResult> Validate(ValidationContext validationContext)
    {
        if (PriorityRules.NeedsJustification(Budget) && string.IsNullOrWhiteSpace(Justification))
        {
            yield return new ValidationResult(
                string.Create(CultureInfo.InvariantCulture,
                    $"A justification is required for budgets of {PriorityRules.JustificationThreshold:N0} or more."),
                [nameof(Justification)]);
        }
    }
}

/// <summary>Body of POST /api/requests/{id}/decision.</summary>
public sealed class DecisionRequest
{
    [Required]
    public bool? Approve { get; set; }

    [Required, EmailAddress]
    public string DecidedBy { get; set; } = "";
}
