# Demo shot list — DEVLADLOG Microsoft 365 #7: Intune & Device Management

Everything in `src/` and `tests/` already ran in the build container (58 Pester tests, offline audit from a fictional
device list). This file lists what the human-supervised session must set up and record in the **lab tenant** with a
**real Windows 11 VM**. Every Graph call below is **needs tenant**; every screen shows the real product: the real
Intune admin center, the real VM, the module talking to the real Graph. The fixture (`tests/fixtures/devices.json`) is
for the automated tests only and never appears on screen.

## Lab environment

Recorded on the **lab Windows desktop** (Hyper-V host): VM console (VMConnect), a browser on the lab tenant
(Intune admin center, Entra admin center) and PowerShell 7 on the host.

**New VM** (also listed in `series/LAB-REQUESTS.md`):

| Item | Value |
|---|---|
| Name | `CON-W11-01` |
| OS | Windows 11 Enterprise **evaluation** (Microsoft Evaluation Center ISO, English). Not Home: Learn says Windows Home doesn't support Microsoft Entra join. The evaluation period is limited: check the download page for the current length, and create the VM shortly before recording |
| Hyper-V | **Generation 2**, Secure Boot **on**, **virtual TPM** enabled (Learn, Windows 11 requirements: generation 2, ≥ 64 GB, ≥ 4 GB, ≥ 2 vCPU, Secure Boot capable, vTPM) |
| Size | **2 vCPU / 4 GB static RAM / 64 GB** dynamically expanding VHDX (the laptop has 191 GB RAM, so RAM is not a constraint) |
| Network | `MGLab-NAT`, static `10.50.0.42/24`, gateway `10.50.0.1` (free range 10.50.0.40–99; `.41` is CON-CLI01). The VM needs **outbound HTTPS to the internet** (Entra, Intune, the Azure attestation endpoints for the device-health checks). It is **not domain-joined** to `lab.contoso.com`: it is **Microsoft Entra joined** |
| Identity | Joined as the lab user `alex.demo` (display name "Alex Demo"). Learn: the user who performs the join becomes local administrator, so Alex can run the elevated BitLocker commands |
| Software | None extra. Windows PowerShell and the BitLocker module ship with Windows |
| Lifetime | Created before the recording, deleted after (tear-down 3) |

| Cloud item | Notes | Cost |
|---|---|---|
| Intune licence | Intune comes with Microsoft 365 E3/E5 (Learn: *Microsoft Intune licensing*). Confirm: Intune admin center → Tenant administration → Tenant status → Tenant details: **Total Intune licenses** > 0 and the MDM authority shown. If it isn't included in the lab's E5 trial, start the Intune free trial (Learn: *Intune free trial sign-up*) | in the lab |
| Entra ID P1/P2 | Needed for automatic enrollment and for Conditional Access; included in E5 | in the lab |
| Lab users | `alex.demo` (joins the VM), `sam.demo`, both with E5 (includes Intune) | none |
| Group (created in setup) | **MG Lab - Intune Users** (security group, assigned membership: alex.demo, sam.demo). Used for the MDM user scope and as the compliance policy's assignment | none |
| Graph scopes (delegated, consent for `labadmin`) | `DeviceManagementConfiguration.ReadWrite.All`, `DeviceManagementManagedDevices.Read.All`, `DeviceManagementManagedDevices.PrivilegedOperations.All` | none |
| Roles | `labadmin` as Intune Administrator (or Global Administrator) | none |
| Host PowerShell | PowerShell 7.2+, `Install-Module Microsoft.Graph.Authentication -Scope CurrentUser` | none |

## Setup (before recording)

1. **Group.** Entra admin center → Groups → New group: Security, name `MG Lab - Intune Users`, add alex.demo and
   sam.demo. Copy the group's **Object Id**.
2. **Automatic enrollment.** Entra admin center → Mobility (MDM and MAM) → **Microsoft Intune** → **MDM user scope**:
   *Some* → the group above; MAM user scope: None; Save. (Learn: with MDM user scope Some/All, joining a device to Entra
   ID also enrolls it in Intune.)
