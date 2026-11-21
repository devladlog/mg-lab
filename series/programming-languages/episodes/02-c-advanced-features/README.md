# DEVLADLOG Code #2 — Advanced C# you'll actually use (C# 14 on .NET 10)

The same project request rules as episode 1, now as a C# library on **.NET 10 (LTS) with C# 14**, using the
"advanced" features where they earn their place, plus the places where they bite:

- **Records** with `required` / `init`, `with` expressions, and the C# 14 **`field` keyword** for validation
- **Pattern matching**: property, relational and type patterns, and **list patterns** for approval chains
- **C# 14 extension members**: extension *properties*, static extension members, extensions on `ReadOnlySpan<T>`
- **Generic math** (`IAdditionOperators`, `INumber<T>`): one `Sum<T>` for `int`, `decimal` and our `Euros`
- **C# 14 user-defined compound assignment** (`void operator +=`) that mutates in place
- **C# 14 null-conditional assignment** (`metrics?.Approved += 1`)
- **Span parsing** with `ISpanParsable<T>`: three request codes parsed from a slice of a string, **0 bytes allocated**
- **`[GeneratedRegex]` on a partial property** (C# 13 / .NET 9+)
- **Primary constructors** for dependencies, and why the parameters are not `readonly`
- `Nullable` + `TreatWarningsAsErrors` + `AnalysisLevel=latest-recommended` on every project

Rules: budget `>= 50,000` EUR is High priority; `>= 250,000` needs a justification and goes to the Board
(Finance first, Board last); you can't approve your own request.

| Path | What it is |
|---|---|
| [`Directory.Build.props`](Directory.Build.props) | `net10.0`, nullable, warnings as errors, `latest-recommended` analyzers, code style in build |
| [`src/Contoso.Requests/Euros.cs`](src/Contoso.Requests/Euros.cs) | `readonly record struct Euros` implementing generic math interfaces; `Totals.Sum<T>` |
| [`src/Contoso.Requests/ProjectRequest.cs`](src/Contoso.Requests/ProjectRequest.cs) | Immutable record, `required`/`init`, `field`-backed `Title`, `IReadOnlyList<Approval>` |
| [`src/Contoso.Requests/RequestState.cs`](src/Contoso.Requests/RequestState.cs) | Abstract record with private constructor + nested sealed records ("closed" hierarchy) |
| [`src/Contoso.Requests/Rules.cs`](src/Contoso.Requests/Rules.cs) | `RouteFor` (property/relational patterns), `IsFullyApproved` (list patterns), `Describe` |
| [`src/Contoso.Requests/RequestCode.cs`](src/Contoso.Requests/RequestCode.cs) | `ISpanParsable<RequestCode>`: `PR-2026-0042` parsed with `Slice`, no allocations |
| [`src/Contoso.Requests/EmailAddress.cs`](src/Contoso.Requests/EmailAddress.cs) | Validated value type, `[GeneratedRegex]` partial property |
| [`src/Contoso.Requests/Extensions.cs`](src/Contoso.Requests/Extensions.cs) | C# 14 `extension(...)` blocks: `TotalBudget`, `HighPriority`, `TimeProvider.Today`, `Euros.FromThousands`, span `Mean()` |
| [`src/Contoso.Requests/BudgetTally.cs`](src/Contoso.Requests/BudgetTally.cs) | `public void operator +=(ProjectRequest request)` |
| [`src/Contoso.Requests/ApprovalService.cs`](src/Contoso.Requests/ApprovalService.cs) | Primary constructor, `with` + collection expressions, null-conditional assignment, `DecisionResult` |
| [`src/Contoso.Requests.Demo/Program.cs`](src/Contoso.Requests.Demo/Program.cs) | Console walk-through used in the video (fixed clock, deterministic output) |
| [`tests/Contoso.Requests.Tests/`](tests/Contoso.Requests.Tests) | 53 xUnit tests, including the record and C# 14 binding gotchas |
| [`demo/Gotchas/`](demo/Gotchas) | Wrong on purpose: CS8509, CS9258, CS9264, plus two files that compile *silently* |
| [`demo/CSharp13/`](demo/CSharp13) | The same `LinqClash.cs` compiled as C# 13, to show the binding change |
| [`demo/expect-errors.sh`](demo/expect-errors.sh) | Builds/runs both demo projects and checks every diagnostic the video mentions |
| [`demo/expected-output.txt`](demo/expected-output.txt) | Real output of the tests, the console demo and `expect-errors.sh` |

## Build, test, run

```bash
dotnet test AdvancedCSharp.slnx -m:1                 # Passed: 53, Failed: 0 (~0.1 s test time)
dotnet run --project src/Contoso.Requests.Demo       # the walk-through from the video
./demo/expect-errors.sh                              # 6 checks "ok" (exit code 0)
```

Tested here with .NET SDK 10.0.115 on Linux (C# 14 is the default language version for `net10.0`). No cloud
resources, no packages besides xUnit and the test SDK.

## What we learned / gotchas

- **The three scary diagnostics are only warnings by default.** Without `TreatWarningsAsErrors`, building
  `demo/Gotchas` succeeds with warnings CS8509 (non-exhaustive switch), CS9258 (`field` rebinding) and CS9264. We
  checked with `-p:TreatWarningsAsErrors=false`. Turn warnings into errors, or these slip through.
- **A "closed" record hierarchy isn't closed for the compiler.** `RequestState` has a private constructor and only
  nested sealed records, and a switch over all four still gets CS8509. You need a `_ =>` arm (we throw
  `UnreachableException`), which also means adding a fifth state is **not** a compile error. TypeScript's unions
  (episode 1) catch that; C# doesn't.
- **`field` changes the meaning of existing code.** A class with a member called `field` and an accessor that uses
  `field` now binds to a new synthesized backing field (CS9258). Learn: use `@field` or `this.field`, or rename.
- **Primary constructor parameters are parameters.** `time = TimeProvider.System;` inside a method compiles without
  a warning (`demo/Gotchas/PrimaryConstructor.cs`). Learn: "Primary constructor parameters can be assigned to." If it
  must not change, copy it into a `readonly` field (we do it for `store` in `ApprovalService`).
- **C# 14 can pick a different method for the same source line.** `values.Average()` on an `int[]`, with
  `System.Linq` and our own `Average(this ReadOnlySpan<int>)` both imported: C# 13 calls LINQ (prints 2), C# 14
  calls the span extension (returns -1). No warning in either version. Learn documents it as a compiler breaking
  change ("different overloads might be chosen compared to C# 13"). If you mean LINQ, call `Enumerable.Average(x)`.
- **Two extension blocks in one static class trigger CA1708** ("names should differ by more than case") with the
  .NET 10.0.115 SDK analyzers at `latest-recommended`: it reports the compiler-generated members. We put one receiver
  type per static class, which reads better anyway.
- **Record equality and `with` are shallow.** Two requests with equal approvals in two different lists are *not*
  equal, and `with` shares the same list instance. Both are pinned by tests (`Gotcha_*` in `RecordTests`). Use
  immutable collections and build new ones with collection expressions (`[.. old, item]`).
- **`GC.GetAllocatedBytesForCurrentThread()` is a cheap allocation test.** Warm up the code first (JIT) and the
  span parser reports exactly 0 bytes for three codes.

## References
- [What's new in C# 14](https://learn.microsoft.com/dotnet/csharp/whats-new/csharp-14)
- [Extension members](https://learn.microsoft.com/dotnet/csharp/programming-guide/classes-and-structs/extension-methods) and [`extension` keyword](https://learn.microsoft.com/dotnet/csharp/language-reference/keywords/extension)
- [`field` keyword (field-backed properties)](https://learn.microsoft.com/dotnet/csharp/language-reference/keywords/field)
- [Tutorial: Create compound assignment operators](https://learn.microsoft.com/dotnet/csharp/whats-new/tutorials/compound-assignment-operators)
- [Compiler breaking changes in .NET 10 (span overloads chosen in more scenarios)](https://learn.microsoft.com/dotnet/csharp/whats-new/breaking-changes/compiler%20breaking%20changes%20-%20dotnet%2010)
- [C# 14 overload resolution with span parameters (.NET 10 compatibility)](https://learn.microsoft.com/dotnet/core/compatibility/core-libraries/10.0/csharp-overload-resolution)
- [Declare primary constructors for classes and structs](https://learn.microsoft.com/dotnet/csharp/whats-new/tutorials/primary-constructors)
- [Pattern matching: list patterns, property and relational patterns](https://learn.microsoft.com/dotnet/csharp/language-reference/operators/patterns)
- [Generic math](https://learn.microsoft.com/dotnet/standard/generics/math)
- [Regular expression source generators (`[GeneratedRegex]` on partial properties)](https://learn.microsoft.com/dotnet/standard/base-types/regular-expression-source-generators)
- [Records](https://learn.microsoft.com/dotnet/csharp/language-reference/builtin-types/record)
- [CA1708: Identifiers should differ by more than case](https://learn.microsoft.com/dotnet/fundamentals/code-analysis/quality-rules/ca1708)
- Blog: [C# Advanced Features — Complete Guide](https://www.devladlog.com/articles/programming-languages/2026-06-03-c-advanced-features-complete-guide-2026/)
