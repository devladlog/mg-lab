# Contoso Bikes pricing: instructions for Copilot

## Build and test
- Build and run all tests with `dotnet test Contoso.Bikes.sln`. Run it before you finish; the pull request must be green.
- Target framework is net10.0. Do not add packages unless the task says so.

## Money
- Money is always `decimal`, never `double` or `float`.
- Round to cents with `Math.Round(value, 2, MidpointRounding.AwayFromZero)`. Finance rounds halves away from zero.
- Reject negative prices and negative years with `ArgumentOutOfRangeException`.

## Tests
- Every behaviour change needs an xunit test in `tests/Contoso.Bikes.Pricing.Tests`.
- Name tests `Method_does_what_when_condition`. Put expected values in `InlineData` when there are several cases.

## Pull requests
- Keep the change small and in one pull request. Describe what changed and how you tested it.
