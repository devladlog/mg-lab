# Demo shot list — DEVLADLOG Dynamics 365 #8: Dynamics 365 Customer Service

Already run in the build container: `python3 -m pytest -q tests` (18 passed, Web API stubbed) and the offline `triage`
on the fictional sample. **Nothing has run against Dataverse yet: all four `screen` scenes need the lab tenant**, and
`sla` and `resolve` depend on names that `doctor` must confirm first (step 4).

## Lab environment

No VMs, no Azure resources: cloud tenant only, browser (Customer Service Hub, admin center) plus a terminal.

| Item | Notes | Cost |
|---|---|---|
| Dynamics 365 **Sales trial** environment (EMEA, created 21 Nov 2026, 30-day trial, ends ~21 Dec 2026) | **Why this one and not `DEV`:** `DEV` is Dataverse-only and Dynamics 365 apps can't be installed there (Learn, *Manage Dynamics 365 apps*). Learn (*Availability of Customer Service Hub*) says Customer Service Hub is installed automatically in environments with customer engagement apps such as Sales Hub, which is this one. Contoso Retail from episode 7 lives here too. Record **before the trial ends**. Mask the org URL | none (trial) |
| **Fallback if Customer Service Hub is missing or the lab users' licences can't open it** | Learn (*Can't install Customer Service applications*) lists the licences: Customer Service Professional / Enterprise / Premium. Start the Customer Service trial (Learn, *About trial environments*: standard trial from the admin center with *Enable Dynamics 365 apps* + Customer Service, or the Customer Service get-started page), 30 days. Then re-create the Contoso Retail account there (`salesctl` isn't needed: create it in the app) and say in the narration that this is a second trial environment | none (trial) |
| `labadmin` | System Administrator; runs the terminal and configures SLAs | none |
| `alex.demo` | Customer service agent in the browser: needs a Customer Service Representative role and *Customer service app access* (setup step 2) | none |
| Recording laptop | Python 3.10+, `pip install --user -r requirements.txt`, dark terminal font 18+, browser with `pipeline/mask.js` | none |

## Setup (before recording)

1. Open `https://admin.powerplatform.microsoft.com` → Environments → *Sales trial* → Resources → Dynamics 365 apps:
   check that **Customer Service Hub** is listed as installed. If not, see the fallback above.
2. Settings → Users + permissions → Users: give `alex.demo` **Customer Service Representative** and **Customer
   service app access** (write the exact role names in README if they differ). Sign in as `alex.demo` once and open
   Customer Service Hub: if it refuses, note the licence message (this decides the fallback).
3. SLA, as `labadmin` in the Copilot Service admin center (Learn, *Configure service-level agreements*): Operations →
   **Service terms** → *SLA KPIs* → Manage → New: name **First response**, Entity **Case**, KPI field
   **FirstResponseByKPI**, Applicable From **Created On**; and **Resolve** with **ResolveByKPI**, same entity and
   applicable-from. Then *Service-level agreements* → Manage → New: **Contoso standard**, entity Case, type **Enhanced**,
   add SLA items for the two KPIs (failure after 4 h and 24 h is enough: a demo SLA, not real targets), Applicable When
   *Priority = High* for one item and no condition for the other if the designer allows; Success criteria *First
   Response Sent = Yes* for the first. **Save, Activate, then Set As Default** (Learn: without a default SLA none is
   applied to a case). Menu names may differ: note what you actually clicked and fix this section.
4. `export DATAVERSE_URL=https://<sales trial>.crm4.dynamics.com`, `cd src`, `python3 -m casekit doctor`.
   **Verify and note in README** ("Not verified on Learn"): `incident`, `incidentresolution`, `sla`, `slakpiinstance`
   present; `CloseIncident` unbound with parameters `IncidentResolution`, `Status`; case KPI lookups listed as
   `firstresponsebykpiid`, `resolvebykpiid`. If the names differ, edit `KPIS` in `sla.py` and the tests.
5. `python3 -m casekit seed` (dry run, 5 lines starting with `+`), then `python3 -m casekit seed --apply`, then
   again (all lines `=`). Needs the account *Contoso Retail* (episode 7 step: qualify the lead; otherwise create it in
   the app).
6. In Customer Service Hub as `alex.demo`: open **[MGL demo] Cannot sign in to the store portal** (High) and check that
   the SLA timers show on the case form. If they don't, the SLA isn't applied: re-check step 3 (default SLA).

## Screens to capture (match the `screen` scenes in script.yaml)

### 1. `screens/service-sla-config.jpg` — "The SLA behind the cases" (needs tenant)
Copilot Service admin center → Service terms: the two SLA KPIs and the SLA **Contoso standard** with its SLA items,
showing it is the default and active. Mask tenant and user.

### 2. `screens/casekit-triage.jpg` — "Triage and the platform's view" (needs tenant)
```bash
python3 -m casekit triage
python3 -m casekit sla
```
Real output for the seeded cases. The seeded cases are brand new, so `triage` will probably find nothing late: to have
something to show, either leave the High case untouched until its 4 h first-response target passes (start step 5 ahead
of the recording), or run `triage` on the sample with `--now` as the "late" example and say it is the offline sample.
`sla` should list the KPI status per case ("In Progress" and so on); keep whatever it really says. Blur case ids.

### 3. `screens/service-case-form.jpg` — "What the agent sees" (needs tenant)
Customer Service Hub as Alex Demo: the High-priority case open with the SLA timers (first response, resolve) and
the customer Contoso Retail. Mask tenant and avatar.

### 4. `screens/casekit-resolve.jpg` — "Resolve from code" (needs tenant)
```bash
python3 -m casekit resolve <case id> --subject "Passwords reset" --description "Reset done, sign-in tested"
python3 -m casekit resolve <case id> --subject "Passwords reset" --description "Reset done, sign-in tested" --apply
python3 -m casekit sla
```
Show the dry run, then apply and its read-back (`statecode 1 statuscode 5`), then in Hub the case as Resolved with the
case resolution activity on the timeline, and `sla` showing the KPI as Succeeded if the success criteria were met.

## Masking checklist
- Org URL, tenant name, user UPNs, avatars, GUIDs and case numbers in the terminal if they could be real (they are
  system-generated, so they aren't, but blur the org-dependent parts).
- Only the fictional account (Contoso Retail), `[MGL demo]` cases and lab users on screen.

## Tear-down
1. Delete the five `[MGL demo]` cases and their resolutions.
2. Deactivate and delete the SLA **Contoso standard** and the two SLA KPIs (unset default first).
3. Remove `alex.demo`'s Customer Service roles if no later episode needs them.
4. If the fallback Customer Service trial was started: delete that environment in the admin center (or let it expire).
