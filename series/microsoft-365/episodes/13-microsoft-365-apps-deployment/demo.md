# Demo shot list — DEVLADLOG Microsoft 365 #13: Microsoft 365 Apps Deployment

Everything in `src/` and `tests/` already ran in the build container (57 Pester tests; offline XML build/validation and
activation audit on fictional data). This file lists what the human-supervised session must set up and record in the
**lab tenant** with a **real Windows 11 VM**. Every screen shows the real product: the real Office Deployment Tool
installing real Microsoft 365 Apps, the real Intune admin center, the module talking to the real Graph. The fixtures in
`tests/fixtures/` are for the automated tests only and never appear on screen.

## Lab environment

Recorded on the **lab Windows desktop** (Hyper-V host): VM console (VMConnect), a browser on the lab tenant (Intune admin
center, Microsoft 365 admin center) and PowerShell 7 on the host.

| Item | Value |
|---|---|
| VM | **`CON-W11-01`** from `series/LAB.md` and episode 7: Windows 11 Enterprise evaluation, Entra joined as `alex.demo` (local administrator because he did the join), Intune enrolled, vTPM. Reuse it. If episode 7's tear-down already deleted it, rebuild it with `lab/hyperv/Start-MGLab.ps1` and Entra join as `alex.demo` again |
| Network | VM on the Hyper-V `Default Switch` with outbound HTTPS to the internet: the Office CDN (`officecdn.microsoft.com`), the release discovery API (`clients.config.office.net`) and the Microsoft 365 sign-in endpoints |
| Disk | Office needs a few GB: keep the 64 GB VHDX, but check free space before the install (Learn: setup error codes 112 / 30192 / 30179 mean disk space) |
| Software on the VM | The module needs **PowerShell 7.2+**, which Windows 11 does not ship: install it on the VM (`winget install Microsoft.PowerShell`, or the MSI from GitHub; not verified on this image, check `winget` works) and the Office Deployment Tool (below) |
| Licence | `alex.demo` must have a licence that includes **Microsoft 365 Apps** (E5 trial). Check: Microsoft 365 admin center > Users > Active users > Alex Demo > Licenses and apps > "Microsoft 365 Apps for enterprise" (or the equivalent in the E5 plan) enabled. If it isn't, enable it for this recording and set it back in tear-down |
| Cloud items | Intune app (created by the demo), Entra group **MG Lab - Intune Users** (episode 7; create it again if removed: security group, members alex.demo and sam.demo; copy the Object Id) |
| Graph scopes (delegated, consent for `labadmin`) | `DeviceManagementApps.ReadWrite.All` (create, update, assign the app), `Reports.Read.All` (activation report; `labadmin` needs a role that can read usage reports, e.g. Global Reader or Reports Reader). Learn: if the tenant conceals user names in reports, the UPN column holds hashes: Microsoft 365 admin center > Settings > Org settings > Services > Reports |
| Host PowerShell | PowerShell 7.2+, `Install-Module Microsoft.Graph.Authentication -Scope CurrentUser` |
| Cost | none beyond the lab trial licences |

## Setup (before recording)