3. **Check the guard rails.** Entra → Devices → Device settings: *Users may join devices to Microsoft Entra* = All (or
   the group), *Maximum number of devices per user* = default 50. Intune → Devices → Enrollment → device platform
   restrictions: Windows (MDM) allowed. Learn: if enrollment restrictions block personal Windows devices, the
   join-and-enroll flow doesn't complete.
4. **Build the VM** (host, elevated PowerShell; adjust paths):
```powershell
$vm = 'CON-W11-01'
New-VM -Name $vm -Generation 2 -MemoryStartupBytes 4GB -NewVHDPath "E:\MGLab\$vm\$vm.vhdx" -NewVHDSizeBytes 64GB -SwitchName 'MGLab-NAT'
Set-VMProcessor -VMName $vm -Count 2
Set-VMMemory -VMName $vm -DynamicMemoryEnabled $false
Set-VMFirmware -VMName $vm -EnableSecureBoot On
Set-VMKeyProtector -VMName $vm -NewLocalKeyProtector
Enable-VMTPM -VMName $vm
Add-VMDvdDrive -VMName $vm -Path 'E:\ISO\Windows11_Enterprise_Eval.iso'
Set-VMFirmware -VMName $vm -FirstBootDevice (Get-VMDvdDrive -VMName $vm)
Start-VM -Name $vm
```
5. **Install and join.** Install Windows 11 Enterprise. At *How would you like to set up this device?* choose **Set up
   for work or school** and sign in as `alex.demo` (the recorder types the lab password; MFA registration, if the tenant
   asks for it, is done before recording). Inside the VM set the static IP. Verify: Settings → Accounts → **Access work
   or school** shows the organization connection (Learn: *Microsoft Entra join a new Windows device during OOBE*).
6. **Config file.** Copy `src/intune.json` to `intune.lab.json` (keep it out of the repo) and replace
   `assignTo.groupId` with the group's Object Id. Do not commit it.
7. **Dry run, off camera:** `./Invoke-IntuneDevices.ps1 -PolicyFile ./intune.lab.json -Audit` against the empty policy
   state, to confirm the VM is listed and the Graph consent is in place.

## Screens to capture (match `script.yaml` screen scenes)

