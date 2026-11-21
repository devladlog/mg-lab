# Demo shot list — DEVLADLOG Dynamics 365 #7: Dynamics 365 Sales

Already run in the build container: `python3 -m pytest -q tests` (23 passed, Web API stubbed) and the offline
`pipeline` / `hygiene` commands on the fictional sample. **Nothing has run against Dataverse yet: all four `screen`
scenes need the lab tenant**, and the `code` scenes show real excerpts that `doctor` must confirm first (step 3).

## Lab environment

No VMs, no Azure resources: cloud tenant only, browser (Sales Hub) plus a terminal on the recording laptop.

| Item | Notes | Cost |
|---|---|---|
| Dynamics 365 **Sales trial** environment (EMEA, created 21 Nov 2026, 30-day trial, ends ~21 Dec 2026) | **Why this one and not `DEV`:** `QualifyLead` and `WinOpportunity` are Dynamics 365 Sales messages (Learn: QualifyLeadRequest "requires Dynamics 365 Sales") and the Sales Hub app with sample data is only here. Record **before the trial ends**. Mask the org URL in every capture | none (trial) |
| `labadmin` | System Administrator in the Sales trial environment; runs the terminal | none |
| `alex.demo` | The seller in the browser. Needs the **Salesperson** security role in the Sales trial environment (setup step 1) | none |
| Recording laptop | Python 3.10+, `pip install --user -r requirements.txt`, dark terminal font 18+, browser with `pipeline/mask.js` | none |

## Setup (before recording)

1. Power Platform admin center → Environments → *Sales trial* → Settings → Users + permissions → Users: add
   `alex.demo` and assign **Salesperson** (note the exact role names the environment offers; if there is no
   Salesperson role, use the Sales app's own role set and write the name in README).
2. `export DATAVERSE_URL=https://<sales trial>.crm4.dynamics.com` (never written in a file), `cd src`. The first
   command opens the interactive sign-in as `labadmin`.
3. `python3 -m salesctl doctor` — **verify and note in README** (section "Not verified on Learn"): `QualifyLead`
   shown as *bound to mscrm.lead*? parameters `CreateAccount, CreateContact, CreateOpportunity, Status,
   SuppressDuplicateDetection`...? `WinOpportunity` / `LoseOpportunity` unbound with `Status, OpportunityClose`? If
   anything differs, fix `lead.py` / `close.py` and their tests before recording.
4. In Sales Hub (as `alex.demo`): Leads → New. Topic **Contoso Retail - analytics inquiry**, First/Last name
   **Jamie Rivera**, Company **Contoso Retail**, Email **jamie.rivera@contoso.example**, Budget 90,000 if the form has
   it. Save. Do not click Qualify.
5. Look at the sample opportunities that ship with the trial: `python3 -m salesctl pipeline` and `hygiene`. The
   numbers will be whatever the sample data says: that is what the screen shows. If the trial's sample data is clean,
   add three deliberately bad opportunities as `alex.demo` (past close date, no estimated revenue, no close date) and
   say so in the narration; delete them in tear-down.

## Screens to capture (match the `screen` scenes in script.yaml)

### 1. `screens/sales-lead-form.jpg` — "The lead and its process" (needs tenant)
Sales Hub as Alex Demo: the lead from step 4 open, the *Lead to Opportunity Sales Process* bar visible at the top
(Qualify stage), Topic and Company readable. Mask tenant, avatar, org URL.

### 2. `screens/salesctl-qualify.jpg` — "Qualify from code" (needs tenant)
```bash
python3 -m salesctl leads --email jamie.rivera@contoso.example
python3 -m salesctl qualify <lead id>              # dry run
python3 -m salesctl qualify <lead id> --apply
```
Show the dry-run line (`would create account, contact, opportunity`), then the apply and the read-back line
(`qualified: statecode 1 statuscode 3  opportunity ...`). Blur the GUIDs. Then, in Sales Hub, the lead is gone from
open leads and the new opportunity, account and contact exist (a second small capture, can be an inset).
Run `qualify <lead id> --apply` a **second** time on camera to show the refusal ("is not open ... not a safe no-op").

### 3. `screens/salesctl-pipeline.jpg` — "Pipeline and hygiene" (needs tenant)
```bash
python3 -m salesctl pipeline
python3 -m salesctl hygiene
```
Real numbers from the environment. Keep any error lines and read them out; if `hygiene` exits 1, say that is the
point (a scheduled check fails the build).

### 4. `screens/sales-closed-won.jpg` — "Close as won" (needs tenant)
```bash
python3 -m salesctl close <opportunity id> --won --revenue 48000 --description "Signed after workshop"     # dry run
python3 -m salesctl close <opportunity id> --won --revenue 48000 --description "Signed after workshop" --apply
```
Then Sales Hub → Opportunities → Closed Opportunities view: the opportunity as Won, actual revenue 48,000, forecast
category Won (Learn says the system sets it), and Related → Activities → the *Opportunity Close* activity. Blur ids.

## Masking checklist
- Org URL, tenant name, user UPNs, avatars, GUIDs in the terminal. Sample-data company names that look real: blur or
  avoid them in the pipeline capture.
- Only the fictional lead (Jamie Rivera, Contoso Retail) and lab users on screen.

## Tear-down
1. Delete the opportunity, account and contact created by the qualify step, and the three optional bad opportunities.
2. Remove `alex.demo`'s Salesperson role in the Sales trial environment if no later episode needs it.
3. Nothing else is created: the trial environment expires on its own (~21 Dec 2026) or can be deleted in the admin
   center once episode 8 is also recorded.
