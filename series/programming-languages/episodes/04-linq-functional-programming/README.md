# DEVLADLOG Code #4 — LINQ and functional C#, without the surprises (.NET 10, EF Core 10)

A portfolio report over the same Contoso project requests as episodes 1-3, written as **pure functions over
immutable records**, then the same queries against a **real SQLite database with EF Core 10**, to see what really
runs:

- **Functional core**: static, pure functions (data in, data out, input never changed), records + `with`,
  rules passed in as `Func<ProjectRequest, bool>`
- **New LINQ operators**: `CountBy`, `AggregateBy`, `Index` (.NET 9) and `LeftJoin` (.NET 10)
- **Method syntax vs query syntax**: the same report both ways, pinned equal by a test
- **Errors as values**: a `Result<T>` with `Select`/`SelectMany`, so a CSV line parser is a C# query
  (`from ... from ... select`) that stops at the first error
- **Deferred execution, observed**: a counting source shows a query running 3 times; the captured-variable trap;
  **CA1851** turned on (it's off by default in .NET 10)
- **IQueryable vs IEnumerable**: same method body, different parameter type: `WHERE` in SQL and 5 rows, or no
  `WHERE` and 12 rows, with the same 5 results
- **What EF Core 10 can't translate**: a C# method in `Where`, `CountBy` on a `DbSet`, an `OrderBy` on a
  constructor-projected record, and how to fix each

| Path | What it is |
|---|---|
| [`Directory.Build.props`](Directory.Build.props) / [`.editorconfig`](.editorconfig) | `net10.0`, nullable, warnings as errors, `latest-recommended`; CA1851 on |
| [`src/Contoso.Portfolio/Model.cs`](src/Contoso.Portfolio/Model.cs) | `ProjectRequest`, `Department` records; `Policy` (50,000 = High, 250,000 = Board), `IsStrategic` |
| [`src/Contoso.Portfolio/SampleData.cs`](src/Contoso.Portfolio/SampleData.cs) | 12 fictional requests, 5 departments (Legal has none) |
| [`src/Contoso.Portfolio/Reports.cs`](src/Contoso.Portfolio/Reports.cs) | Pure report functions: `AggregateBy`, query syntax twin, `CountBy`, `Index`, `LeftJoin`, `Needing(rule)` |
| [`src/Contoso.Portfolio/Result.cs`](src/Contoso.Portfolio/Result.cs) / [`Import.cs`](src/Contoso.Portfolio/Import.cs) | `Result<T>` + `Select`/`SelectMany`; CSV import as a query, rejected lines with line numbers |
| [`src/Contoso.Portfolio/Deferred.cs`](src/Contoso.Portfolio/Deferred.cs) | `CountingSource<T>`, multiple enumeration, captured variable |
| [`src/Contoso.Portfolio/PortfolioDb.cs`](src/Contoso.Portfolio/PortfolioDb.cs) | EF Core 10 `DbContext` on SQLite, seeds the sample data, logs every executed SQL command |
| [`src/Contoso.Portfolio/Queries.cs`](src/Contoso.Portfolio/Queries.cs) | `AtLeast(IQueryable)` vs `AtLeast(IEnumerable)`, `LeftJoin` to `LEFT JOIN`, the untranslatable queries and their fixes |
| [`src/Contoso.Portfolio.Cli/Program.cs`](src/Contoso.Portfolio.Cli/Program.cs) | Console app used in the video: `report`, `import FILE`, `deferred`, `sql` |
| [`samples/requests.csv`](samples/requests.csv) | 8 lines: 4 valid, 4 with one problem each |
| [`tests/Contoso.Portfolio.Tests/`](tests/Contoso.Portfolio.Tests) | 34 xUnit tests, including real SQLite databases (one temp file per test) |
| [`demo/Analyzers/`](demo/Analyzers) / [`demo/expect-errors.sh`](demo/expect-errors.sh) | Wrong on purpose: CA1851; the script checks it and runs the deferred demo |
| [`demo/expected-output.txt`](demo/expected-output.txt) | Real output of the tests, all four CLI modes and the script |

## Build, test, run

```bash
dotnet test LinqFunctional.slnx -m:1                        # Passed: 34, Failed: 0 (~2 s)
dotnet run --project src/Contoso.Portfolio.Cli -- report    # pure functions over the sample data
dotnet run --project src/Contoso.Portfolio.Cli -- import samples/requests.csv   # 4 accepted, 4 rejected
dotnet run --project src/Contoso.Portfolio.Cli -- deferred  # read 3 times vs 1; 5 then 1
dotnet run --project src/Contoso.Portfolio.Cli -- sql       # creates ./portfolio.db, prints the SQL EF Core sent
./demo/expect-errors.sh                                     # CA1851 as a build error, then the deferred demo (exit 0)
```

Tested here with .NET SDK 10.0.115 on Linux, `Microsoft.EntityFrameworkCore.Sqlite` 10.0.15, 5 consecutive green
runs. SQLite is a real embedded database (a file), so no server or container is needed; the tests create and delete
one database file per test in the temp folder. `portfolio.db` is git-ignored.

## What we learned / gotchas

- **An `IEnumerable<T>` parameter silently moves the filter into memory.** `AtLeast(db.Requests, 50_000)` produced
  `WHERE ef_compare("r"."Budget", @threshold) >= 0` and tracked 5 entities; the identical method body with an
  `IEnumerable<ProjectRequest>` parameter produced a `SELECT` without `WHERE` and tracked all 12 rows. Same 5
  results, no exception, no warning. Pinned by `Gotcha_IEnumerable_parameter_reads_the_whole_table_silently`.
- **`CountBy`/`AggregateBy` compile on a `DbSet` but EF Core 10 can't translate them.** `Queryable.CountBy` exists
  since .NET 9; with EF Core 10.0.15 + SQLite both threw *"The LINQ expression ... could not be translated"* at run
  time. `GroupBy(...).Select(g => g.Count())` becomes `GROUP BY`. Use the new operators freely in LINQ to Objects.
- **`OrderBy` after projecting into a positional record wasn't translated.** Our first `LeftJoin` query projected into
  `new DepartmentRow(...)` and then ordered by `x.Department`: EF Core 10 threw "could not be translated". Ordering an
  anonymous type and projecting into the record last works (`Gotcha_OrderBy_on_a_constructor_projected_record...`).
- **A C# method inside `Where` fails when the query runs, not when it compiles.** EF Core only evaluates on the client
  in the top-level projection; anywhere else an untranslatable expression throws (Learn: client vs server evaluation).
  Fix: filter in SQL first, then apply the C# rule in memory explicitly.
- **CA1851 is off by default, even at `latest-recommended`.** Without our `.editorconfig` line the analyzer demo
  builds clean; with it, the build fails on the method that calls `Count()` and then loops. Learn lists CA1851 as
  "Enabled by default in .NET 10: No".
- **CA1851 needs the pragma around the whole pattern.** Our deliberate multiple-enumeration demo still failed the build
  until `#pragma warning disable CA1851` covered the line that *defines* the query too: the rule reports every
  enumeration site, including the first.
- **SQLite has no `decimal` type.** EF Core translates decimal comparisons to functions it registers on the
  connection (`ef_compare`), which is why the generated `WHERE` looks unusual. Learn: SQLite provider limitations.
- **Logged SQL hides parameter values** (`@threshold='?'`) unless you enable sensitive data logging. We left it off.
- **Query syntax has no left join.** `LeftJoin`/`RightJoin` are method-only in C# (Learn: join operations); the same is
  true for `CountBy`, `AggregateBy` and `Index`.
- **Analyzer noise we hit while building**: CA1000 (no static members on generic types) moved `Result.Ok/Fail` to a
  non-generic class; CA1725 wanted `optionsBuilder`/`modelBuilder` as parameter names in the `DbContext` overrides.

## References
- [LINQ queries: deferred and immediate execution](https://learn.microsoft.com/dotnet/csharp/fundamentals/statements/linq) and [Introduction to LINQ queries (classification by manner of execution)](https://learn.microsoft.com/dotnet/csharp/linq/get-started/introduction-to-linq-queries)
- [What's new in .NET 9 libraries: CountBy, AggregateBy, Index](https://learn.microsoft.com/dotnet/core/whats-new/dotnet-9/libraries#linq)
- [Join operations in LINQ (LeftJoin, RightJoin in .NET 10)](https://learn.microsoft.com/dotnet/csharp/linq/standard-query-operators/join-operations)
- [What's new in EF Core 10 (LeftJoin/RightJoin translation)](https://learn.microsoft.com/ef/core/what-is-new/ef-core-10.0/whatsnew)
- [Client vs. server evaluation](https://learn.microsoft.com/ef/core/querying/client-eval)
- [SQLite EF Core provider limitations (decimal)](https://learn.microsoft.com/ef/core/providers/sqlite/limitations) and [function mappings](https://learn.microsoft.com/ef/core/providers/sqlite/functions)
- [CA1851: Possible multiple enumerations of IEnumerable collection](https://learn.microsoft.com/dotnet/fundamentals/code-analysis/quality-rules/ca1851)
- [`Enumerable.AggregateBy`](https://learn.microsoft.com/dotnet/api/system.linq.enumerable.aggregateby), [`Enumerable.CountBy`](https://learn.microsoft.com/dotnet/api/system.linq.enumerable.countby), [`Queryable.CountBy`](https://learn.microsoft.com/dotnet/api/system.linq.queryable.countby)
- Blog: [LINQ & Functional Programming — Complete Guide](https://www.devladlog.com/articles/programming-languages/2025-06-21-linq-functional-programming-complete-guide-2025/)