### 1. `screens/enroll.jpg` — "A real device, enrolled" (**needs tenant + VM**)
1. VMConnect on `CON-W11-01`: Settings → Accounts → Access work or school (connected to the organization).
2. Intune admin center → Devices → **Windows**: `CON-W11-01`, primary user Alex Demo, ownership Corporate, the compliance
   value as it really is (often *Not evaluated* before a policy is assigned; with the tenant default it may say
   *Compliant*; read it, don't assume). Allow a few minutes after the join for the device to appear.
3. Mask the tenant name, the UPN domain, the device's Entra ID and serial number.

### 2. `screens/apply.jpg` — "Apply it, then look in the portal" (**needs tenant**, creates a policy)
```powershell
Connect-MgGraph -Scopes DeviceManagementConfiguration.ReadWrite.All -NoWelcome
./Invoke-IntuneDevices.ps1 -PolicyFile ./intune.lab.json -ApplyPolicy -WhatIf     # WhatIf-Create
./Invoke-IntuneDevices.ps1 -PolicyFile ./intune.lab.json -ApplyPolicy             # Created (confirm)
./Invoke-IntuneDevices.ps1 -PolicyFile ./intune.lab.json -ApplyPolicy             # Unchanged
```
Then Intune admin center → Devices → Compliance → *MG Lab - Windows 11 baseline* → Properties: settings as in the file,
**Actions for noncompliance** (the grace period of the *Mark device noncompliant* action; the module sends `block` with
`gracePeriodHours` 24: confirm the portal shows 1 day, because Learn doesn't spell out the mapping), **Assignments**:
MG Lab - Intune Users. Optional second pass to show the update path: change `passwordMinimumLength` to 12 and
`gracePeriodHours` to 48 in `intune.lab.json`, `-ApplyPolicy -WhatIf` (row `WhatIf-Update`, changes listed), apply, and
refresh the portal; set both back afterwards.

> **Verify on first run (not confirmable from Learn):** the create call sends `scheduledActionsForRule` inside the POST
> body, and omits `notificationTemplateId` on a `block` action. If Graph rejects either, fix `ConvertTo-IDCompliancePolicyBody`
> / `Set-IntuneCompliancePolicy` before recording and re-run the tests.

### 3. `screens/device.jpg` — "What the device really reports" (**needs tenant + VM**)
1. VM, elevated PowerShell: `Get-BitLockerVolume -MountPoint C:` (not protected on a fresh install, unless Windows turned
   on device encryption by itself: show what is real).
2. Sync: on the VM Settings → Accounts → Access work or school → *(the organization)* → Info → **Sync**, or from the host
   `./Invoke-IntuneDevices.ps1 -PolicyFile ./intune.lab.json -SyncDeviceName CON-W11-01` (needs the
   `…PrivilegedOperations.All` scope).
3. Intune admin center → Devices → Windows → CON-W11-01 → **Device compliance** (policy state and the setting that
   fails). Learn: the BitLocker and other device-health settings come from Device Health Attestation / Azure
   attestation, so allow several minutes and a second sync.
4. Fix on the VM (Learn: BitLocker operations guide, `Enable-BitLocker`):
```powershell
Add-BitLockerKeyProtector -MountPoint C: -RecoveryPasswordProtector       # never show the recovery password on screen
Enable-BitLocker -MountPoint C: -EncryptionMethod XtsAes256 -UsedSpaceOnly -TpmProtector
Restart-Computer
```
   After the restart (and the encryption pass) sync again and capture the new compliance state. Learn: the BitLocker
   health setting is only measured at boot, so a restart is needed. **Rewrite the narration to the real states and the
   real failing settings** (they may include Secure Boot, code integrity or the OS build: record what Intune reports).
5. If a setting stays red for a reason outside the episode, say so on camera rather than editing the policy to hide it.

### 4. `screens/audit.jpg` — "Audit the whole fleet" (**needs tenant**)
```powershell
Connect-MgGraph -Scopes DeviceManagementManagedDevices.Read.All -NoWelcome
./Invoke-IntuneDevices.ps1 -PolicyFile ./intune.lab.json -Audit -OutFile ./audit.lab.md
```
Capture the state table and the findings for the devices that really exist in the lab (at least `CON-W11-01`). Do not
add fake devices. If you want a second finding on camera, create it for real, for example a second enrollment of the
same VM (leaves two records with one serial, so `DuplicateSerial`), or just report an empty result honestly.
Rewrite the narration to the real findings and counts. Mask UPNs, device serials and the tenant domain.

### Optional insert for the "Three things Microsoft documents" scene
Intune admin center → Endpoint security → Device compliance → **Compliance policy settings**: show *Mark devices with no
compliance policy assigned as* (default *Compliant*). Capture only; changing it affects every lab device.

## Masking checklist
- Tenant name/domain, admin UPN, user addresses beyond the lab aliases, device serial numbers, Entra device IDs, the
  group object id, the BitLocker recovery password and key ID.
- `intune.lab.json` and `audit.lab.md` contain tenant data: don't show them in full, never commit them.

## Tear-down (before the trial ends on 20 Dec 2026)
1. Intune: delete the policy *MG Lab - Windows 11 baseline* (Devices → Compliance) and, if no later episode needs it, the
   group `MG Lab - Intune Users`; set the MDM user scope back to None.
2. Retire/delete `CON-W11-01` in Intune (Devices → Windows) and delete its device object in Entra (Devices → All devices).
   (Learn: back up BitLocker recovery keys before deleting a device that matters; this one doesn't.)
3. Host: `Stop-VM CON-W11-01 -TurnOff; Remove-VM CON-W11-01 -Force`, delete `E:\MGLab\CON-W11-01`.
4. Delete `intune.lab.json`, `audit.lab.md`; `Disconnect-MgGraph`; remove the delegated consent granted only for the recording.
