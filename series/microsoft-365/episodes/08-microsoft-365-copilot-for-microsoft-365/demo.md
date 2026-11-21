# Demo shot list — DEVLADLOG Microsoft 365 #8: Microsoft 365 Copilot for Microsoft 365

Everything in `src/` and `tests/` already ran in the build container (49 Pester tests, offline report from a fictional
snapshot). This file lists what the human-supervised session must set up and record in the **lab tenant**. Every Graph
call below is **needs tenant**; every screen shows the real product (the real admin center, the real Copilot Chat, the
script talking to the real Graph). `tests/fixtures/*` is for the automated tests only and never appears on screen.

**The lab has no Microsoft 365 Copilot licence, and none is bought for this episode.** The episode is built on what
works without one: licence readiness, Copilot Chat with Entra accounts, the oversharing review and the label check.
Anything that needs the licence is marked **NEEDS COPILOT LICENCE** with its cost, is an optional insert at the end, and is
never simulated: if it isn't recorded, the script's licence scenes already say what the licence adds.

## Lab environment

No VM. Recorded on the **lab Windows desktop**: a browser on the lab tenant (Microsoft 365 admin center, Copilot Chat,
SharePoint, Purview) and PowerShell 7.2+ on the host.

| Cloud item | Notes | Cost / requirement |
|---|---|---|
| Microsoft 365 E5 trial (already in the lab) | Includes Exchange Online, SharePoint, Purview, Entra ID P2 and the Copilot Chat entitlement for Entra accounts (Learn: Copilot Chat needs an eligible base licence and an Entra account, no Copilot licence) | in the lab |
| Copilot Chat | `copilot.cloud.microsoft` signed in as `alex.demo` (a work account). Learn: allow `*.cloud.microsoft` on the network; the Work label and the green data protection shield show an Entra sign-in | **free with E5** (enterprise data protection applies) |
| Lab users | `alex.demo` (Chat screen), `labadmin` (recording account, owner of the lab site), `sam.demo`, `jordan.demo`, `riley.demo`, `taylor.demo` (appear in the readiness table) | none |
| Lab site | **MG Lab - Marketing** (Team site, owner `labadmin`) with fictional files, see Setup | none |
| Labels | The labels created in episode 5 (Public, General, Confidential) from Purview, if they still exist. If they don't, record the `NoLabels` finding honestly, or re-create them with episode 5's script | none (E5 includes Purview) |
| Graph scopes (delegated, consent for `labadmin`) | `LicenseAssignment.Read.All`, `User.Read.All`, `SensitivityLabel.Read`, `Sites.Read.All`, `Files.Read.All`. All read-only | none |
| Roles | `labadmin` as Global Administrator (Learn: `licenseDetails` needs a role such as License Administrator or Directory Readers; the other calls only see what `labadmin` can see) | none |
| Host PowerShell | PowerShell 7.2+, `Install-Module Microsoft.Graph.Authentication -Scope CurrentUser` | none |
| **NEEDS COPILOT LICENCE** (optional insert only) | **Microsoft 365 Copilot add-on**: Copilot in Word/Excel/PowerPoint/Outlook/Teams, grounding in Microsoft Graph, SharePoint Advanced Management (SAM) reports, the Copilot usage report API | Microsoft's own pricing page (en-us, read on 21 Nov 2026): **30.00 USD per user per month, paid yearly, annual subscription that auto-renews**; Copilot Business (organizations up to 300 users, needs eligible Business licences such as Microsoft 365 Business Standard): **18.00 USD per user per month paid yearly** (page shows a discount window 1 Jul to 31 Dec 2026). The page says it is for marketing purposes and the real price is shown at checkout; no currency code is shown. **One seat for one year is therefore a commitment of roughly 216 to 360 USD**: the lab owner decides whether that is worth one optional insert. Whether a trial tenant can buy it, and the cancellation and refund terms, were not verified |

## Setup (before recording)

1. **Module.** On the host: `Install-Module Microsoft.Graph.Authentication -Scope CurrentUser`.
2. **Config.** Copy `src/copilot.json` to `copilot.lab.json` (outside the repo). Nothing tenant specific is needed in it.
3. **Site and files** (SharePoint, as `labadmin`, so the owner sees every permission: Learn says a non-owner only gets the
   sharing permissions that apply to them, so run the script as the site owner or the review under-reports):
   - Create the Team site **MG Lab - Marketing**.
   - In Documents create `Campaigns/Launch plan.docx`, `HR/Payroll 2026.xlsx`, `HR/salary-bands.xlsx`, `Board/minutes.docx`.
     Content is a line of fictional text ("Contoso lab file"). No real data, ever.
