---
applyTo: "tests/**/*.cs"
---
# Test code rules

- One behaviour per test. No `Thread.Sleep`, no random data, no dependence on the machine's culture.
- Money literals use the `m` suffix (`12.25m`). Do not compare `decimal` values through `double`.
