# DEVLADLOG Power Apps #5 — Custom connectors: a holiday API, an OpenAPI file and a little C#

Episode 3 counted **working days** for overdue loans with a hard-coded `Holidays` list in `App.Formulas`, and said so:
"a demo shortcut". This episode replaces it with a **custom connector**. **Contoso Holidays** wraps the free, public
[Nager.Date](https://date.nager.at) API (no key, no Azure resource) and adds one operation of its own, **GetDaysOff**,
whose **custom code** (C# in `script.csx`) turns "every holiday the source knows" into "the days this office is closed":

- the source returns 17 Portuguese holidays for 2026; only **13** are days off in Lisbon. **Carnival** is listed with type
  `Optional` (offices open), **Azores Day** applies to `PT-20` only, **Madeira Day** and **St. Stephen's Day** to `PT-30` only;
- one call covers up to five years (the app asks for last year to next year: three requests to the source, one answer);
- bad input is a `400` with a readable message *before* anything is sent; source errors keep their status and explanation.

The connector is built **from files**, not clicked together: an OpenAPI 2.0 definition, an API properties file and the
script, created in the episode 1 solution with `pac connector create`. The canvas app from episodes 2 and 3 then gets
its holidays from `ContosoHolidays.GetDaysOff(...)` and its working-day functions stay exactly as they were.

| Path | What it is |
|---|---|
| [`src/connector/apiDefinition.swagger.json`](src/connector/apiDefinition.swagger.json) | OpenAPI **2.0**: `GetDaysOff` (important), `ListPublicHolidays` (advanced, raw), `ListCountries` (internal, feeds the Country drop-down via `x-ms-dynamic-values`) |
| [`src/connector/apiProperties.json`](src/connector/apiProperties.json) | No authentication (`connectionParameters: {}`), `scriptOperations: ["GetDaysOff"]` so the two passthrough operations skip the script |
| [`src/connector/script.csx`](src/connector/script.csx) | Custom code: parse and validate, call the source once per year with `Context.SendAsync`, classify, merge same-day holidays, sort |
| [`src/connector/settings.json`](src/connector/settings.json) | Argument file in the format `pac connector init` generates |
| [`src/app/Src/App.pa.yaml`](src/app/Src/App.pa.yaml) | Episode 3's `App.Formulas` with `Holidays` now coming from the connector (`OfficeCountry`, `OfficeSubdivision`, `DaysOff`) |
| [`tests/ContosoHolidays.Tests`](tests/ContosoHolidays.Tests) | 51 xUnit tests (+2 live tests, skipped by default) |
| [`tests/ContosoHolidays.Tests/ScriptBase.cs`](tests/ContosoHolidays.Tests/ScriptBase.cs) | `ScriptBase` and `IScriptContext` exactly as Learn defines them "for local testing and compilation" |
| [`tests/ContosoHolidays.Tests/ScriptCompileTests.cs`](tests/ContosoHolidays.Tests/ScriptCompileTests.cs) | Roslyn compiles `script.csx` for **.NET Standard 2.0**, with only Learn's supported namespaces and C# 7.3 |
| [`tests/ContosoHolidays.Tests/PowerFxTests.cs`](tests/ContosoHolidays.Tests/PowerFxTests.cs) | The open-source **Power Fx connector library** turns the definition into `ContosoHolidays.*` functions and runs the app's formulas |
| [`tests/ContosoHolidays.Tests/fixtures`](tests/ContosoHolidays.Tests/fixtures) | Responses recorded from the real API (PT 2025-2027, country list), so tests don't need the internet |

## Run the tests (no tenant needed)

```bash
cd tests
dotnet test ContosoHolidays.Tests -m:1
# Passed!  - Failed: 0, Passed: 51, Skipped: 2, Total: 53 (.NET 8, Microsoft.PowerFx.Connectors 1.8.1, Roslyn 4.11)

LIVE_HOLIDAYS=1 dotnet test ContosoHolidays.Tests -m:1 --filter Category=Live
# Passed!  - Failed: 0, Passed: 2, Skipped: 0, Total: 2   (the same script against the real date.nager.at, Nov 2026)
```

What the four groups prove:
- **ScriptTests** (28): the script run the way the platform runs it (`new Script()`, context, `ExecuteAsync`) against the
  recorded source: 13 days off for Lisbon, 15 for Madeira, Carnival excluded as `Optional`, three years = three source
  requests in order, the source address taken from the incoming URL (point the host at your own API and it follows),
  every validation error (no request sent), 404 and 503 from the source, a failure in year two fails the whole call,
  same-day merge, base64 operation ids.
- **DefinitionTests** (12): a valid OpenAPI 2.0 document (Microsoft.OpenApi reader, no errors), under 1 MB, https only,
  Learn's coding standards (PascalCase ids, summary differs from description, descriptions end with a period, a `200` with
  a schema, a title on every parameter), valid `x-ms-visibility`, the drop-down wiring, and a **contract test**: what the
  script returns has exactly the fields and types the `DaysOff` schema declares.
- **ScriptCompileTests** (5): the strict compile, plus four negative cases that prove the check catches a .NET 6 API, a
  .NET Core-only API, a C# 8 switch expression and the `Formatting` ambiguity.
- **PowerFxTests** (6): makers see `GetDaysOff` (2 required, 2 optional parameters) and `ListPublicHolidays` but not the
  internal `ListCountries`; the `DaysOff` named formula from `App.pa.yaml` is **one** connector call for 2025-2027; episode
  3's `WorkingDaysBetween` gives 6 working days from 23 Dec 2026 to 4 Jan 2027; a Madeira office differs on 26 Dec 2025;
  the raw list would make Carnival a day off; an unknown country is an error value, not an empty calendar.

What they **don't** prove: the platform's exact request (we follow Learn: host + basePath + path, the script sees it in
`Context.Request`), that Power Apps Studio accepts `ContosoHolidays.GetDaysOff` inside a **named formula** (the open-source
engine does), DLP, sharing, or throttling. That's the lab run in [`demo.md`](demo.md).

## Create it in the lab (needs tenant)

```bash
pac auth create --environment <DEV environment URL>          # device code, off camera
cd src/connector
pac connector create --api-definition-file apiDefinition.swagger.json --api-properties-file apiProperties.json \
                     --script-file script.csx --solution-unique-name EquipmentDesk
pac connector list                                            # Learn: only solution-aware connectors are listed
# after a change:
pac connector update --connector-id <id> --api-definition-file apiDefinition.swagger.json \
                     --api-properties-file apiProperties.json --script-file script.csx
```

Then in the canvas app: **Data → Add data → Contoso Holidays** (creates the connection; no sign-in, the API is public),
and replace `App.Formulas` with the block in [`src/app/Src/App.pa.yaml`](src/app/Src/App.pa.yaml). Steps in [`demo.md`](demo.md).
This has **not yet run against the lab tenant**.

## What we learned / gotchas

- **A holiday list is not a list of days off.** The source returns 17 rows for Portugal 2026. `Carnival` is a real row with
  `global: true` but `types: ["Optional"]`; Azores Day, Madeira Day and St. Stephen's Day are regional (`counties`). Feeding
  the raw list into episode 3's `IsWorkingDay` makes Tuesday 17 February a holiday (test
  `The_gotcha_using_the_raw_list_makes_Carnival_a_day_off`). The filter lives in the connector, so every app and flow
  gets the same answer.
