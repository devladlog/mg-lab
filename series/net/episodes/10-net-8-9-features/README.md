# DEVLADLOG .NET #10 — What .NET 8 and 9 gave you (and what you can use today on .NET 10)

The series runs on **.NET 10 (LTS)**, but most teams arrive from .NET 8 or 9, and **both reached end of support in
November 2026**: Microsoft's lifecycle page lists 11/11/2026 for .NET 8 and for .NET 9, and 11/15/2028 for .NET 10
(.NET 10 is "supported for three years as a long-term support release"). So this episode is a tour of what those two
releases (C# 12 and 13) added, written as **one library that compiles for `net8.0` and `net10.0`** (and `net9.0`, see
below) with the .NET 9 code behind `#if NET9_0_OR_GREATER`. The same tests run once per target. You see, on screen,
exactly what a retarget gives you and what the compiler says when you try to get it too early.

Everything is in the project requests domain of the earlier episodes (fictional data):

| Feature | Since | Where | What the test checks |
|---|---|---|---|
| Primary constructors on classes | C# 12 | [`CSharp12.cs`](src/ProjectRequests.Features/CSharp12.cs) `RequestReport`, `Ticket` | parameters used by every member; **no property is generated** for a class, one is for a record |
| Collection expressions + spread | C# 12 | `RequestReport.HighThenStandard`, `SampleData` | high priority first, nothing lost |
| Alias any type, default lambda parameters | C# 12 | `using Money = (decimal Amount, string Currency)`, `FormatAll` | tuple alias; default `"EUR"` used when omitted |
| `FrozenDictionary` | .NET 8 | [`Net8Library.cs`](src/ProjectRequests.Features/Net8Library.cs) `Departments` | case-insensitive lookup; `Add` through `IDictionary` throws |
| snake_case, `JsonStringEnumConverter<T>`, populate read-only members | .NET 8 | `Feed`, `FeedItem`, `Priority` | exact JSON; `Tags` ignored by default, appended with `Populate` |
| `SearchValues<char>`, `CompositeFormat`, `Random.GetItems` / `Shuffle` | .NET 8 | `SmallThings` | forbidden characters; format parsed once; sample stays in the pool |
| `CountBy`, `AggregateBy`, `Index` | .NET 9 | [`Net9Library.cs`](src/ProjectRequests.Features/Net9Library.cs) `Net9Linq` | **same answers as the `GroupBy` versions** (`LinqBefore`) |
| `params ReadOnlySpan<T>` / `params IEnumerable<T>` | C# 13 | `Net9Params` | works like `params T[]`; **0 bytes allocated** in a Release build |
| `System.Threading.Lock` | .NET 9 / C# 13 | `RequestNumbers` | 40,000 numbers from 8 threads: unique, no gaps; **typed as `object` it silently becomes `Monitor`** |
| `Guid.CreateVersion7` | .NET 9 | `RequestIds` | `Version == 7`; sorts by creation time (as text) |
| `Base64Url` | .NET 9 | `PageCursor` | round trip; no `+` `/` `=`; `++//` becomes `--__` |
| `Task.WhenEach` | .NET 9 | `Notifier` | results arrive in completion order, not list order |
| `OrderedDictionary<,>`, `ReadOnlySet<T>` | .NET 9 | `Workflow` | `Insert` keeps order; the set is a live, read-only view |
| `JsonSerializerOptions.Web`, `SearchValues<string>`, `TimeSpan.FromSeconds(int, int)` | .NET 9 | `Net9Misc` | camelCase out, any casing in; banned phrases; exact ticks |

| Other files | What it is |
|---|---|
| [`FeatureMatrix.cs`](src/ProjectRequests.Features/FeatureMatrix.cs) | `CompiledFor` and `Net9FeaturesCompiledIn`: which target this build is |
| [`src/ProjectRequests.Features.Tour/`](src/ProjectRequests.Features.Tour/) | The demo: one console app, `dotnet run -f net8.0` then `-f net10.0` |
| [`tests/ProjectRequests.Features.Tests/`](tests/ProjectRequests.Features.Tests/) | xUnit v3, multi-targeted (`net8.0;net10.0`): 53 test runs, 18 on .NET 8 and 35 on .NET 10 |
| [`deploy/net8-compile-errors.txt`](deploy/net8-compile-errors.txt) | Real compiler output for .NET 9 / C# 13 code built for `net8.0` |
| [`deploy/tour-net8.0.output.txt`](deploy/tour-net8.0.output.txt) · [`tour-net10.0.output.txt`](deploy/tour-net10.0.output.txt) | Real output of the tour on each runtime |
| [`deploy/lock-warning-cs9216.txt`](deploy/lock-warning-cs9216.txt) | The compiler's own warning for the `Lock`-as-`object` trap |

