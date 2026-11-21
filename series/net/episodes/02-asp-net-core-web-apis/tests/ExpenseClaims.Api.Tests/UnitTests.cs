using System.ComponentModel.DataAnnotations;
using ExpenseClaims.Api.Claims;

namespace ExpenseClaims.Api.Tests;

public class ValidationRuleTests
{
    private static List<ValidationResult> Validate(SubmitClaimRequest request)
    {
        var results = new List<ValidationResult>();
        Validator.TryValidateObject(request, new ValidationContext(request), results, validateAllProperties: true);
        return results;
    }

    private static SubmitClaimRequest Valid() => new()
    {
        Description = "Train to Porto",
        Amount = 48.50m,
        Currency = "EUR",
        Category = "Travel",
        IncurredOn = DateOnly.FromDateTime(DateTime.UtcNow),
    };

    [Fact]
    public void A_valid_claim_has_no_errors() => Assert.Empty(Validate(Valid()));

    [Theory]
    [InlineData("eur")]
    [InlineData("EURO")]
    public void Currency_must_be_three_upper_case_letters(string currency)
    {
        var request = Valid();
        request.Currency = currency;
        Assert.Contains(Validate(request), r => r.MemberNames.Contains(nameof(SubmitClaimRequest.Currency)));
    }

    [Fact]
    public void Category_must_be_one_of_the_allowed_values()
    {
        var request = Valid();
        request.Category = "Party";
        Assert.Contains(Validate(request), r => r.MemberNames.Contains(nameof(SubmitClaimRequest.Category)));
    }

    [Fact]
    public void Expenses_older_than_90_days_are_rejected()
    {
        var request = Valid();
        request.IncurredOn = DateOnly.FromDateTime(DateTime.UtcNow).AddDays(-91);
        var error = Assert.Single(Validate(request));
        Assert.Equal("Claims must be submitted within 90 days.", error.ErrorMessage);
    }
}

public class ClaimWorkflowTests
{
    private readonly ClaimWorkflow _workflow = new(TimeProvider.System);

    private ExpenseClaim Submit(string by) => _workflow.Submit(new SubmitClaimRequest
    {
        Description = "Hotel", Amount = 120m, Currency = "EUR", Category = "Travel",
        IncurredOn = DateOnly.FromDateTime(DateTime.UtcNow),
    }, by);

    [Fact]
    public void Another_user_with_the_role_can_approve()
    {
        var claim = Submit("alex");
        var approved = _workflow.Approve(claim.Id, "sam");
        Assert.Equal(ClaimStatus.Approved, approved.Status);
        Assert.Equal("sam", approved.ApprovedBy);
    }

    [Fact]
    public void Approving_your_own_claim_is_a_conflict()
    {
        var claim = Submit("sam");
        var ex = Assert.Throws<ClaimConflictException>(() => _workflow.Approve(claim.Id, "sam"));
        Assert.Equal(409, ex.StatusCode);
    }

    [Fact]
    public void Approving_twice_is_a_conflict()
    {
        var claim = Submit("alex");
        _workflow.Approve(claim.Id, "sam");
        Assert.Throws<ClaimConflictException>(() => _workflow.Approve(claim.Id, "kim"));
    }

    [Fact]
    public void Unknown_claim_is_not_found()
    {
        var ex = Assert.Throws<ClaimNotFoundException>(() => _workflow.Approve(404, "sam"));
        Assert.Equal(404, ex.StatusCode);
    }
}
