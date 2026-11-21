# Demo shot list: DEVLADLOG Deep Dive #9, Zero Trust network architecture

Code, test and Bicep scenes in `script.yaml` are real (from this folder). The four `screen` scenes need the lab.
**Status: needs tenant + Azure subscription + the Hyper-V Windows 11 VM.** Offline (container): 57 Pester tests pass,
`bicep build` and `bicep lint` are clean. **Not yet run against the tenant or Azure:** `Deploy-ZeroTrust.ps1`, the Bicep
deployment, `Test-PrivateAccess.ps1`, the Windows 11 enrolment and compliance result. Record each outcome in the README
("Not verified in the lab yet" lists what to check) and fix the narration if reality differs.

## Lab environment

Recorded on the **lab Windows laptop** (host): Edge for the Entra, Intune and Azure portals, Windows Terminal with PowerShell 7
for the scripts, Hyper-V Manager only off camera. Screens of Office 365 sign-in are produced **inside the VM** (see below).

**Hyper-V VM (existing, from `series/LAB.md`)**: `CON-W11-01`, Windows 11 Enterprise Evaluation (90 days) with vTPM, 2 vCPU /
4 GB, DHCP on the Hyper-V Default Switch (not the 10.50.0.0/24 lab network, it only needs internet). It stops at Windows setup:
**on camera or off, join it to Entra ID as `alex.demo`** (Setup for work or school > Sign in > the account joins Entra and, because of
the MDM user scope set below, enrols in Intune). Needs `E:\MGLab\iso\Win11Ent-Eval.iso`. No other VM is used; the shared
DC/SQL VMs are untouched.

**Microsoft 365 / Entra lab tenant** (E5 trial: Entra ID P2, Intune, Conditional Access): lab users `alex.demo` and
`sam.demo` (pilot), `labadmin` (recording account, Global Administrator). Created by the scripts:
two security groups `ct-zt-pilot` (add `alex.demo`, `sam.demo`) and `ct-zt-breakglass` (the lab's emergency account is
`labadmin`: add it; a real tenant uses two dedicated cloud-only accounts), three Conditional Access policies (report-only),
one Intune compliance policy. One tenant setting is changed by hand and **reverted in tear-down**: Entra admin center >
Mobility > Microsoft Intune > **MDM user scope = Some**, group `ct-zt-pilot` (Learn: automatic enrolment when a device joins Entra).
No new licences; no Defender for Endpoint.

**Azure** (lab subscription, one resource group `rg-mglab-deep-dive-09`, West Europe)

