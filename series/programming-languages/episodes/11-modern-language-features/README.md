# DEVLADLOG Code #11 - Modern language features: one job, four languages

Series: `programming-languages` (DEVLADLOG Code). Blog: <https://www.devladlog.com/articles/programming-languages/2025-07-09-modern-language-features-complete-guide-2025/>

The same small job, a **request digest**, written four times with the recent features of each language, and a
conformance script that proves all four print the *same* 23 lines. The scenario is the fictional Contoso project
request intake of the earlier episodes: budgets of `>= 50,000` EUR are High priority, `>= 250,000` goes to Finance
and then the Board, zero or negative budgets are rejected. Input: `samples/requests.json` (13 requests). Output:
`expected/digest.txt` (totals, rejections, count per route, total per department, largest three, review batches of
four).

Earlier episodes covered C# 14 itself (02), TypeScript strictness (01), PowerShell modules (07), Python on Azure (08)
and Node patterns (09). This one does not repeat them: it shows the *other* recent features (type stripping, file-based
apps, `CountBy`/`AggregateBy`, strict `System.Text.Json`, PEP 695, `typing.ReadOnly`, PowerShell 7 operators) and what
bites when you move between languages.

## What is here
| Path | What |
|---|---|
| `samples/requests.json`, `expected/digest.txt` | The shared input and the golden output every implementation must print |
| `src/ts/digest.ts`, `types.ts`, `main.ts` | TypeScript run **directly by Node** (type stripping): `Object.groupBy`, `Map.groupBy`, iterator helpers, `toSorted`, const object instead of `enum`, `unknown` + type guard at the boundary |
| `tsconfig.json` | `erasableSyntaxOnly`, `verbatimModuleSyntax`, `allowImportingTsExtensions`, `noUncheckedIndexedAccess`, `noEmit` |
| `src/cs/digest.cs` | C# **file-based app** (`#:project`, `#:property PublishAot=false`, list pattern on `args`) |
| `src/cs/Contoso.Digest/Digest.cs` | Library: collection expressions, `CountBy`, `AggregateBy`, `Chunk`, relational patterns, strict `System.Text.Json` (`RespectNullableAnnotations`, `RespectRequiredConstructorParameters`, `AllowDuplicateProperties = false`) |
| `src/py/digest.py` | Python 3.13: `type` alias and generic function (PEP 695), `match` on dataclasses, `TypedDict` with `ReadOnly`, `itertools.batched(strict=)`, `warnings.deprecated`, `StrEnum`, `Decimal` JSON parsing |
| `src/ps/Digest.psm1`, `digest.ps1` | PowerShell 7.6: `enum` and `class`, ternary, `?.` / `?[]` / `??`, strict mode |
| `tests/ts`, `tests/cs`, `tests/py`, `tests/ps` | 11 + 16 + 16 + 17 = 60 tests (node:test, xUnit, pytest, Pester) |
| `demo/conformance.ps1` | Runs the four implementations and compares each with `expected/digest.txt` |
| `demo/gotchas.ps1` + `demo/ts`, `demo/cs`, `demo/py` | The three gotchas below, each as a runnable file |
| `demo/expected-output.txt` | Real captured output of the scripts and test runs |
| `script.yaml`, `demo.md` | Video script (14 scenes, ~890 narration words) and shot list |

## Run it
Needs Node 22.18+ (type stripping unflagged), .NET SDK 10, Python 3.13, PowerShell 7.4+ (tested on 7.6). Nothing here
needs a cloud tenant or any secret.

```bash
npm install --no-audit --no-fund                  # typescript 7 + @types/node, only for the type check
pwsh demo/conformance.ps1                         # 4 x [ok], exit code 0
pwsh demo/gotchas.ps1                             # the three gotchas

npm test && npx tsc -p tsconfig.json              # 11 tests pass, type check silent
dotnet test ModernFeatures.slnx -m:1              # Passed: 16
python -m pytest -q && ruff check . && mypy src/py tests/py   # 16 passed, ruff and mypy --strict clean
pwsh -c "Invoke-Pester -Path tests/ps"            # Tests Passed: 17

node src/ts/main.ts samples/requests.json
dotnet run src/cs/digest.cs -- samples/requests.json
python src/py/digest.py samples/requests.json
pwsh src/ps/digest.ps1 samples/requests.json
```