1. **Office Deployment Tool on the VM.** Download from the Microsoft Download Center (Learn:
   <https://go.microsoft.com/fwlink/p/?LinkID=626065>), run the self-extracting file, extract to `C:\ODT`. It contains
   `setup.exe` and a sample `configuration.xml`. Learn: always use the latest ODT.
2. **Copy the code** to the VM: from the host, `Copy-VMFile -VMName CON-W11-01 -SourcePath <zip> -DestinationPath C:\mg\ -FileSource Host -CreateFullPath`
   (needs Guest Services enabled on the VM), or the Hyper-V enhanced session clipboard. Unzip `src\` to `C:\mg\src`.
3. **Config copies (keep out of the repo):** `apps.lab.json` = copy of `src\apps.json` with `intune.assignTo.groupId` set
   to the group's Object Id (on the host, for the Graph steps). On the VM `apps.json` is used as is.
4. **Dry run, off camera:** on the host `./Invoke-AppsDeploy.ps1 -BuildXml` and `-ValidateXml`; on the VM `-Inventory`
   (expect `NotInstalled`); `Connect-MgGraph -Scopes DeviceManagementApps.ReadWrite.All,Reports.Read.All`.
5. **Make sure Office is not already installed** on the VM (Settings > Apps > Installed apps). The Windows 11 evaluation
   image may ship without Office.

## Screens to capture (match `script.yaml` screen scenes)

### 1. `screens/install.jpg` — "Install on a real PC" (**needs tenant licence + VM**)
Elevated PowerShell **7** on `CON-W11-01`, in `C:\mg\src`:
```powershell
./Invoke-AppsDeploy.ps1 -Inventory                                                    # NotInstalled
./Invoke-AppsDeploy.ps1 -Install -OdtPath C:\ODT\setup.exe -WhatIf                    # Result WhatIf: command + file
./Invoke-AppsDeploy.ps1 -Install -OdtPath C:\ODT\setup.exe -Confirm:$false            # real install, several minutes
```
Learn: after a successful install the command prompt shows "Products configured successfully" (if it doesn't appear with
`Display Level="None"`, check the log files in `%temp%`; say what really happened). Then open Word, sign in as
`alex.demo` if asked: **File > Account** shows the user, "Product Activated" and the update channel (Learn: shown
under Product Information). Capture both. Mask the UPN domain.

### 2. `screens/publish.jpg` — "Publish and assign" (**needs tenant**, creates an app, beta API)
On the host:
```powershell
Connect-MgGraph -Scopes DeviceManagementApps.ReadWrite.All -NoWelcome
./Invoke-AppsDeploy.ps1 -ConfigFile ./apps.lab.json -PublishIntune -WhatIf     # WhatIf-Create
./Invoke-AppsDeploy.ps1 -ConfigFile ./apps.lab.json -PublishIntune             # Created
./Invoke-AppsDeploy.ps1 -ConfigFile ./apps.lab.json -PublishIntune             # Unchanged
```
Then Intune admin center > Apps > Windows > *MG Lab - Microsoft 365 Apps (Monthly Enterprise)*: Properties and Assignments.
Optional update path: set `channel` to `Current` in `apps.lab.json`, `-PublishIntune -WhatIf` (row `WhatIf-Update`, change
`updateChannel`), apply, refresh the portal, set it back.

> **Verify on first run (not confirmable from Learn):** (a) the create call accepts the body with all 15 `excludedApps`
> booleans, including `bing`, `infoPath`, `sharePointDesigner` and `visio` as `false`; (b) the `assign` call accepts an
> assignment with only `intent` and `target` (no `settings`) for this app type; (c) `Unchanged` on the second run, which
> relies on Graph returning the same values we sent (if it normalises something, the module reports a permanent diff:
> fix `Compare-ADOfficeSuiteApp` before recording); (d) that the portal shows Monthly Enterprise Channel. If Graph rejects
> something, show the real error on camera and fix the module + tests.
> **Do not assign this app to the VM's group while Office is already installed by the ODT** unless you want to show what
> Intune does with an existing install: record the real result.

### 3. `screens/inventory.jpg` — "What is really installed" (**needs VM**)
On `CON-W11-01`: `./Invoke-AppsDeploy.ps1 -Inventory`. Capture the property list and the findings table exactly as it is.
On a fresh install of the file above, expect no findings, or `BuildBehind` if the CDN has published newer builds in between
(the module compares with the live release data). Optional split screen: regedit at
`HKLM\SOFTWARE\Microsoft\Office\ClickToRun\Inventory\Office\16.0` (`OfficePackageVersion`, `OfficeProductReleaseIds`) and
`HKLM\SOFTWARE\Microsoft\Office\ClickToRun\Configuration` (`CDNBaseUrl`, `UpdateChannel`).
To show a real finding without faking anything, use a real change: e.g. in `apps.lab.json` on the VM set `"officeClientEdition": "32"`
and run `-Inventory` (`ArchitectureMismatch`), then set it back. That changes only the expectation, not the machine.

### 4. `screens/activation.jpg` — "Who has activated what" (**needs tenant**)
On the host:
```powershell
Connect-MgGraph -Scopes Reports.Read.All -NoWelcome
./Invoke-AppsDeploy.ps1 -ActivationAudit -OutFile ./activation.lab.md
```
Capture the summary and table. The report lists users who activated; `alex.demo` appears once the report has refreshed after the
VM activation (Learn doesn't state the delay: record the next day if it isn't there yet). Only real findings are shown; an
honest "0 findings" is fine. Mask UPNs (and the hashed names if concealment is on).

## Masking checklist
- Tenant name/domain, admin UPN, user addresses beyond the lab aliases, the group Object Id, the CDN GUID is public (fine),
  device name `CON-W11-01` is a lab name (fine).
- `apps.lab.json` and `activation.lab.md` contain tenant data: don't show them in full, never commit them.

## Tear-down (before the trial ends on 20 Dec 2026)
1. Intune: delete the app *MG Lab - Microsoft 365 Apps (Monthly Enterprise)* (Apps > Windows) and the group `MG Lab - Intune Users`
   if no later episode needs it.
2. VM: uninstall Microsoft 365 Apps (Settings > Apps) or delete the VM if episode 7 is finished (see its tear-down). In the
   Microsoft 365 admin center, deactivate nothing manually: removing the licence or deleting the VM frees the activation.
3. Delete `apps.lab.json`, `activation.lab.md`, `C:\ODT`, `C:\mg`; `Disconnect-MgGraph`; remove the delegated consent granted only for the recording.
4. Restore any licence option you enabled for this recording.
