# DEVLADLOG Dynamics 365 #7 — Dynamics 365 Sales

The sales side of the consultancy from episodes 1–6: a lead comes in, becomes an account, a contact and an
opportunity, is worked through a pipeline, and is closed as won. The designer and the Sales Hub app do all of that.
This episode shows what the app doesn't give you and **salesctl**, a small Python tool, does:

- **doctor**: reads `$metadata` and says whether the Sales tables and the three actions we call are in the
  environment, how each action is bound and which parameters it takes. Nothing about the actions is assumed
- **qualify**: the `QualifyLead` action (account + contact + opportunity, each switchable), dry run by default,
  refuses a lead that isn't open and verifies the result on the lead afterwards
- **close**: `WinOpportunity` / `LoseOpportunity` with the OpportunityClose row (actual revenue, date, description,
  competitor), dry run by default, verified afterwards (state, status reason, forecast category)
- **pipeline**: open opportunities by estimated close month and by forecast category: count, value, weighted value
- **hygiene**: the rules that make a pipeline report lie (past or missing close date, no revenue, no probability,
  untouched for 30 days, a large deal closing within 30 days that is still *Pipeline*); exit code 1 for a scheduled check
- **leads**: open leads by e-mail or topic, to find the id to qualify

The fictional deals are the consultancy's: *Fabrikam – project portal rollout* is the win that, in the story, becomes
a **Project Request** in `DEV` (episodes 1–6). No code connects the two environments here; the Sales trial environment
and `DEV` are separate Dataverse environments.

| Path | What it is |
|---|---|
| [`sales.json`](sales.json) | App name, stale-days (30), large-deal threshold (50,000, the same figure as episodes 3–5), soon-days (30), currency |
| [`src/salesctl/pipeline.py`](src/salesctl/pipeline.py) | Open-opportunity query (`statecode eq 0`, formatted values), weighted value, summary buckets, hygiene rules H001–H006 |
| [`src/salesctl/lead.py`](src/salesctl/lead.py) | Find open leads; `QualifyLead` (bound to the lead) with state check, dry run and read-back |
| [`src/salesctl/close.py`](src/salesctl/close.py) | `WinOpportunity` / `LoseOpportunity` body (`OpportunityClose` with `opportunityid@odata.bind`), status reason rules, read-back |
| [`src/salesctl/doctor.py`](src/salesctl/doctor.py) | `$metadata` (CSDL) parser: tables present, actions bound or unbound, their parameters |
| [`src/salesctl/cli.py`](src/salesctl/cli.py), [`webapi.py`](src/salesctl/webapi.py), [`auth.py`](src/salesctl/auth.py) | CLI; Web API client (429 + Retry-After, formatted-value annotations); MSAL token provider, as in episodes 1–6 |
| [`sample/open-opportunities.json`](sample/open-opportunities.json) | 14 fictional open opportunities in Web API shape, for the offline `pipeline` and `hygiene` |
| [`tests/`](tests/) | 23 pytest tests; the Web API is a recording stub (tests only: the demo runs against the real environment) |

## Run and test (no tenant)

```bash
cd series/dynamics-365/episodes/07-dynamics-365-sales
python3 -m pip install --user -r requirements.txt
python3 -m pytest -q tests                                              # 23 passed
cd src
python3 -m salesctl pipeline --from-json ../sample/open-opportunities.json --now 2027-01-15
python3 -m salesctl hygiene  --from-json ../sample/open-opportunities.json --now 2027-01-15    # exit 1: 3 errors
```
```
Open pipeline: 14 opportunities, 753,500 EUR, weighted 336,075 EUR

close month  deals      value   weighted
2026-12          1     22,000     11,000
2027-01          6    341,500    136,325
...
ERROR   H001  Tailspin - data platform assessment: estimated close date 2026-12-18 is 28 day(s) in the past
ERROR   H002  Coho Winery - e-commerce connector: no estimated close date: it falls out of every forecast
ERROR   H003  Proseware - integration backlog: no estimated revenue: it counts for nothing in the pipeline
...
14 open opportunities: 3 error(s), 6 warning(s)
```

## Against an environment (needs tenant)

Prerequisites: a Dynamics 365 Sales environment (the lab's *Sales trial*), an identity with the Salesperson role (or
Sales Manager / System Administrator) so it can read and write leads and opportunities.