4. **Seed the oversharing for real** (this is the demo's data, all removed in tear-down):
   - *Organization link:* `Launch plan.docx` → Share → **People in Contoso** (view), or with Graph
     (`Files.ReadWrite.All`, needs tenant, Learn: *driveItem: createLink*):
     ```powershell
     Connect-MgGraph -Scopes Files.ReadWrite.All -NoWelcome
     Invoke-MgGraphRequest -Method POST -Uri "/v1.0/drives/$driveId/items/$itemId/createLink" -ContentType 'application/json' -Body (@{ type = 'view'; scope = 'organization' } | ConvertTo-Json)
     ```
   - *Everyone except external users:* folder `HR` → Manage access → grant it **Everyone except external users**
     (read). If the people picker doesn't offer the group in this tenant, say so on camera and skip it (not verified).
   - *Anyone link* on `salary-bands.xlsx` **only if the tenant already allows Anyone links**. Do not change the tenant
     sharing policy for a demo. If it isn't allowed, that is itself worth one sentence on camera.
5. **Labels.** Purview portal → Information protection → Sensitivity labels: confirm the episode 5 labels exist and are published.
6. **Dry run, off camera:** `./Invoke-CopilotReadiness.ps1 -ConfigFile ./copilot.lab.json -SaveSnapshot ./snapshot.lab.json -OutFile ./readiness.lab.md`.
   Check that the `EveryoneExceptExternalUsers` row appears for `HR`. **If it doesn't, the permission is rendered differently from
   what `Get-PermissionSignal` matches** (Learn documents the group by its display name; the claim fragment is a common rendering,
   not something Learn states): open `snapshot.lab.json`, find the permission on `HR`, adjust the match, add a test, rerun the tests.

## Screens to capture (match `script.yaml` screen scenes)

### 1. `screens/licences.jpg` — "What the tenant really has" (**needs tenant**)
1. Microsoft 365 admin center → Billing → **Licenses**: the E5 trial and the Copilot Studio trial listed, no Microsoft 365 Copilot.
2. Host PowerShell:
   ```powershell
   ./Invoke-CopilotReadiness.ps1 -ConfigFile ./copilot.lab.json -Check Licences
   ```
   Capture the line `Copilot licence in tenant: NO` and the user table with the **real** statuses (a user can legitimately show
   `Not ready` or a note about a mailbox: say what it is, don't edit it away).
3. Mask the tenant name, the UPN domain and any SKU object ids.

### 2. `screens/chat.jpg` — "Copilot Chat, with an Entra account" (**needs tenant**, free)
1. Browser as `alex.demo` → `copilot.cloud.microsoft`. Show the Work label under the profile and the data protection shield.
2. Upload the fictional `Contoso travel policy.docx` (create it first: a short paragraph of fictional text) and ask for a three-bullet summary.
3. Capture the real answer. **Do not** script what Chat says about the company's mail or files: without the add-on it
   isn't grounded in Microsoft Graph, so show only what actually happens. Rewrite the narration to the real answer.
4. Optional capture for the "controls" bullet: Microsoft 365 admin center → Copilot → Settings (pinning) and Copilot controls
   (web search policy, agents). Capture only, change nothing.

### 3. `screens/sharing.jpg` — "Seeded oversharing, found by the script" (**needs tenant**, read-only)
```powershell
Connect-MgGraph -Scopes Sites.Read.All, Files.Read.All -NoWelcome
./Invoke-CopilotReadiness.ps1 -ConfigFile ./copilot.lab.json -Check Sharing -OutFile ./readiness.lab.md
```
Capture the findings table (worst first) and the line with the item count. Then open `Launch plan.docx` → Manage access in SharePoint
and show the same permission. Rewrite the narration to the real findings and counts. Mask the site URL and UPNs.

### 4. `screens/labels.jpg` — "Do the labels exist?" (**needs tenant**, read-only)
```powershell
./Invoke-CopilotReadiness.ps1 -ConfigFile ./copilot.lab.json -Check Labels
```
Alongside, Purview portal → Information protection → Sensitivity labels. Capture the real findings (episode 5's labels are Public, General,
Confidential: expect `NoContainerLabel` and `NoAutoLabel` unless they were changed). If the label call is refused (403) because of a missing
scope or role, show that error and fix the consent: do not fall back to a snapshot.

### Optional insert — **NEEDS COPILOT LICENCE** (not part of the recorded screens; cost above)
Only if the lab owner decides to buy one seat: Microsoft 365 admin center → Billing → Purchase services → Microsoft 365 Copilot;
assign it to `alex.demo`; allow time to propagate (not documented, check). Then capture:
1. Copilot in Word summarising `Contoso travel policy.docx`, as the real product shows it.
2. `./Invoke-CopilotReadiness.ps1 -ConfigFile ./copilot.lab.json -Check Licences` now says `Copilot licence in tenant: YES` and
   Alex shows `Copilot licensed`.
3. After some real use: `./Invoke-CopilotReadiness.ps1 -Check Usage` (`Reports.Read.All` plus a reader role such as AI Administrator or
   Reports Reader). Learn: only users with a Copilot licence appear, and the report may lag.
4. SharePoint admin center → Reports → Data access governance (SharePoint Advanced Management comes with the Copilot licence, Learn).
If none of this is recorded, the script's "what the licence adds" scene stands as written: it makes no claim about output.

## Masking checklist
- Tenant name/domain, admin UPN, user addresses beyond the lab aliases, SKU and user object ids, SharePoint site URLs, share link URLs.
- `copilot.lab.json`, `snapshot.lab.json`, `readiness.lab.md` contain tenant data: don't show them in full, never commit them.

## Tear-down (before the trial ends on 20 Dec 2026)
1. SharePoint: delete the site **MG Lab - Marketing** (and from the recycle bin if the files must go), or remove the seeded links and the
   Everyone except external users grant.
2. Delete `Contoso travel policy.docx` from wherever it was uploaded, and the Chat conversation if it holds anything beyond the demo.
3. If a Copilot seat was bought for the optional insert: unassign it from `alex.demo` and cancel the subscription as the purchase terms
   allow (annual commitment: check before buying).
4. Delete `copilot.lab.json`, `snapshot.lab.json`, `readiness.lab.md`; `Disconnect-MgGraph`; remove the delegated consent granted only for the recording.
