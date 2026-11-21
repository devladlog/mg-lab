# DEVLADLOG Dynamics 365 #8 — Dynamics 365 Customer Service

The support side of the story. Contoso Retail, the account that came out of [episode 7](../07-dynamics-365-sales/)'s
lead, now raises **cases**. Customer Service Hub, queues and SLAs do the day-to-day work; **casekit**, a small Python
tool, does the parts around them:

- **doctor**: reads `$metadata` and says whether the Customer Service tables are there (case, case resolution, SLA,
  SLA KPI instance, entitlement, queue, queue item), how `CloseIncident` is defined and which **SLA KPI lookups** the
  case table has in this environment
- **seed**: the demo cases (fictional, `[MGL demo]` prefix, customer *Contoso Retail*), created only when missing,
  dry run by default
- **triage**: open cases against the team's own targets in [`service.json`](service.json): no first response in time
  (C002, error), resolve target exceeded (C001, error), 80% of the resolve target used (C003, warning), escalated
  (C004, info); exit code 1 on errors so a schedule can fail
- **sla**: what the platform's SLA engine says about each open case: the first-response and resolve KPI instances
  (status, warning time, failure time)
- **resolve**: the `CloseIncident` action with a case resolution (Problem Solved or Information Provided), dry run
  by default, read back afterwards

`triage` is deliberately *not* the SLA engine: wall-clock hours from `service.json` (fictional targets), no business-hours
calendar, no pause on hold. It answers "which cases would my own rule call late" from three columns, anywhere. `sla`
shows what the real engine decided. Showing both side by side is the point.

| Path | What it is |
|---|---|
| [`service.json`](service.json) | Demo prefix and account, first-response and resolve targets per priority (hours), due-soon ratio |
| [`src/casekit/cases.py`](src/casekit/cases.py) | Open-case fetch (formatted values), triage rules C001–C004, summary, case body, seed, `CloseIncident` body and resolve |
| [`src/casekit/sla.py`](src/casekit/sla.py) | `$expand` of the case's two SLA KPI lookups, status labels, report |
| [`src/casekit/doctor.py`](src/casekit/doctor.py) | `$metadata` (CSDL) parser: tables, `CloseIncident`, KPI lookups on the case |
| [`src/casekit/cli.py`](src/casekit/cli.py), [`webapi.py`](src/casekit/webapi.py), [`auth.py`](src/casekit/auth.py) | CLI; Web API client (429 + Retry-After, formatted-value annotations); MSAL token provider, as in episodes 1–7 |
| [`sample/open-cases.json`](sample/open-cases.json) | 10 fictional open cases in Web API shape, for the offline `triage` |
| [`sample/demo-cases.json`](sample/demo-cases.json) | The 5 cases `seed` creates |
| [`tests/`](tests/) | 18 pytest tests; the Web API is a recording stub (tests only: the demo runs against the real environment) |

## Run and test (no tenant)

```bash
cd series/dynamics-365/episodes/08-dynamics-365-customer-service
python3 -m pip install --user -r requirements.txt
python3 -m pytest -q tests                                                             # 18 passed
cd src
python3 -m casekit triage --from-json ../sample/open-cases.json --now 2027-01-15T12:00:00Z    # exit 1: 4 errors
```
```
10 open case(s)

priority  open  oldest h  no 1st reply
High         3        26             1
...
ERROR   C001  CAS-01005-E4F5A6 Payment gateway timeouts: open 26 h, resolve target 24 h
ERROR   C002  CAS-01001-A1B2C3 Portal login fails for store managers: no first response after 4.5 h (target 4 h, High priority)
WARNING C003  CAS-01002-D4E5F6 Report totals lag by one day: 83% of the 72 h resolve target used
INFO    C004  CAS-01005-E4F5A6 Payment gateway timeouts: escalated
4 error(s), 1 warning(s)
```

## Against an environment (needs tenant)

