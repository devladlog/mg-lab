# MG Lab – local Hyper-V lab

Real VMs for the DEVLADLOG demos (Windows Server, Active Directory, SQL Server), built on the recording laptop.

## What it builds
- Internal NAT network `MGLab-NAT` 10.50.0.0/24 (host 10.50.0.1), with internet access for the VMs.
- Windows Server 2025 Datacenter **evaluation** VMs (180 days) on differencing disks from two base images
  (Server Core and Desktop Experience), so each VM only stores its own changes.
- `CON-DC01` (AD DS + DNS for `lab.contoso.com`), `CON-SRV01`, `CON-SRV02` (Desktop Experience),
  `CON-SQL01` with SQL Server 2022 **Developer** edition.
- All files go to `E:\MGLab` (`LabRoot` in `lab.config.psd1`; `auto` = the fixed drive with the most free space).

## Run it
Easiest: double-click **`Run-MGLab.cmd`** and approve the administrator prompt. Or by hand:

In **Windows PowerShell as Administrator** (right-click → Run as administrator):
```powershell
cd D:\momento_galatico_kit\mg-lab-build\lab\hyperv
Set-ExecutionPolicy -Scope Process Bypass -Force
.\Start-MGLab.ps1 -CheckOnly     # shows the drive and RAM plan, changes nothing
.\Start-MGLab.ps1                # first run enables Hyper-V and asks for a restart; run again after it
```
The second run downloads the media (~6 GB server ISO, ~1.1 GB SQL), builds the base disks and VMs, the domain and
SQL. Expect 60–90 minutes the first time. Re-running is safe; finished stages are skipped.

## Password
Generated on your PC and stored encrypted for your Windows user only in `<LabRoot>\secrets\lab-admin.xml`.
It's never printed or sent anywhere. To see it:
`(Import-Clixml E:\MGLab\secrets\lab-admin.xml).GetNetworkCredential().Password`

## Windows 11 client (Intune episode)
`CON-W11-01` is a Windows 11 Enterprise evaluation VM with a virtual TPM on Hyper-V's built-in `Default Switch`
(DHCP + internet). Download the x64 ISO from microsoft.com/evalcenter → Windows 11 Enterprise (registration needed) and
save it as `E:\MGLab\iso\Win11Ent-Eval.iso`, then run `Run-MGLab.cmd` again. The VM stops at Windows setup on purpose:
the Entra join and Intune enrolment are done there as part of the recording. Without the ISO the VM is simply skipped.

## Daily use
- Free RAM after recording: `.\Stop-MGLab.ps1`. Start again: `.\Stop-MGLab.ps1 -Start`.
- Connect: `mstsc /v:10.50.0.22` (GUI server), `Enter-PSSession -VMName CON-DC01 -Credential CONTOSO\Administrator`,
  SQL: `10.50.0.30,1433` from SSMS / VS Code on the laptop.
- Evaluation copies must be activated online in the first 10 days (they have internet through the NAT). They run
  180 days and can be re-armed with `slmgr /rearm`.

## Notes
- Needs Windows 11 Pro/Enterprise/Education with virtualization on in the BIOS.
- The SQL Developer key (22222-00000-00000-00000-00000) is the free non-production edition.
- Episodes that record a "from zero" step (e.g. promoting a new forest) use a throwaway VM, not these.
