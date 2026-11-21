# Demo shot list — DEVLADLOG Microsoft 365 #1: Tenant Administration & Monitoring

Everything in `src/` and `tests/` already ran in the build container (38 Pester tests, offline run from the fictional
snapshot). This file lists what the human-supervised session must record in the **lab tenant**.

## Prerequisites

| Item | Notes | Cost |
|---|---|---|
| Lab tenant with Microsoft 365 licences (exists) | Any E3/E5 lab; Secure Score and message center exist in every tenant | none |
| Recording account | Delegated sign-in. Suggested roles: **Global Reader** + **Reports Reader** (Global Reader alone only gets tenant-level usage data). Don't record with a Global Administrator if avoidable | none |
| PowerShell 7.2+ with `Microsoft.Graph.Authentication` | `Install-Module Microsoft.Graph.Authentication -Scope CurrentUser` | none |
| Consent | First `Connect-MgGraph` asks for the 7 read scopes (`ServiceHealth.Read.All`, `ServiceMessage.Read.All`, `Reports.Read.All`, `ReportSettings.Read.All`, `LicenseAssignment.Read.All`, `RoleManagement.Read.Directory`, `SecurityEvents.Read.All`). An admin may have to grant tenant-wide consent for the Microsoft Graph Command Line Tools app | none |
| Browser with `pipeline/mask.js` | For the admin center shot | none |

Optional (not needed for the video): an app registration with a certificate and the same 7 permissions as
*application* permissions, to show the scheduled `-TenantId -ClientId -CertificateThumbprint` run.

## Setup (before recording)

1. `cd series/microsoft-365/episodes/01-tenant-administration-monitoring`
2. `pwsh -NoProfile -Command 'Invoke-Pester ./tests'` → expect `Tests Passed: 38` (with the Graph module installed).
3. Leave the **Reports** org setting at its default (concealed names ON) so the gotcha scene reproduces. Check it in
   Microsoft 365 admin center → Settings → Org settings → Services → Reports.
4. Terminal: dark theme, font 18+, window ~1600×900, prompt shortened (`function prompt { 'PS> ' }`).

## Screens to capture (match the `screen` scenes in script.yaml)

### 1. `screens/sample-run.jpg` — "Fictional tenant, real report" (local, no tenant)
```powershell
cd src
./Invoke-TenantHealthCheck.ps1 -FromSnapshot ../tests/fixtures/snapshot.json -Now 2026-11-20T09:30:00Z -OutFile ../sample/report.md -FailOnHigh
```
Capture the findings table: 5 High rows first (EMSPREMIUM grace period, MC000005 overdue by 5 days, MC000001 action in
4 days, 5 active Global Administrator assignments, guest Partner Admin (Fabrikam)), then Medium/Low, and the red
`5 high-severity finding(s).` line. All data is fictional; nothing to mask.

### 2. `screens/live-run.jpg` — "The same check, live in the lab tenant" (**needs tenant**)
```powershell
./Invoke-TenantHealthCheck.ps1 -OutFile ./report.md -SnapshotFile ./snapshot.json
```
- Capture the consent prompt once (optional B-roll) and the findings table.
- **Rewrite the narration of this scene to the real numbers on screen** (the draft narration is deliberately generic).
- Things to verify and note in README if different:
  - the usage report section works, i.e. `Invoke-MgGraphRequest -OutputFilePath` follows the reports API `302`
    (if not, the report shows "Could not collect activeUsers" — record that honestly and fix in the module);
  - which sections, if any, return 403 with Global Reader + Reports Reader.
- Mask: tenant name/domain in UPNs, real people's names, message center IDs only if the lab owner considers them
  identifying (they're not tenant-specific, usually fine).

### 3. `screens/concealed.jpg` — "The gotcha: every user is a hash" (**needs tenant**)
```powershell
Import-Module ./M365TenantHealth/M365TenantHealth.psd1
Get-M365UsageReport -Report getOffice365ActiveUserDetail -Period D30 |
    Select-Object -First 3 'User Principal Name', 'Display Name' | Format-Table
(Get-Content ./snapshot.json -Raw | ConvertFrom-Json).reportSettings
```
Show the hashed values, `displayConcealedNames : True`, and the Info finding
"Usage reports are concealed; inactive users cannot be named" from shot 2. Nothing to mask (hashes).

### 4. `screens/report-setting.jpg` — "Whether to show names is a privacy decision" (**needs tenant**)
Microsoft 365 admin center → Settings → Org settings → Services → **Reports** panel, with the checkbox
"Conceal user, group, and site names in all reports" visible. **Do not change it on camera** unless the lab owner
agrees (it is audited). Mask the tenant name in the header / account menu.

## Masking checklist
- Tenant name, `*.onmicrosoft.com` domain, real user names/UPNs, tenant ID (never print `Get-MgContext`).
- Use `pipeline/mask.js` in the browser; blur terminal rows with real UPNs in post if needed.
- Never show `snapshot.json` from the lab in full: it contains real names.

## Tear-down
1. Delete `report.md` and `snapshot.json` produced from the lab (they contain tenant data); don't commit them.
2. `Disconnect-MgGraph`.
3. If consent was granted only for the recording, remove it: Entra admin center → Enterprise applications →
   Microsoft Graph Command Line Tools → Permissions (or delete the user's delegated grant).
4. If the Reports setting was changed for a test, put it back.
