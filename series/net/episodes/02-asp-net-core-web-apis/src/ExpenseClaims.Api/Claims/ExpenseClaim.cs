using System.ComponentModel.DataAnnotations;

namespace ExpenseClaims.Api.Claims;

public enum ClaimStatus { Submitted, Approved }

/// <summary>A stored expense claim, as returned by the API.</summary>
public sealed record ExpenseClaim(
    int Id,
    string Description,
    decimal Amount,
    string Currency,
    DateOnly IncurredOn,
    string Category,
    string SubmittedBy,
    ClaimStatus Status,
    DateTimeOffset SubmittedAt,
    string? ApprovedBy = null);

/// <summary>
/// Body of POST /api/claims. [ApiController] runs these rules during model binding and returns
/// a 400 ValidationProblemDetails automatically — the action never sees an invalid model.
/// </summary>
public sealed class SubmitClaimRequest : IValidatableObject
{
    public const int MaxAgeDays = 90;

    [Required, StringLength(200, MinimumLength = 3)]
    public string Description { get; set; } = "";

    [Range(typeof(decimal), "0.01", "5000")]
    public decimal Amount { get; set; }

    [Required, RegularExpression("^[A-Z]{3}$", ErrorMessage = "Currency must be a three-letter ISO code, like EUR.")]
    public string Currency { get; set; } = "EUR";

    [Required]
    public DateOnly? IncurredOn { get; set; }

    [Required, AllowedValues("Travel", "Meals", "Equipment", "Training")]
    public string Category { get; set; } = "";

    public IEnumerable<ValidationResult> Validate(ValidationContext validationContext)
    {
        // MVC passes the request services to the ValidationContext, so the rule uses the app's clock.
        var clock = validationContext.GetService(typeof(TimeProvider)) as TimeProvider ?? TimeProvider.System;
        var today = DateOnly.FromDateTime(clock.GetUtcNow().UtcDateTime);

        if (IncurredOn > today)
            yield return new ValidationResult("The expense date can't be in the future.", [nameof(IncurredOn)]);
        else if (IncurredOn < today.AddDays(-MaxAgeDays))
            yield return new ValidationResult($"Claims must be submitted within {MaxAgeDays} days.", [nameof(IncurredOn)]);
    }
}
