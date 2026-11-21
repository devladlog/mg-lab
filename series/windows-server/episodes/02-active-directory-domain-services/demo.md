# Demo shot list — DEVLADLOG Windows Server #2: Active Directory Domain Services

## Lab environment

Two parts, on the local Hyper-V lab of the recording laptop (`series/LAB.md`). No tenant, no Azure, no licence
(evaluation editions), cost 0.

**1. Promote screen (destructive, "from zero") → a throwaway VM, never CON-DC01.** Promoting a new forest can't be
recorded on the shared DC (it is already the DC of `lab.contoso.com`, and the script refuses to run on a DC anyway).

| VM | OS / edition | vCPU / RAM / disk | Network | Role / software |
|---|---|---|---|---|
| **CON-FOREST01** (throwaway, listed in `series/LAB-REQUESTS.md`) | Windows Server 2025 Datacenter Eval, Server Core | 2 / 2–3 GB dynamic / 60 GB (differencing disk on the lab base image is fine) | **Private** Hyper-V switch `MGLab-Isolated` only (no NAT, no host access), static IP **10.50.0.90/24**, no gateway, DNS 127.0.0.1 after promotion | Not domain-joined. Gets AD DS + DNS from `New-LabForest.ps1`. Deleted after the shot |

It promotes a forest with the same names as the shared lab (`lab.contoso.com` / NetBIOS `CONTOSO`) so the shot shows
how the shared domain was built. **Never connect CON-FOREST01 to `MGLab-NAT`**: two forests with the same name on one
network break name resolution for the shared VMs.

**2. Every other screen → the shared lab domain** `lab.contoso.com` (NetBIOS `CONTOSO`) on `10.50.0.0/24`:

| VM | Used for | Changes made for the recording |
|---|---|---|
| **CON-DC01** (10.50.0.10, Server Core) | provisioning, snapshot, hygiene report, lastLogon query | PowerShell 7 (MSI) installed; episode folder in `C:\lab\ep02`; OU tree `OU=Contoso`, 5 groups, 8 users from `src/users.csv`; `adm-alex` in Domain Admins (removed right after the report shot) |
| **CON-SRV02** (10.50.0.22, Desktop Experience) | the sign-in for the lastLogon gotcha | none (interactive sign-in as `CONTOSO\jgoncalves`) |

- Sign-in: the **lab Administrator** (`CONTOSO\Administrator` on the shared VMs, local Administrator on
  CON-FOREST01). The recorder types passwords; they are never written in a file or shown.
- The users created here are AD objects of the lab domain from the episode's fictional CSV (Alex Demo, João Gonçalves,
  …), not tenant accounts.
- Recording machine: the Windows lab laptop (Hyper-V host); screens are VMConnect windows of CON-FOREST01, CON-DC01
  and CON-SRV02.

Everything in `src/`, `setup/` and `tests/` already ran in the build container: 42 Pester tests (AD cmdlets mocked),
the offline report from the fictional snapshot (`sample/report.md`) and a parse/5.1-syntax check of
`New-LabForest.ps1`. **Nothing has run against a real domain controller yet.** Rewrite the narration of each screen
scene to what is actually on screen.

## Prepare (before recording)

1. **CON-FOREST01** (Hyper-V Manager or PowerShell on the laptop): create the Private switch
   (`New-VMSwitch -Name MGLab-Isolated -SwitchType Private`), create the VM from the lab's Windows Server 2025
   evaluation media/base disk, Server Core, name it `CON-FOREST01`, set the static IP above, and copy the episode
   folder in with PowerShell Direct:
   ```powershell
   $s = New-PSSession -VMName CON-FOREST01 -Credential (Get-Credential Administrator)
   Copy-Item -ToSession $s -Path .\series\windows-server\episodes\02-active-directory-domain-services -Destination C:\lab\ep02 -Recurse
   Invoke-Command -Session $s { Install-WindowsFeature AD-Domain-Services -IncludeManagementTools }   # so -WhatIf gets past the role check
   ```
2. **CON-DC01**: copy the episode folder to `C:\lab\ep02` and install PowerShell 7 from the MSI (Server Core has no
   `winget`), the same way (`New-PSSession -VMName CON-DC01 -Credential CONTOSO\Administrator`).

## Setup and screens (in recording order)

### 1. `screens/promote.jpg` — "Check first, then promote" (CON-FOREST01, throwaway)
On CON-FOREST01, elevated `powershell.exe`:
```powershell
cd C:\lab\ep02
.\setup\New-LabForest.ps1 -DomainName lab.contoso.com -NetbiosName CONTOSO -WhatIf
```
Capture: `ForestMode values accepted here: ...` and the `Test-ADDSForestInstallation` output (`Status : Success`).
- **Verify and note in README:** is `Win2025` in the accepted list? If not, re-run with `-FunctionalLevel` set to the
  highest listed value and change the narration (the scene is about *checking*, so either result works).

Then the real run (B-roll of the restart is enough), still on CON-FOREST01:
```powershell
.\setup\New-LabForest.ps1 -DomainName lab.contoso.com -NetbiosName CONTOSO
```
After the B-roll, shut down CON-FOREST01 and delete it (tear-down). The remaining screens use the shared domain.

