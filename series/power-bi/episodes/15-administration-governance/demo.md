# Demo shot list — Power BI #15 Administration and Governance

## Lab environment

No VM and no Azure resource. Everything runs on the **Windows recording laptop** against the **lab tenant** (`series/LAB.md`): M365 E5 trial and the Fabric/Power BI 60-day trial (West Europe).

| What | Details | Cost |
|---|---|---|
| Recording laptop (Windows) | PowerShell 7.2+, Windows Terminal, a Markdown preview (VS Code), a browser with a clean profile | free |
| PowerShell modules | `MicrosoftPowerBIMgmt` (`Install-Module MicrosoftPowerBIMgmt -Scope CurrentUser`), `Az.Accounts` (for the Fabric token), `Pester` 5+ for the tests | free |
| Lab tenant: account | `labadmin` (Global Administrator, therefore Fabric administrator) runs the audit and changes the setting | trial |
| Lab tenant: content | workspace `Contoso Sales (Lab)` with the model and report of episode 5; users `alex.demo`, `sam.demo`, `jordan.demo`, `riley.demo`, `taylor.demo` as workspace members or viewers | trial, €0 |
| Optional | a second workspace `Contoso Orphan (Lab)` for the orphaned-workspace screen (see step 5) | €0 |

## What was verified where

| Step | In the container | Needs the lab tenant on the recording day |
|---|---|---|
| Module logic, rules GV001-GV009, drift, report, exit codes | 59 Pester tests with Learn-shaped fixtures, 5 pytest tests for `script.yaml` | nothing more |
| Fabric call wrapper (bearer header, 429 + Retry-After, continuationUri) | tested over real HTTP against a loopback stand-in | the real `api.fabric.microsoft.com` call |
| All Power BI admin calls (activity events, groups, modified workspaces, scanner) | mocked | **all of it** |
| Tenant setting delay, event delay, which operation names appear | nothing | see "Write down" |

## Setup (off camera, once)

1. Copy `15-administration-governance` to `C:\MGLab\power-bi\ep15\`. From that folder: `Invoke-Pester ./tests/PbiGovernance.Tests.ps1` (expect 59 passed).
2. `Connect-PowerBIServiceAccount` as `labadmin`. Fabric token: `Connect-AzAccount` as `labadmin`, then `$fabric = (Get-AzAccessToken -ResourceUrl 'https://api.fabric.microsoft.com' -AsSecureString).Token` (the shape of the result depends on the Az.Accounts version: check `$fabric` is a SecureString).
3. Write the baseline from the tenant as it is today, then review it and keep the settings the episode talks about:
   `Import-Module ./src/PbiGovernance/PbiGovernance.psd1; Export-PbiTenantBaseline -Setting @(Get-PbiTenantSetting -FabricToken $fabric) -Path ./src/policy/tenant-baseline.json`
   (the file holds group names of the lab tenant: keep it out of the repository, `tenant-baseline.example.json` is the committed shape).
4. **The day before the recording**, do some activity as the demo users: open the report, export it once, share it once (this feeds the `activity-summary` screen).
5. Optional orphaned workspace: create `Contoso Orphan (Lab)`, make `taylor.demo` Admin, then try to remove `labadmin` and any other Admin. If the service does not allow it, skip the screen and use the offline run on the fixture instead (say so in the voice over).

## Steps and screens (match the `screen` scenes in script.yaml)

| Scene id | File | Steps and what must be on screen |
|---|---|---|
| `report` | `screens/governance-report.jpg` | Terminal in `src`: `./Invoke-GovernanceAudit.ps1 -BaselinePath ./policy/tenant-baseline.json -FabricToken $fabric`, then open `out/governance-<date>.md` in the preview: the five sections. Then the offline run `./Invoke-GovernanceAudit.ps1 -ScanResultPath ../tests/fixtures/scan-result.json -SkipActivity -OutDir ./out-offline` (12 findings, exit code 1: show `$LASTEXITCODE`). Blur workspace ids, if any |
| `drift-screen` | `screens/settings-drift.jpg` | Admin portal, **Tenant settings**: switch one baseline setting off (note which one), **Apply**. After the wait (see `gotcha`) run the audit: the section **Tenant settings drift** lists `EnabledChanged: enabled=True -> enabled=False`. Switch it back on, wait, run again: "No difference from the baseline" |
| `activity-screen` | `screens/activity-summary.jpg` | `Get-PbiActivitySummary -Event @(Get-PbiActivityEvent -Date (Get-Date).AddDays(-1))` and show the object (totals, per activity, most viewed reports with distinct users, risky operations). Aliases only: blur anything with a domain just in case |
| `gotcha` | `screens/lag.jpg` | Immediately after **Apply** on a setting, and right after an export by `sam.demo`, run the audit: neither shows. Wait and run again: both do. Keep a clock visible. Record the real delays |

## Write down (the README's "Not verified" list)

1. Does every Power BI admin call work for `labadmin` as it is, and do the scanner results contain `users`, `sensitivityLabel`, `endorsementDetails`, `misconfiguredDatasourceUsages` with the names the module reads? Does the scanner need the two "Enhance admin APIs responses ..." tenant settings for `datasetSchema` and `datasetExpressions`?
2. Does a Power BI token work for `api.fabric.microsoft.com`? (If yes, the second token is not needed and the narration can say so.)
3. Does Get Groups as Admin still return `users` with `$expand=users`? Does it return the orphaned workspace?
4. The real delay of a tenant setting and of an activity event.
5. Which operation names appear for export, share and view, and are they all in the module's risky list (`ExportReport`, `ShareReport`, ...)?
6. How many events one day holds in the lab and how many requests that took.

## Masking

Blur: the tenant name and sign-in domain (account menu, terminal prompt of the token step), workspace and report ids, the baseline's security group names if they carry the tenant name.
Tokens are never printed: `$fabric` is a SecureString; do not run `ConvertFrom-SecureString` on camera.