| Resource | SKU | Cost for the recording window |
|---|---|---|
| Virtual network `vnet-mgl09` 10.60.0.0/24, NSG `nsg-zerotrust-workloads` | n/a | free |
| Key Vault `kv-mgl09-<token>` | Standard, RBAC, soft delete 7 days | per-operation charges, cents for a recording ([pricing](https://azure.microsoft.com/pricing/details/key-vault/)) |
| Private endpoint `pe-keyvault-zerotrust` + private DNS zone `privatelink.vaultcore.azure.net` | n/a | hourly charge per endpoint plus data and a monthly zone fee: check [Private Link](https://azure.microsoft.com/pricing/details/private-link/) and [DNS](https://azure.microsoft.com/pricing/details/dns/) pricing on the day; delete the group the same day |
| VM `vm-mgl09-workload` | Ubuntu 24.04 LTS, `Standard_B1s`, StandardSSD OS disk, no public IP | per-hour while running: check [VM pricing](https://azure.microsoft.com/pricing/details/virtual-machines/linux/); run for the recording only |

Budget alert `mglab-monthly` (EUR 30) stays active. No Log Analytics, no Defender plans, no Bastion (run-command replaces SSH).
**Local tools on the laptop:** PowerShell 7.2+, module `Microsoft.Graph.Authentication`
(`Install-Module Microsoft.Graph.Authentication -Scope CurrentUser`), Azure CLI, Bicep CLI, `ssh-keygen`, the repo checked out.

## Setup (off camera)

1. **Tests first**
   ```powershell
   cd series/deep-dive/episodes/09-zero-trust-network-architecture
   Invoke-Pester ./tests          # expect Tests Passed: 57
   bicep build infra/main.bicep --stdout > $null; bicep lint infra/main.bicep
   ```
2. **MDM user scope and the VM.** Set the scope as above. Boot `CON-W11-01`, finish setup by joining Entra as `alex.demo`.
   Confirm in the Intune admin center that the device appears (Devices > Windows). Create the throwaway SSH key:
   `ssh-keygen -t ed25519 -f ./zt-lab -N ""` (never committed; delete in tear-down).
3. **Identity and device policies** (as `labadmin`)
   ```powershell
   Connect-MgGraph -Scopes Policy.ReadWrite.ConditionalAccess,Policy.Read.All,Group.ReadWrite.All,DeviceManagementConfiguration.ReadWrite.All,AuditLog.Read.All
   ./scripts/Deploy-ZeroTrust.ps1 -WhatIf
   ./scripts/Deploy-ZeroTrust.ps1
   ```
   Then add `alex.demo`, `sam.demo` to `ct-zt-pilot` and `labadmin` to `ct-zt-breakglass` (portal). **Check on first run and write into the README:**
   (a) the three policies are created in report-only (a 400 on CT002 means the `authenticationStrength` body shape needs changing);
   (b) the compliance policy is created and assigned; (c) the VM receives it (Devices > CON-W11-01 > Device compliance).
4. **Network and workload**
   ```bash
   az group create -n rg-mglab-deep-dive-09 -l westeurope
   az vm list-skus -l westeurope --size Standard_B1s -o table        # pick another size if restricted, pass -p vmSize=...
   az deployment group create -g rg-mglab-deep-dive-09 -f infra/main.bicep -p adminPublicKey="$(cat ./zt-lab.pub)" --query properties.outputs
   ```
   **Check and write into the README:** (a) the secret resource deploys with public access Disabled (if not, the secret is created by the
   VM with a role that has Secrets Officer, or by temporarily allowing your IP, and that is stated in the README); (b) the private endpoint
   connection shows *Approved*; (c) `Test-PrivateAccess.ps1` works end to end, including the VM's `10.60.0.x` answer.
5. **Dry run** the compliance story once: on the VM, sign in to `https://outlook.office.com` as `alex.demo` in Edge (interactive sign-in),
   sync the device (Settings > Accounts > Access work or school > Info > Sync), wait for Intune to report. Expected before BitLocker:
   the baseline reports BitLocker as not compliant and CT003 shows **Report-only: Failure**. If the VM is already compliant, the
   story changes: turn BitLocker off (`Disable-BitLocker`) for the "before" take, or delete the compliance assignment for a take
   that shows "no policy assigned counts as compliant".

## Screens to capture (1920x1080, browser zoom 100 %)

| Scene id | File | What must be on screen |
|---|---|---|
| `ca-screen` | `screens/ca-policies.jpg` | Entra admin center > Conditional Access > Policies: CT001, CT002, CT003, State "Report-only". Tenant name masked. |
| `intune-screen` | `screens/intune-compliance.jpg` | Intune admin center > Devices > CON-W11-01 > Device compliance > "CT Windows corporate baseline" > per-setting status with BitLocker "Not compliant" (take before enabling BitLocker). Serial number masked. |
| `signin-screen` | `screens/signin-report-only.jpg` | Take 1: Sign-in logs > the Office 365 sign-in of `alex.demo` > Report-only tab: CT003 Failure. Fix on the VM: `Enable-BitLocker -MountPoint C: -TpmProtector -UsedSpaceOnly` (elevated; restart if asked), sync, wait for Compliant. Take 2: next sign-in, CT003 Success. Take 3: terminal `Get-CaReportOnlyImpact -Hours 3` output. Log entries lag a few minutes. |
| `private-screen` | `screens/private-access.jpg` | Windows Terminal: `./scripts/Test-PrivateAccess.ps1 -ResourceGroup rg-mglab-deep-dive-09 -VaultName <vault> -VmName vm-mgl09-workload`. OUTSIDE: public IP address, Forbidden. INSIDE: `10.60.0.x`, "got a token", HTTP 200, `curl` to example.com fails. Second shot: portal Key Vault > Networking (public access Disabled) and Private endpoint connections (Approved). |

Order: policies in the portal, Intune (failing), sign-in log failure, fix and success, impact in terminal, then the network demo.

## Masking

Run `pipeline/mask.js` before portal captures. Mask tenant name and id, subscription id, vault name, user domain, device serial,
the VM's SSH public key and any object ids. The Graph token and the IMDS token are never printed (the scripts print only a length).

## Tear-down

```powershell
# Conditional Access policies and groups
# Remove the three CT* policies (Entra admin center > Conditional Access > Policies > Delete) or via Graph: DELETE /identity/conditionalAccess/policies/{id}
# Intune: delete the policy "CT Windows corporate baseline"; retire/delete CON-W11-01 in Intune and Entra if the VM is rebuilt
# Entra: delete groups ct-zt-pilot and ct-zt-breakglass; set MDM user scope back to what it was (None)
az group delete -n rg-mglab-deep-dive-09 --yes
az keyvault list-deleted -o table
az keyvault purge --name <vault name> --location westeurope        # soft-deleted vault names stay reserved for 7 days otherwise
Remove-Item ./zt-lab, ./zt-lab.pub
Disconnect-MgGraph
```

The private DNS zone, private endpoint, NSG, network and VM are all in the group and go with it. Confirm in the portal that
the resource group is gone and that no policy named CT0* is left.