Prerequisites: an environment with Customer Service (the lab's *Sales trial* environment, see [demo.md](demo.md)),
the account *Contoso Retail* from episode 7, an identity that can read and write cases (Customer Service
Representative or System Administrator).

```bash
export DATAVERSE_URL=https://<org>.crm4.dynamics.com
cd src
python3 -m casekit doctor
python3 -m casekit seed            # dry run
python3 -m casekit seed --apply
python3 -m casekit triage
python3 -m casekit sla
python3 -m casekit resolve <case id> --subject "Reset done" --description "Passwords reset, sign-in tested" --apply
```

## What we learned / gotchas

- **The case's date columns are not the SLA.** Learn's troubleshooting page: in Unified Interface SLAs, *First
  Response By* and *Resolve By* aren't filled by default (a case can have several KPIs per KPI field); it suggests a
  workflow or plug-in if you want them. So `sla` reads the **SLA KPI instance** the case points to instead.
- **No default SLA, no SLA.** Learn (*SLA isn't getting applied to a case*): SLAs aren't applied to a case if no
  default SLA is set (Service terms → Service-level agreements → *Set As Default*); a null *Applicable From* on the KPI
  also stops it. A case showing "no SLA applied" in `sla` is usually this.
- **Pausing creates a new KPI instance.** Learn (*Configure service-level agreements*): when an SLA KPI instance is
  paused and resumed, the instance is canceled and a new one is created, so one case can have several instances over
  its life; the case's KPI lookup points at the current one.
- **`CloseIncident` needs Customer Service** (Learn, `CloseIncidentRequest`: "This message requires Dynamics 365
  Customer Service"); `doctor` reports it missing otherwise. The resolution is an activity (`incidentresolution`) with
  a subject and the case; Status 5 *Problem Solved* sets the case to Resolved (statecode 1), 1000 *Information Provided*
  is the other resolved status. The caller needs privileges on the case table, activities and queue items (Learn).
- **`ticketnumber` can't be set**: Learn says the case number cannot be modified, so `seed` finds its cases by title.
- **Titles are limited to 200 characters** (Case table reference); `case_body` checks before sending.
- **Where the app comes from.** Learn (*Availability of Customer Service Hub*): Customer Service Hub is installed
  automatically in environments that have customer engagement apps such as Sales Hub, and users need the *Customer
  service app access* security role. Dynamics 365 apps can only be installed in an environment created with *Enable
  Dynamics 365 apps*; a Dataverse-only environment like `DEV` can't host them (Learn, *Manage Dynamics 365 apps*).
- **Not verified on Learn** (so the tool checks instead of assuming): the names of the case's SLA KPI lookups
  (`firstresponsebykpiid`, `resolvebykpiid`, from the SDK column names) and therefore the `$expand` in `sla`; the Web API
  reference page for `CloseIncident` couldn't be fetched while building, so the action's parameter names and the
  `@odata.type` of the resolution come from the SDK message class. `casekit doctor` lists both from the real
  environment ([demo.md](demo.md) step 4); if it differs, the code and tests are fixed from its output.

## References
- [CloseIncidentRequest](https://learn.microsoft.com/dotnet/api/microsoft.crm.sdk.messages.closeincidentrequest) (requires Customer Service; resolution subject + incidentid; status 5; required privileges; "for the Web API use the CloseIncident action")
- [Case (Incident) table reference](https://learn.microsoft.com/dynamics365/developer/reference/entities/incident) (priority, origin, type, state/status choices, customerid targets, title 200, ticketnumber read-only, SLA status columns)
- [Case Resolution table reference](https://learn.microsoft.com/dynamics365/developer/reference/entities/incidentresolution)
- [SLA KPI Instance table reference](https://learn.microsoft.com/power-apps/developer/data-platform/reference/entities/slakpiinstance) (status choices, warning/failure time)
- [Create enhanced SLAs](https://learn.microsoft.com/dynamics365/customer-service/administer/create-enhanced-sla) (KPI lookups on the case refer to the SLA KPI instance table) and [Configure service-level agreements](https://learn.microsoft.com/dynamics365/customer-service/administer/define-service-level-agreements) (Service terms, SLA KPIs, pause creates a new instance)
- [SLA isn't getting applied to a case](https://learn.microsoft.com/troubleshoot/dynamics-365/customer-service/service-level-agreements/sla-not-getting-applied) and [First Response By / Resolve By aren't populating](https://learn.microsoft.com/troubleshoot/dynamics-365/customer-service/service-level-agreements/sla-firstresponseby-resolveby-not-populating-uci)
- [Availability of Customer Service Hub](https://learn.microsoft.com/dynamics365/customer-service/implement/availability-customer-service-hub), [Manage Dynamics 365 apps](https://learn.microsoft.com/power-platform/admin/manage-apps), [About trial environments](https://learn.microsoft.com/power-platform/admin/trial-environments)
- Blog: [Dynamics 365 Customer Service — Complete Guide](https://www.devladlog.com/articles/dynamics-365/2025-10-12-dynamics-365-customer-service-complete-guide-2025/)