```bash
export DATAVERSE_URL=https://<org>.crm4.dynamics.com
cd src
python3 -m salesctl doctor                           # tables + actions, binding and parameters from $metadata
python3 -m salesctl leads --email jamie.rivera@contoso.example
python3 -m salesctl qualify <lead id>                # dry run
python3 -m salesctl qualify <lead id> --apply        # account + contact + opportunity; --no-account etc.
python3 -m salesctl pipeline
python3 -m salesctl hygiene
python3 -m salesctl close <opportunity id> --won --revenue 48000 --description "Signed" --apply
```

## What we learned / gotchas

- **Qualifying twice is not a safe no-op.** Learn's description of the qualify-lead tool says so, and says that
  disqualifying needs the lead to have no opportunity (Learn, *Qualify and convert a lead*: "You can disqualify a lead
  only if no opportunity is associated with it"). `qualify` stops on any lead that isn't open and reads the result back.
- **`QualifyLead` creates what you ask for and links it.** With account and contact both created, the account becomes
  the contact's parent customer and the contact the account's primary contact (Learn, `QualifyLeadRequest`). Duplicate
  detection applies unless `SuppressDuplicateDetection` is set; we leave it off.
- **Every opportunity needs an account or a contact** (Learn, *Create an opportunity*), so qualifying with all three
  flags off is refused by the tool before anything is sent.
- **Closing is an activity, not a field edit.** Learn: closing creates an *Opportunity Close* activity with actual
  revenue, close date, competitor and description; state values 1 Won / 2 Lost; status reasons 3 Won, 4 Canceled, 5
  Out-Sold. Win is the default and only status unless you add custom win reasons (SDK sample comment). The tool picks
  Canceled or Out-Sold for a loss depending on whether a competitor is named, as Learn's close-opportunity tool does.
- **The forecast category changes on close** (Sales Hub *Close opportunities as won or lost*): Won or Lost, set by the
  system. The Web API client asks for formatted values so `close` can print the label.
- **Weighted value here is arithmetic** (value × probability), the classic pipeline view. It is not Sales Premium's
  forecasting or predictive scoring, which this episode doesn't touch.
- **Date-only columns are strings.** `estimatedclosedate` is `DateOnly` (Opportunity table reference); the tool parses
  the first ten characters and never applies a time zone.
- **Not verified on Learn** (so the tool checks instead of assuming): the Web API reference pages for `QualifyLead`,
  `WinOpportunity` and `LoseOpportunity` could not be fetched while building, so the *binding* of `QualifyLead` (we use
  the bound form `leads(id)/Microsoft.Dynamics.CRM.QualifyLead`), the exact parameter names and the
  `@odata.type` of the `OpportunityClose` entity come from the SDK message classes (same names) and are confirmed on the
  real environment by `salesctl doctor` ([demo.md](demo.md) step 3). If `doctor` says otherwise, the code is fixed
  from its output.

## References
- [QualifyLeadRequest](https://learn.microsoft.com/dotnet/api/microsoft.crm.sdk.messages.qualifyleadrequest) (requires Dynamics 365 Sales; account/contact parent rules; "For the Web API use the QualifyLead action")
- [WinOpportunityRequest](https://learn.microsoft.com/dotnet/api/microsoft.crm.sdk.messages.winopportunityrequest) (Won, status 3, OpportunityClose entity) and [Create an opportunity](https://learn.microsoft.com/dynamics365/sales/developer/create-opportunity) (close creates an OpportunityClose activity)
- [Opportunity table reference](https://learn.microsoft.com/dynamics365/developer/reference/entities/opportunity) (estimatedvalue, estimatedclosedate DateOnly, closeprobability 0–100, msdyn_forecastcategory choices, WinOpportunity message)
- [Opportunity Close table reference](https://learn.microsoft.com/dynamics365/developer/reference/entities/opportunityclose) (opportunitystatecode 0/1/2, status reasons 3/4/5, actualrevenue, competitorid)
- [Lead table reference](https://learn.microsoft.com/dynamics365/developer/reference/entities/lead) (QualifyLead message)
- [Qualify lead (MCP tool)](https://learn.microsoft.com/dynamics365/developer/reference/mcp-tools/qualify_lead) and [Close opportunity (MCP tool)](https://learn.microsoft.com/dynamics365/developer/reference/mcp-tools/close_opportunity) (flags, default status reasons 3 / 7, loss defaults, not idempotent)
- [Qualify and convert a lead to opportunity](https://learn.microsoft.com/dynamics365/sales/qualify-lead-convert-opportunity-sales) and [Close opportunities as won or lost](https://learn.microsoft.com/dynamics365/sales/close-opportunity-won-lost-sales)
- Blog: [Dynamics 365 Sales — Complete Guide](https://www.devladlog.com/articles/dynamics-365/2025-10-08-dynamics-365-sales-complete-guide-2025/)