Tested here (Ubuntu container) with Node 22.23.5, TypeScript 7.0.2, .NET SDK 10.0.115, Python 3.13.18 (pytest 9.1,
ruff 0.17, mypy 2.3), PowerShell 7.6.0 and Pester 6.2.0. Windows was not available in the container: line endings
are normalised in every comparison, `.gitattributes` pins the golden files to LF, and `demo.md` lists what to check on
the laptop.

## What we learned / gotchas
- **Node runs `.ts` files, but only the erasable subset.** `node src/ts/main.ts` works without a flag from Node
  22.18 (the release notes for 22.18.0 turn type stripping on by default and still call it experimental; the 22.x
  docs now mark it "Stability: 1.2 - Release candidate"). It is stable from Node 24.12.0 and 25.2.0, and the video
  was recorded on Node 24.16.0, where it prints no warning. An
  `enum` fails with `ERR_UNSUPPORTED_TYPESCRIPT_SYNTAX`; the same file under `erasableSyntaxOnly` fails the compiler
  with TS1294. Use a `const` object plus a union type. Imports must name the real file (`./digest.ts`), which needs
  `allowImportingTsExtensions`. Node does no type checking, `tsc --noEmit` stays in CI.
- **File-based apps target native AOT by default, and then JSON reflection is off.** `dotnet run digest.cs` with
  `System.Text.Json` and a record fails with `Reflection-based serialization has been disabled for this application`.
  Learn: "File-based apps enable native AOT publishing by default... Disable this feature by adding
  `#:property PublishAot=false`". Our `digest.cs` has the directive; `demo/cs/no-aot-flag.cs` is the same file without
  it. Alternative: use the source generator.
- **`#:include` is not available on every SDK.** Learn: it needs .NET SDK 10.0.300 or later, we have 10.0.115, so the
  app uses `#:project` to a small library (and the xUnit project tests the library, not the file).
- **The same expression gives a different number per language.** `0.29 * 100` is `28.999999999999996`. JavaScript
  (`Math.trunc`), C# (`(long)`) and Python (`int()`) truncate to 28; a PowerShell `[long]` cast rounds to 29. All four
  implementations avoid the question: C# and Python use `decimal`/`Decimal`, TypeScript uses `Math.round`, PowerShell
  uses `[decimal]` and `Math.Round`. Python's `json` needs `parse_float=Decimal` (and `parse_int=Decimal` to treat
  whole numbers the same way) or `49999.99` arrives as a float. Tests pin each of these.
- **PowerShell: `@($null).Count` is 1.** The first version of `New-Digest` counted `@($byRoute[$key]).Count` and
  reported one Board request when there were none (the sample has all three routes filled, only a unit test with one
  small request caught it). `${group}?.Count ?? 0` is the fix.
- **PowerShell: strict mode and missing JSON properties.** With `Set-StrictMode -Version Latest`, `$item.budget` on an
  object without that property throws "The property 'budget' cannot be found". Look the property up with
  `$item.PSObject.Properties[$name]` if you want your own error message.
- **PowerShell: `-f` inside a method call.** `$lines.Add('{0}' -f $a, $b)` passes *two* arguments to `Add`; wrap the
  format expression in its own parentheses. Also: the decimal suffix is `d` (`100d`), not `m`; and `?[]` / `?.`
  need braces around the variable name (`${group}?.Count`) because `?` is legal in variable names (Learn).