- **`Formatting` is ambiguous in connector code.** Learn's supported namespaces include both `Newtonsoft.Json` and `System.Xml`,
  and both have a `Formatting` type. With all of them as usings, `JObject.ToString(Formatting.None)` doesn't compile (CS0104),
  and Learn's FAQ says a compile failure shows up only as an "internal server error" on update. We don't know whether the
  platform imports every namespace; we qualify `Newtonsoft.Json.Formatting` and the compile test pins it.
- **Test the compile the strict way.** Learn: the supported version is **.NET Standard 2.0**. The tests compile for .NET 8 too,
  which accepts things the platform won't (`Math.Clamp`, `DateOnly`). `ScriptCompileTests` uses the .NET Standard 2.0 reference
  assemblies. `System.Web.HttpUtility` *is* in .NET Standard 2.0 (we first assumed it wasn't), so the script uses
  `HttpUtility.ParseQueryString`.
- **Base64 operation ids.** Learn (known issues): in some regions `Context.OperationId` arrives base64-encoded, and the sample
  decodes whenever `Convert.FromBase64String` succeeds. But `ListRows` or `Test` are valid base64 too and would decode to
  garbage. `DecodeOperationId` only accepts a decoded value that looks like an operation id.
- **`scriptOperations` limits the script.** Learn (paconn CLI): an empty list means *all* operations run through the script.
  We list only `GetDaysOff`; the passthrough operations go straight to the API.
- **`x-ms-dynamic-values` without `value-collection`.** Learn: if it isn't specified, the response is evaluated as an array, which
  is exactly what `/AvailableCountries` returns. No script needed for the drop-down. `ListCountries` is `internal`, so makers
  don't see it as an action (the Power Fx connector library hides it too).
- **`Table.Column` is deprecated in Power Fx.** Our first `Holidays = DaysOff.days.date` failed in the open-source engine with
  "Deprecated use of '.'. Please use the 'ShowColumns' function instead." We use `ForAll(DaysOff.days, ThisRecord.date)`.
- **`format: date` arrives as a Date.** The Power Fx connector library maps `"format": "date"` strings to Power Fx `Date`
  values, so `d in Holidays` compares dates, not text.
- **Limits** (Learn, custom connector FAQ and custom code): OpenAPI **2.0 only** (no 3.0), definition **under 1 MB**, one script
  per connector, script **under 1 MB** and done within **2 minutes**, no custom code through the on-premises data gateway,
  10,000 requests per minute per connection (Power Apps/Power Automate). Only ASCII in header names and values.
- **Governance.** Learn: by default other users can't use your custom connector; sharing an app that uses it shares it
  indirectly. Environment data policies classify custom connectors by name; unclassified ones go to the **default group**
  (Non-Business unless an admin changed it), so a policy that puts Dataverse in Business would block this app until an admin
  classifies Contoso Holidays. Tenant policies classify by **host URL pattern** (`https://date.nager.at*`).
- **Where it's created.** Learn: the **Data → Custom connectors** entry is no longer on the left pane; create connectors inside an
  unmanaged solution (we use `--solution-unique-name EquipmentDesk`). `pac connector list` only shows solution-aware ones.
- **Licensing.** The app already needs premium licences because it uses Dataverse (Learn: licensing FAQ, Dataverse is a premium
  capability). The free plan allows one custom connector and no sharing (Learn FAQ); a Power Apps per user plan allows 50.
- **A free public API has no SLA.** Nager.Date is fine for a demo and for learning; for production point the same definition
  at your HR system's API (the script takes the address from the request, test
  `The_source_address_comes_from_the_incoming_request_not_from_the_code`).