### 2. `screens/provision.jpg` — "Run it twice" (CON-DC01)
In `pwsh` on CON-DC01:
```powershell
cd C:\lab\ep02
Import-Module .\src\AdLab\AdLab.psd1
$pw = Read-Host -AsSecureString 'Initial password'          # lab-only password, never shown on screen
$p = @{ CsvPath = '.\src\users.csv'; DomainDn = 'DC=lab,DC=contoso,DC=com'; UpnSuffix = 'lab.contoso.com'; InitialPassword = $pw }
Invoke-AdLabProvisioning @p | Group-Object Action, Type | Format-Table Count, Name     # Created OU 9, Group 5, User 8
Invoke-AdLabProvisioning @p | Group-Object Action, Type | Format-Table Count, Name     # Exists 22
```
Capture both tables in one frame. Optional: Active Directory Users and Computers on CON-SRV02
(`Install-WindowsFeature RSAT-ADDS-Tools`) showing the OU tree (B-roll).
- Verify: the Import-Module of `ActiveDirectory` works in PowerShell 7 on the DC (it's loaded by `Assert-AdLabModule`).
- If an earlier take left `OU=Contoso` in place, the first run shows `Exists`: remove it first (tear-down step 2).

### 3. Prepare the report data (before shot 4, not recorded)
```powershell
# a privileged account for the Tier 0 finding, and an orphaned adminCount
New-ADUser -Name 'adm-alex' -SamAccountName adm-alex -Path 'OU=IT,OU=Users,OU=Contoso,DC=lab,DC=contoso,DC=com' -AccountPassword $pw -Enabled $true
Add-ADGroupMember -Identity 'Domain Admins' -Members adm-alex
Add-ADGroupMember -Identity 'Domain Admins' -Members iferreira
# wait for SDProp (runs every 60 minutes by default on the PDC emulator), check adminCount=1 on iferreira, then:
Remove-ADGroupMember -Identity 'Domain Admins' -Members iferreira -Confirm:$false
```
(`Domain Admins` by name is fine in an English lab; the module itself uses SIDs.)

### 4. `screens/report.jpg` — "The lab domain, judged" (CON-DC01)
```powershell
.\src\Invoke-AdHygieneReport.ps1 -SnapshotFile .\lab-snapshot.json -OutFile .\ad-report.md   # live: exports the snapshot, saves it, reports
```
Expect (verify): `RecycleBin` Medium (unless the shared forest already has it enabled), `PasswordPolicy` Medium if the
default minimum length is below 14, `LockoutPolicy` if the threshold is 0, `PrivilegedGroup` for Domain
Admins/Administrators (adm-alex + Administrator is fine with `MaxTierZeroMembers = 1`), `OrphanedAdminCount` for
iferreira, `NeverUsed` won't appear (accounts are new). `KrbtgtPassword` depends on the age of the shared forest:
record what appears.
- Note in README the exact `DomainMode`/`ForestMode` strings the snapshot shows.
- **Right after this shot:** `Remove-ADGroupMember -Identity 'Domain Admins' -Members adm-alex -Confirm:$false`
  (no extra Tier 0 account stays in the shared domain).

### 5. `screens/lastlogon.jpg` — "Gotcha: lastLogonTimestamp isn't a stopwatch"
1. Sign in to **CON-SRV02** (VMConnect) as `CONTOSO\jgoncalves` (first sign-in forces the password change), sign out.
2. A few minutes later, sign in again.
3. On CON-DC01:
```powershell
Get-ADUser jgoncalves -Properties lastLogon, lastLogonTimestamp | Select-Object Name,
    @{ n = 'lastLogon (this DC)';       e = { [datetime]::FromFileTimeUtc($_.lastLogon) } },
    @{ n = 'lastLogonTimestamp (repl)'; e = { [datetime]::FromFileTimeUtc($_.lastLogonTimestamp) } } | Format-List
```
Expected: `lastLogon` = second sign-in, `lastLogonTimestamp` = first sign-in. If both match (e.g. S4U or other
activity updated it), record what you see and change the narration; the Learn reference stays valid.

### Optional B-roll: enable the Recycle Bin — **not on the shared forest**
Enabling the AD Recycle Bin is irreversible. Don't run it against `lab.contoso.com` on CON-DC01 just for B-roll (it
would also remove the `RecycleBin` finding from every later take). If you want the shot, record it on CON-FOREST01
before deleting it:
```powershell
Enable-ADOptionalFeature -Identity 'Recycle Bin Feature' -Scope ForestOrConfigurationSet -Target lab.contoso.com
```
Show the irreversible-change confirmation only.

## Masking
- Everything is fictional (`lab.contoso.com`, `CONTOSO`, CSV names). Keep it that way.
- Never type passwords on screen: always `Read-Host -AsSecureString`.
- Crop VMConnect title bars ("<VM> on <laptop name>") and hide the Windows user profile path.

## Tear-down
1. **CON-FOREST01**: `Stop-VM CON-FOREST01 -TurnOff; Remove-VM CON-FOREST01 -Force`, delete its VHDX, and remove the
   `MGLab-Isolated` switch if nothing else uses it.
2. **Shared domain**: keep `OU=Contoso` and the users if Windows Server #3 (Group Policy) is recorded next; otherwise
   on CON-DC01:
   ```powershell
   Get-ADOrganizationalUnit -SearchBase 'OU=Contoso,DC=lab,DC=contoso,DC=com' -Filter * |
       Set-ADObject -ProtectedFromAccidentalDeletion $false
   Remove-ADOrganizationalUnit -Identity 'OU=Contoso,DC=lab,DC=contoso,DC=com' -Recursive -Confirm:$false
   ```
   (removes the 8 users, 5 groups and `adm-alex`). Check that `Domain Admins` holds only the lab Administrator again.
3. Remove `lab-snapshot.json`, `ad-report.md` and `C:\lab\ep02` from CON-DC01. Sign out of CON-SRV02 and delete the
   `jgoncalves` profile there (`Get-CimInstance Win32_UserProfile | Where-Object LocalPath -like '*jgoncalves*' | Remove-CimInstance`).
