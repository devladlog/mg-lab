# Demo shot list — DEVLADLOG Microsoft 365 #14: Microsoft Forms & Data Collection

Everything in `src/` and `tests/` already ran in the build container (48 Pester tests; offline spec check, list body, flow
map and analysis on fictional data). This file lists what the human-supervised session must set up and record in the **lab
tenant**. Every screen shows the real product: the real Microsoft Forms, the real Power Automate flow, the real SharePoint
list, the module talking to the real Graph. The fixture `tests/fixtures/items.json` is for the automated tests only and
never appears on screen.

## Lab environment

Recorded on the **lab Windows desktop**: a browser on the lab tenant (signed in as `labadmin`; private/InPrivate windows for the
three respondents), PowerShell 7 in a terminal. No VM is needed.

| Item | Value |
|---|---|
| Licences | Microsoft Forms and Power Automate come with the lab's E5 trial (Learn lists E1/E3/E5 and Business plans for Forms). The flow only uses **standard** connectors (Microsoft Forms: Standard class; SharePoint), so no premium licence is needed |
| SharePoint site | A new team site, e.g. **MG Lab Forms** (`https://<tenant>.sharepoint.com/sites/mg-lab-forms`), created by `labadmin` (SharePoint admin center > Active sites > Create > Team site, or SharePoint start page). Members: `labadmin` (owner), `alex.demo`, `sam.demo`, `jordan.demo` (visitors are enough for them: they only answer the form) |
| Power Platform | Environment `DEV`. The flow is created by `labadmin` (the Forms and SharePoint connections are his) |
| Respondents | `alex.demo`, `sam.demo`, `jordan.demo`, each in a separate private browser window. The form is set to *Only people in my organization can respond* with *Record name* on |
| Graph scopes (delegated, consent for `labadmin`) | `Sites.Read.All`, `Sites.Manage.All` (creating the list needs `Sites.Manage.All` per Learn). `labadmin` is Global Administrator and owner of the site |
| Host PowerShell | PowerShell 7.2+, `Install-Module Microsoft.Graph.Authentication -Scope CurrentUser` |
| Cost | none beyond the lab trial licences |

## Setup (before recording)

1. **Site.** Create the team site above. Copy its URL.
2. **Spec copy (keep out of the repo).** Copy `src/form.json` to `form.lab.json` and set `site.url` to the real site URL
   (the repo file has `contoso`). Do not commit it; mask the URL on screen.
3. **Dry run, off camera.** `./Invoke-FormsData.ps1 -SpecFile ./form.lab.json -Validate`, then
   `Connect-MgGraph -Scopes Sites.Read.All,Sites.Manage.All` and `-Provision -WhatIf` (expect `WhatIf-Create`). Delete nothing yet.
4. **Admin settings (read only).** Microsoft 365 admin center > Settings > Org settings > Services > **Microsoft Forms**: note the
   current values of External sharing (four options), Record names by default, Internal phishing protection, Bing and YouTube. Learn
   says these admin settings are available for Office 365 Education and Microsoft 365 Apps for business customers: if the lab tenant
   does not show the page, record that and say so on camera. Do not change them for the recording.

## Screens to capture (match `script.yaml` screen scenes)

### 1. `screens/provision.jpg` — "Create the list, twice" (**needs tenant**, creates a list)
```powershell
Connect-MgGraph -Scopes Sites.Read.All,Sites.Manage.All -NoWelcome
./Invoke-FormsData.ps1 -SpecFile ./form.lab.json -FlowMap        # the mapping table: show it, it is used in screen 2
./Invoke-FormsData.ps1 -SpecFile ./form.lab.json -Provision -WhatIf   # WhatIf-Create
./Invoke-FormsData.ps1 -SpecFile ./form.lab.json -Provision           # Created (confirm)
./Invoke-FormsData.ps1 -SpecFile ./form.lab.json -Provision           # Unchanged
```
Then the site: Site contents > *M365 Apps Pulse Responses*: the columns (ResponseId required; open the column settings to show *enforce
unique values*), the Rating min/max, the Department choices. Optional update path: add a question to `form.lab.json`, `-Provision -WhatIf`
(row `WhatIf-AddColumns`), apply (row `ColumnsAdded`), remove the question column again in the list settings afterwards.