## Build, test, run

```bash
dotnet test -c Release        # MTP mode via global.json: total 53, failed 0 (net8.0: 18, net10.0: 35), ~20 s
dotnet test                   # Debug: 52 passed, 1 skipped (the allocation test refuses to run in Debug, see gotchas)
dotnet test -c Release -f net8.0     # only the .NET 8 test app (needs the .NET 8 runtime installed)

dotnet run --project src/ProjectRequests.Features.Tour -f net8.0      # .NET 9 section: "not compiled into this build"
dotnet run --project src/ProjectRequests.Features.Tour -f net10.0     # everything

dotnet build src/ProjectRequests.Features -p:IncludeNet9=true         # also compiles the net9.0 target
```

Tested with .NET SDK 10.0.115 and the .NET 8.0.34 and 10.0.15 runtimes, xUnit.net v3 4.0.3, on Linux. **The `net9.0`
target was compiled but not run**: the container has no .NET 9 runtime, so "works on .NET 9" is not claimed here;
the .NET 9 APIs ran on .NET 10, which includes them. The multi-target test run needs both runtimes on the recording
laptop (see demo.md). No Azure, no tenant, no network at run time.

## What we learned / gotchas

- **Syntax is stopped by the language version, APIs by the target framework, and you see them separately.** Built
  for `net8.0` (default C# 12): `'\e'` and `params ReadOnlySpan<int>` fail with **CS9202** ("Feature ... is not available
  in C# 12.0. Please use language version 13.0 or greater."); `CountBy`, `Guid.CreateVersion7` and `System.Threading.Lock`
  fail with **CS1061 / CS0117 / CS0234**. A syntax error stops the compiler before it reports the missing APIs, so
  fixing the first reveals the rest ([`deploy/net8-compile-errors.txt`](deploy/net8-compile-errors.txt)).
- **Raising `LangVersion` on an old target is not the fix.** With `<LangVersion>13.0</LangVersion>` on `net8.0`, the
  syntax-only C# 13 features (`\e`, `params ReadOnlySpan<int>`) compiled and ran here. Learn says plainly that using a
  language version newer than the one associated with the target framework isn't supported, and the library-dependent
  ones (`Lock`, `CountBy`) can't work anyway. Retarget, or multi-target with `#if NET9_0_OR_GREATER` (Learn documents
  the `<framework>_OR_GREATER` symbols: defined for the targeted version and all earlier ones).
- **A `Lock` typed as `object` is a `Monitor`.** Learn: the `lock` statement uses the new type only if the expression's
  type is precisely `System.Threading.Lock`; "no other code changes are needed", you change the type of the field. The
  trap is a field or parameter still declared `object`. Our test holds the *same* `Lock` instance inside
  `lock (Lock gate)` and inside `lock (object gate)` and reads `IsHeldByCurrentThread`: **true** and **false**. The
  compiler warns **CS9216** when it sees the conversion ([`deploy/lock-warning-cs9216.txt`](deploy/lock-warning-cs9216.txt));
  we suppress it in the one place we do it on purpose.
- **`params ReadOnlySpan<T>` only saves the array in a Release build.** Measured over 10,000 calls: Release, span 0
  bytes (array version 320,000, i.e. 32 B per call); **Debug, span 720,000 bytes (72 B per call)**, worse than the
  array. The test skips itself in Debug (`Assert.Skip`) and says why. Allocation claims are about the build you ship
  (the same point as episode 9: benchmark in Release).
- **A class primary-constructor parameter is not a property, and it is mutable.** Learn: the compiler generates public
  properties for primary-constructor parameters only in `record` types. `Ticket(int start)` can increment `start`
  inside `Next()`; there's no `start` to read from outside; `TicketRange(int Start)` as a record has `Start`.
