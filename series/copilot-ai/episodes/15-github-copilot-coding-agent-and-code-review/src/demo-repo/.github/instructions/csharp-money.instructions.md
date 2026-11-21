---
applyTo: "src/**/*.cs"
---
# Money code review rules

- Flag any `double` or `float` used for a price, discount or total. Use `decimal`.
- Flag `Math.Round` without `MidpointRounding.AwayFromZero`.
- Flag public methods that accept a price or a count and do not validate negative values.
- Flag `catch` blocks that swallow an exception without logging or rethrowing.