## References
- [Custom connectors overview](https://learn.microsoft.com/connectors/custom-connectors/)
- [Create a custom connector from an OpenAPI definition (OpenAPI 2.0, under 1 MB)](https://learn.microsoft.com/connectors/custom-connectors/define-openapi-definition)
- [Create a custom connector from scratch (create in a solution, Code step)](https://learn.microsoft.com/connectors/custom-connectors/define-blank)
- [Use custom code in a custom connector (ScriptBase, supported namespaces, limits, base64 OperationId)](https://learn.microsoft.com/connectors/custom-connectors/write-code)
- [Extend an OpenAPI definition (x-ms-summary, x-ms-visibility, x-ms-dynamic-values)](https://learn.microsoft.com/connectors/custom-connectors/openapi-extensions)
- [Follow coding standards for custom connectors](https://learn.microsoft.com/connectors/custom-connectors/coding-standards)
- [Custom connector FAQ (limits, OpenAPI 3.0, authentication types)](https://learn.microsoft.com/connectors/custom-connectors/faq)
- [Create a custom connector with the CLI (apiProperties.json, scriptOperations)](https://learn.microsoft.com/connectors/custom-connectors/paconn-cli)
- [pac connector (create, update, list, init)](https://learn.microsoft.com/power-platform/developer/cli/reference/connector)
- [Use a custom connector from a Power Apps app](https://learn.microsoft.com/connectors/custom-connectors/use-custom-connector-powerapps)
- [Share a custom connector in your organization](https://learn.microsoft.com/connectors/custom-connectors/share)
- [Data policies for custom connectors](https://learn.microsoft.com/power-platform/admin/dlp-custom-connector-parity)
- [Connector classification (default group)](https://learn.microsoft.com/power-platform/admin/dlp-connector-classification)
- [App object: Formulas (named formulas)](https://learn.microsoft.com/power-platform/power-fx/reference/object-app)
- [Power Apps licensing FAQs](https://learn.microsoft.com/power-platform/admin/powerapps-licensing-faq)
- [Microsoft.PowerFx.Connectors API reference](https://learn.microsoft.com/dotnet/api/microsoft.powerfx.connectors)
- Holiday source: [Nager.Date public API](https://date.nager.at) (free, no API key; `GET /api/v3/PublicHolidays/{year}/{countryCode}`)
- Blog: [Custom Connectors — Complete Guide](https://www.devladlog.com/articles/powerapps/2026-02-21-custom-connectors-complete-guide-2026/)
