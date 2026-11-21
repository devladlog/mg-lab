using System.ComponentModel.DataAnnotations;
using ProjectRequests.Api.Data;
using ProjectRequests.Api.Requests;

namespace ProjectRequests.Api.Tests;

/// <summary>Pure unit tests: no host, no database. Traits are what --filter-trait selects on.</summary>
[Trait("Category", "Unit")]
public sealed class PriorityRulesTests
{
    [Theory]
    [InlineData(1, Priority.Standard)]
    [InlineData(49_999.99, Priority.Standard)]          // attributes can't hold decimals: xUnit converts the double
    [InlineData(50_000, Priority.High)]
    [InlineData(10_000_000, Priority.High)]
    public void Classify_uses_the_50k_threshold(decimal budget, Priority expected) =>
        Assert.Equal(expected, PriorityRules.Classify(budget));

    /// <summary>Strongly typed rows: the compiler checks every value against the parameters.</summary>
    public static TheoryData<decimal, string?, bool> JustificationCases => new()
    {
        { 249_999m, null, true },
        { 250_000m, null, false },
        { 250_000m, "   ", false },
        { 250_000m, "Replaces the 2019 fleet", true },
    };

    [Theory]
    [MemberData(nameof(JustificationCases))]
    public void Budgets_from_250k_need_a_justification(decimal budget, string? justification, bool valid)
    {
        var input = new CreateProjectRequest
        {
            Title = "Laptop refresh", Budget = budget, RequestedBy = "alex.demo@contoso.com",
            DepartmentCode = "FIN", Justification = justification,
        };
        var results = new List<ValidationResult>();

        var isValid = Validator.TryValidateObject(input, new ValidationContext(input), results, validateAllProperties: true);

        Assert.Equal(valid, isValid);
        if (!valid)
            Assert.Equal(["Justification"], Assert.Single(results).MemberNames);
    }
}