- **System.Text.Json is lenient unless you ask.** Constructor parameters are optional and `null` is accepted for a
  `string` by default; `RespectRequiredConstructorParameters` and `RespectNullableAnnotations` (.NET 9) change that
  and Learn recommends both for new applications. `AllowDuplicateProperties = false` is new in .NET 10. There is also
  a `JsonSerializerOptions.Strict` preset (it additionally rejects unmapped properties); we start from `Web` for the
  camelCase names. Three tests pin missing, null and duplicate.
- **Python: `typing.ReadOnly` is for the type checker only.** Nothing stops `raw["code"] = "x"` at run time;
  `mypy --strict` does. `warnings.deprecated` does warn at run time (our test uses `pytest.warns`), and
  `filterwarnings = ["error"]` in `pyproject.toml` makes any stray warning fail the suite. Ruff's B911 asks for an
  explicit `strict=` on `itertools.batched`.
- **Intentional non-features.** Group sorting is by ordinal on upper-case ASCII in all four languages. Non-ASCII
  department names would sort differently per language (`localeCompare`, `StringComparer.Ordinal`, `Sort-Object`);
  we did not test that.

## References
- [Node.js 22.18.0 release notes (type stripping on by default)](https://nodejs.org/en/blog/release/v22.18.0),
  [24.12.0 release notes (type stripping marked stable)](https://nodejs.org/en/blog/release/v24.12.0) and the
  [Modules: TypeScript documentation (stability index and history)](https://nodejs.org/api/typescript.html)
- [TypeScript `erasableSyntaxOnly`](https://www.typescriptlang.org/tsconfig/#erasableSyntaxOnly)
- [File-based apps (directives, native AOT default, `dotnet run file.cs`)](https://learn.microsoft.com/dotnet/core/sdk/file-based-apps)
- [Tutorial: Build file-based C# programs](https://learn.microsoft.com/dotnet/csharp/fundamentals/tutorials/file-based-programs)
- [What's new in the SDK and tooling for .NET 10 (file-based apps)](https://learn.microsoft.com/dotnet/core/whats-new/dotnet-10/sdk#file-based-apps-enhancements)
- [What's new in .NET libraries for .NET 9 (`CountBy`, `AggregateBy`, nullable annotations)](https://learn.microsoft.com/dotnet/core/whats-new/dotnet-9/libraries)
- [`Enumerable.AggregateBy`](https://learn.microsoft.com/dotnet/api/system.linq.enumerable.aggregateby) and [`CountBy`](https://learn.microsoft.com/dotnet/api/system.linq.enumerable.countby)
- [`System.Text.Json`: respect nullable annotations](https://learn.microsoft.com/dotnet/standard/serialization/system-text-json/nullable-annotations) and [required properties](https://learn.microsoft.com/dotnet/standard/serialization/system-text-json/required-properties)
- [`JsonSerializerOptions.AllowDuplicateProperties`](https://learn.microsoft.com/dotnet/api/system.text.json.jsonserializeroptions.allowduplicateproperties)
- [PowerShell support lifecycle (7.6 is LTS, built on .NET 10)](https://learn.microsoft.com/powershell/scripting/install/powershell-support-lifecycle)
- [What's new in PowerShell 7.6](https://learn.microsoft.com/powershell/scripting/whats-new/what-s-new-in-powershell-76)
- [about_Operators (ternary, `??`, `?.`, `?[]`)](https://learn.microsoft.com/powershell/module/microsoft.powershell.core/about/about_operators) and [about_Pipeline_Chain_Operators](https://learn.microsoft.com/powershell/module/microsoft.powershell.core/about/about_pipeline_chain_operators)
- [What's New In Python 3.12](https://docs.python.org/3.13/whatsnew/3.12.html) (PEP 695, `itertools.batched`) and [3.13](https://docs.python.org/3.13/whatsnew/3.13.html) (`ReadOnly`, `warnings.deprecated`, `batched(strict=)`)
- Blog: [Modern Language Features - Complete Guide](https://www.devladlog.com/articles/programming-languages/2025-07-09-modern-language-features-complete-guide-2025/)