- **System.Text.Json ignores read-only members by default.** `public List<string> Tags { get; } = ["imported"]` stays
  `["imported"]` when the JSON has tags. `PreferredObjectCreationHandling = JsonObjectCreationHandling.Populate`
  (.NET 8) fills it, by **appending** to what's already there: `["imported", "urgent", "finance"]`.
- **`TimeSpan.FromSeconds(101.832)` is one tick short** (1,018,319,999 ticks, "00:01:41.8319999"), on .NET 8 and 10
  alike, because 101.832 isn't exactly a `double`. The .NET 9 integer overload `FromSeconds(101, 832)` gives exactly
  1,018,320,000. Both are tests.
- **`Assert.Contains` is ambiguous for `ReadOnlySet<T>`** in xUnit v3 (`ISet<T>` and `IReadOnlySet<T>` overloads, CS0121);
  call `set.Contains(x)` instead.
- **`Random.GetItems` samples with replacement.** Asking for 20 items from a pool of 8 returns 20 items, with repeats.
- **`Base64Url` drops the padding and swaps two characters.** `[0xFB, 0xEF, 0xFF]` is `++//` in standard Base64 and
  `--__` in Base64Url (Learn: `+` becomes `-`, `/` becomes `_`); our cursor has no `=`, so it needs no URL escaping.
- **v7 GUIDs sort by time as text** (the timestamp comes first), which is what the test checks. Whether *your database*
  sorts them that way is a separate question we did not test here.
- **`dotnet test` runs one test app per target.** In MTP mode you get one run per framework (18 tests on .NET 8,
  35 on .NET 10: the .NET 9 tests are compiled out of the net8 build), which is also the proof that the `#if`s do what
  they claim. The SDK 10.0.115 built `net8.0` without any "out of support" warning, even though Learn's lifecycle page
  lists the end of support as 11/11/2026: don't count on the tooling to tell you.

## References
- [.NET and .NET Core support policy / lifecycle table (.NET 8, 9, 10 dates)](https://learn.microsoft.com/lifecycle/products/microsoft-net-and-net-core)
- [What's new in .NET 10 (LTS)](https://learn.microsoft.com/dotnet/core/whats-new/dotnet-10/overview)
- [What's new in .NET 9: libraries (LINQ `CountBy`/`AggregateBy`/`Index`, `Task.WhenEach`, `Guid.CreateVersion7`, `OrderedDictionary`, `Base64Url`, `ReadOnlySet`, `SearchValues<string>`, `params` spans, `TimeSpan`, `JsonSerializerOptions.Web`)](https://learn.microsoft.com/dotnet/core/whats-new/dotnet-9/libraries)
- [What's new in .NET 8: runtime (`FrozenDictionary`, `TimeProvider`, JSON naming policies, `JsonStringEnumConverter<T>`, populate read-only, `Random.GetItems`, `SearchValues`, `CompositeFormat`)](https://learn.microsoft.com/dotnet/core/whats-new/dotnet-8/runtime)
- [What's new in C# 12 (primary constructors, collection expressions, alias any type, lambda defaults)](https://learn.microsoft.com/dotnet/csharp/whats-new/csharp-12)
- [What's new in C# 13 (`params` collections, `lock` and `System.Threading.Lock`, `\e`)](https://learn.microsoft.com/dotnet/csharp/whats-new/csharp-13)
- [C# compiler message CS9216 (`Lock` converted to another type)](https://learn.microsoft.com/dotnet/csharp/language-reference/compiler-messages/lock-semantics)
- [`System.Threading.Lock`](https://learn.microsoft.com/dotnet/api/system.threading.lock) · [`Base64Url`](https://learn.microsoft.com/dotnet/api/system.buffers.text.base64url)
- [Configure C# language version (a newer `LangVersion` than the TFM isn't supported)](https://learn.microsoft.com/dotnet/csharp/language-reference/configure-language-version)
- [Target frameworks in SDK-style projects (`TargetFrameworks`, `NET9_0_OR_GREATER`)](https://learn.microsoft.com/dotnet/standard/frameworks)
- Blog: [.NET 8/9 Features — Complete Guide](https://www.devladlog.com/articles/dotnet/2026-05-27-net-89-features-complete-guide-2026/)
