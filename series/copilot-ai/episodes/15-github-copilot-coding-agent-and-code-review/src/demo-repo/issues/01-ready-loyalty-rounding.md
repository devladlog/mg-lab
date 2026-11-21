# Loyalty price rounds halves to even; finance expects away from zero

## Problem
`DiscountCalculator.LoyaltyPrice` uses `Math.Round(value, 2)`, which rounds halves to the nearest even cent.
For a dealer with 3 years, a list price of 12.25 gives 11.02. Finance's price list says 11.03.

## Acceptance criteria
- [ ] `LoyaltyPrice(12.25m, 3)` returns `11.03m`; `LoyaltyPrice(12.45m, 3)` returns `11.21m` (11.205 rounds up).
- [ ] A negative `listPrice` or negative `years` throws `ArgumentOutOfRangeException` (parameter name in the exception).
- [ ] New xunit tests cover the two prices above and both exceptions; the existing tests still pass.
- [ ] `dotnet test Contoso.Bikes.sln` is green.

## Where to look
- `src/Contoso.Bikes.Pricing/DiscountCalculator.cs`
- `tests/Contoso.Bikes.Pricing.Tests/DiscountCalculatorTests.cs`

## Out of scope
- Changing the loyalty rates or adding new discount types.