> **Verify on first run (not confirmable from Learn):** (a) Graph accepts `required`, `indexed` and `enforceUniqueValues` on a column created
> with the list (SharePoint normally wants a column indexed before it can enforce unique values: if the create call is rejected, create
> the list without those flags and add them with an update column call, then fix `Get-FDMetaColumn` and the tests); (b) a `choice` column
> with `displayAs: checkBoxes` accepts several values (multi-select); (c) `Unchanged` on the second run, which relies on Graph returning
> the same `choices`, `minimum` and `maximum` we sent (if it normalises them, the module reports false drift: fix `Compare-FDColumn`);
> (d) `Title` is present (Learn: genericList includes it). If Graph rejects something, show the real error and fix module and tests.

### 2. `screens/flow.jpg` — "The form and the flow" (**needs tenant**, hand-built; this is the real product)
1. forms.office.com as `labadmin`: new form *Microsoft 365 Apps rollout pulse* with the six questions of `form.json` (same wording,
   Department as Choice, Rating as Rating or Choice 1–5, apps as Choice with *Multiple answers*, Comment as long text, Yes/No as Choice,
   date as Date). Settings: only people in my organization can respond, record name. Mask the form URL.
2. make.powerautomate.com (`DEV`): new automated cloud flow *MG Lab - Forms to SharePoint*: trigger **Microsoft Forms > When a new
   response is submitted** (select the form), action **Get response details** (Form Id, Response Id from the trigger), action
   **SharePoint > Create item** (the site and list). Fill the columns from the `-FlowMap` table: ResponseId = trigger Response Id,
   Responder = Responders' Email, Submitted = submission time (find the exact dynamic content name in the designer: it was not
   verified), the answers from the question outputs, Title = an expression such as `concat('Response ', <Response Id>)`.
   The multi-select answer arrives from Forms in a form the designer shows: record what it really is and what the Create item
   column accepts; if you need an expression (for example `join`), say so on camera. **Rewrite the narration to match.**
3. Save and turn on. Capture the designer.

### 3. `screens/analyze.jpg` — "Real responses, real report" (**needs tenant**)
1. Submit the form as `alex.demo`, `sam.demo` and `jordan.demo` (private windows; different departments and ratings, at least one low
   rating without a comment, one multi-select with two apps). Power Automate > the flow > run history: runs succeeded (wait a few
   minutes; if a run failed, show the real error and fix the flow).
2. The list shows the rows (Site contents > list).
3. `./Invoke-FormsData.ps1 -SpecFile ./form.lab.json -Analyze -OutFile ./responses.lab.md` and show the markdown (the summary table and the
   findings). Expect `LowRatingNoComment` if you did step 1 with a low rating and no comment; everything else only if it really happens.
4. **Real gap, no faking:** in Forms > Responses, delete one response, re-run: `ResponseIdGap`. (Optional second real test of the
   gotcha: turn the flow off, submit once, turn it on, re-run: record whether the response was captured or the gap shows. Learn does not
   say if the trigger back-fills: **say only what you observe.**)
5. Rewrite the narration to the real numbers and findings. Mask UPNs.

### 4. Admin settings (optional capture for the "Admin settings worth a look" bullets)
Microsoft 365 admin center > Settings > Org settings > Services > Microsoft Forms (read only, see Setup 4). Capture only.

## Masking checklist
- Tenant name/domain, site URL, form URL and form id, list/site/flow ids, admin UPN, user addresses beyond the lab aliases.
- `form.lab.json` and `responses.lab.md` contain tenant data: don't show them in full, never commit them.

## Tear-down (before the trial ends on 20 Dec 2026)
1. Power Automate: delete the flow *MG Lab - Forms to SharePoint* (and its run history goes with it).
2. Forms: delete the form (and its responses: they are personal data of lab users, fictional but still tidy).
3. SharePoint: delete the list (Site contents > list > Delete) or the whole site *MG Lab Forms*, and empty the recycle bins if you want it gone now.
4. Delete `form.lab.json`, `responses.lab.md`; `Disconnect-MgGraph`; remove the delegated consent granted only for the recording.
