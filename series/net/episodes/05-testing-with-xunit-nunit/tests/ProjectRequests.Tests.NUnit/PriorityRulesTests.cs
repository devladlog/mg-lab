using System.ComponentModel.DataAnnotations;
using ProjectRequests.Api.Data;
using ProjectRequests.Api.Requests;

namespace ProjectRequests.Api.Tests;

/// <summary>The same rules as the xUnit PriorityRulesTests, written the NUnit way.</summary>
[Category("Unit")]
public sealed class PriorityRulesTests
{
    [TestCase(1, Priority.Standard)]
    [TestCase(49_999.99, Priority.Standard)]            // NUnit converts the double to decimal too
    [TestCase(50_000, Priority.High)]
    [TestCase(10_000_000, Priority.High)]
    public void Classify_uses_the_50k_threshold(decimal budget, Priority expected) =>
        Assert.That(PriorityRules.Classify(budget), Is.EqualTo(expected));

    private static IEnumerable<TestCaseData<decimal, string?, bool>> JustificationCases()
    {
        yield return new(249_999m, null, true);
        yield return new(250_000m, null, false);
        yield return new(250_000m, "   ", false);
        yield return new(250_000m, "Replaces the 2019 fleet", true);
    }

    [TestCaseSource(nameof(JustificationCases))]
    public void Budgets_from_250k_need_a_justification(decimal budget, string? justification, bool valid)
    {
        var input = new CreateProjectRequest
        {
            Title = "Laptop refresh", Budget = budget, RequestedBy = "alex.demo@contoso.com",
            DepartmentCode = "FIN", Justification = justification,
        };
        var results = new List<ValidationResult>();

        var isValid = Validator.TryValidateObject(input, new ValidationContext(input), results, validateAllProperties: true);

        using (Assert.EnterMultipleScope())                     // report every failed assert, not just the first
        {
            Assert.That(isValid, Is.EqualTo(valid));
            Assert.That(results.SelectMany(r => r.MemberNames), valid ? Is.Empty : Is.EqualTo(new[] { "Justification" }));
        }
    }
}
