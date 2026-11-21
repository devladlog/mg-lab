# Demo shot list — DEVLADLOG Power Apps #5, Custom connectors

The connector files were tested locally (`dotnet test`: 51 passed, 2 live tests passed against the real date.nager.at on
21 Nov 2026). Everything below **needs the lab tenant** and has not been run there: `pac connector create`, the wizard's
Test tab, the connector in Power Apps Studio and Power Automate.

## Lab environment
No VM and no Azure resource. The holiday source is the free public API `https://date.nager.at` (no key, no account).

| What | Notes | Cost |
|---|---|---|
| Lab **DEV** environment with episodes 1-3 (solution **Equipment Desk**, tables, the phone app with episode 3's Loans screen) | existing | existing |
| Recording user with **System Customizer** (or System Administrator) in DEV and a **Power Apps Premium** licence | premium already needed for Dataverse; the free plan only allows one custom connector and no sharing (Learn FAQ) | existing |
| `pac` CLI on the recording laptop (lab Windows host), signed in to DEV | `pac auth create --environment <DEV URL>`, device code **off camera** | free |
| Outbound HTTPS from Power Platform to `date.nager.at` | if the tenant has a **data policy**, an admin classifies Contoso Holidays (environment policy, by name) or `https://date.nager.at*` (tenant policy, host pattern) in the **same group as Dataverse**; otherwise the app is blocked | free |
| .NET 8 SDK on the laptop | only for the optional `dotnet test` cutaway | free |

All screens are recorded on the **lab Windows host**: terminal + browser on the lab tenant.

Things to confirm in the lab and report back (fix code/tests/README if they differ):
- `pac connector create` accepts the three files and puts the connector in **Equipment Desk** (`pac connector list` shows it).
- The **Code** tab shows custom code enabled for **GetDaysOff only** (from `scriptOperations`).
- The script compiles on the platform (an "internal server error" on create/update means it didn't; Learn FAQ).
- `Context.Request.RequestUri` is `https://date.nager.at/api/v3/DaysOff/PT?...` (the Test tab result proves it: a wrong
  path gives the "Unexpected path" 400).
- Studio accepts `ContosoHolidays.GetDaysOff(...)` inside a **named formula** in `App.Formulas`. If it refuses (behavior
  function / side effects), move `DaysOff` to `App.OnStart` with `Set(DaysOff, ...)`, keep `Holidays` as a named formula, and
  note it as a gotcha in README and script.yaml.
- Monitor shows **one** GetDaysOff request when the Loans screen loads (the claim in `app-screen`). If it shows one per row,
  re-record and change the narration.
- The `ForAll(DaysOff.days, ThisRecord.date)` result works with `d in Holidays` in Studio (it does in the open-source engine).

## Steps
1. Off camera: `pac auth create --environment <DEV URL>`; `pac org who` to confirm DEV.
2. Record the terminal (`definition-screen`, part 1), from `src/connector`:
   `pac connector create --api-definition-file apiDefinition.swagger.json --api-properties-file apiProperties.json --script-file script.csx --solution-unique-name EquipmentDesk`
   then `pac connector list`. Note the connector id off camera for `pac connector update`; don't commit it (it's a tenant identifier).
3. make.powerapps.com → Solutions → **Equipment Desk** → **Contoso Holidays** → Edit. Record the **Definition** tab (three
   actions, Get days off selected) and the **Code** tab (`definition-screen`, part 2).
4. **Test** tab → New connection (no credentials) → GetDaysOff: Country `PT`, From Year `2026`, Subdivision `PT-30` → Test
   operation. Scroll the response so `count: 15`, Madeira Day and the excluded Carnival/Azores Day are visible
   (`test-screen`). Repeat with Country `XX` for the 404 shot.
5. Open **Equipment Desk (phone)** in Studio → Data → Add data → **Contoso Holidays**. App → **Formulas**: replace with the
   block from `src/app/Src/App.pa.yaml` (only `OfficeCountry`, `OfficeSubdivision`, `DaysOff`, `Holidays` change). Save.
6. Advanced tools → **Monitor** → Play the **Open loans** screen. Record Studio + Monitor side by side (`app-screen`).
   Make sure at least one loan is overdue (if none is, lend CT-0043 with a due date in the past, e.g. 16 Nov 2026).
7. make.powerautomate.com → Create → Instant cloud flow (manual trigger) → add action → Custom → **Contoso Holidays** →
   **Get days off**. Open the Country drop-down; expand advanced options to show Subdivision (`flow-screen`). **Don't save**:
   discard the flow.
8. Optional terminal capture for `compile`/`gotcha`: `dotnet test ContosoHolidays.Tests -m:1` (51 passed) and
   `dotnet test --filter "FullyQualifiedName~gotcha|FullyQualifiedName~Compile"`.

## Screens to capture (match `screen` scenes in script.yaml)
| Scene | File | What must be on screen |
|---|---|---|
| `definition-screen` | `screens/connector-definition.jpg` | Terminal: `pac connector create` output with the new id, `pac connector list` with Contoso Holidays; portal Definition tab with Get days off / List public holidays / List countries; Code tab with code enabled for GetDaysOff |
| `test-screen` | `screens/connector-test.jpg` | Test tab, GetDaysOff PT / 2026 / PT-30 → **200**, `count: 15`, `2026-07-01 Madeira Day scope PT-30`, excluded `Carnival — Optional`, `Azores Day — Regional (PT-20)`; second shot XX → **404** with "The holiday source returned 404 for XX 2026: ..." |
| `app-screen` | `screens/app-monitor.jpg` | Studio: Data pane with Contoso Holidays, App.Formulas with DaysOff/Holidays, Open loans screen playing; Monitor with **one** `GetDaysOff` row (fromYear 2025, toYear 2027, status 200) |
| `flow-screen` | `screens/flow-dropdown.jpg` | Power Automate designer: Contoso Holidays → Get days off, Country drop-down open with country names, Subdivision under advanced options, no "List countries" action offered |

## Masking
- Environment name and URL, tenant name, connector id (GUID in the terminal), user names/avatars.
- The Test tab shows the connection name: mask it if it contains a user name.
- `pipeline/mask.js` in the browser; `series_label: "POWER APPS"` is set in `script.yaml`.

## Tear-down
1. Keep the connector and the app change: episode 6 builds on the same app. If you need to remove it: remove the data
   source from the app, then delete **Contoso Holidays** from the solution (Learn: deleting a connector deletes all its
   connections).
2. Make sure the unsaved test flow from step 7 was discarded (My flows shouldn't list it).
3. If an admin added a data policy rule just for this episode, leave a note for the lead session before removing it.
4. `pac auth clear` on the recording laptop if the profile was created only for this.
