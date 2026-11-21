# Demo shot list: DEVLADLOG Deep Dive #17, Cloud migration platform (Azure Migrate + Site Recovery)

Code, test and Bicep scenes in `script.yaml` are real (from this folder). The four `screen` scenes need the lab.
**Status: needs the Azure subscription and the lab VMs.** Offline (container): 58 pytest tests pass (Bicep compiled and linted, the PowerShell collector
parsed, run with `-FromFacts` and tested with 9 Pester tests). **Not yet run:** the collector on the real VMs, the Bicep deployment, the Azure Migrate import,
the assessment, Site Recovery replication, test failover and the gate against a real vault. Record each outcome in the README ("Not verified" lists what to
check) and correct the narration of the screen scenes if reality differs.

## Lab environment

Recorded on the **lab Windows laptop** (host): Windows Terminal with PowerShell 7 (Azure CLI, Python 3.10+), Edge for the Azure portal.
**No new Hyper-V VM is needed.** The collector runs against the existing lab VMs `CON-DC01`, `CON-SRV01`, `CON-SRV02`, `CON-SQL01`, `CON-SQL02` and
`CON-CLI01` (10.50.0.0/24, domain `lab.contoso.com`) over PowerShell remoting as the lab Administrator (`labadmin` signs in to Azure; the Windows
credential is typed at the prompt, never saved). No Power Platform environment, no Microsoft 365 licence. The only Azure account used is `labadmin`
(Owner on the lab subscription). If you later want a real Azure Migrate appliance (not in this episode: Learn's agent-based replication appliance
needs 8 vCPU, 16 GB RAM and a 600 GB cache disk), add a throwaway VM `CON-MIG01` at `10.50.0.46` (free address) and record it here.

**Azure** (lab subscription; two resource groups, deleted at the end)

| Resource | SKU | Cost for the recording window |
|---|---|---|
| Azure Migrate project (in `rg-mglab-deep-dive-17`, geography Europe) with the Discovery and assessment tool | n/a | not verified: check the [Azure Migrate pricing page](https://azure.microsoft.com/pricing/details/azure-migrate/) before the recording |
| Test VM `con-app01`, West Europe (+ OS disk StandardSSD_LRS, NIC, VNet `10.60.0.0/16`, NSG) | **Standard_D2s_v5** (2 vCPU, 8 GiB), Windows Server 2022 g2, no public IP | billed per hour while running: [VM pricing](https://azure.microsoft.com/pricing/details/virtual-machines/windows/). Deallocate it when not recording |
| Recovery Services vault `rsv-mglab-dr`, North Europe (`rg-mglab-deep-dive-17-dr`) + target VNet `10.61.0.0/16` | **RS0**, Standard | vault: see the [Site Recovery pricing page](https://azure.microsoft.com/pricing/details/site-recovery/) |
| Site Recovery protection of one Azure VM | per protected instance | free for the first 31 days (Learn pricing page); replica disks, cache storage and transfer are billed; test-failover VM compute is billed while it exists |
| Test-failover VM (temporary, North Europe) | same size as the source | delete it with **Cleanup test failover** straight after the capture |

Site Recovery also creates a cache storage account and a target resource group for the replica disks (a default name is proposed; accept it or pick
`rg-mglab-deep-dive-17-dr`). **Check the group list at the end**: every group whose name starts with `rg-mglab-deep-dive-17`, plus anything Site Recovery
added, must be gone. Budget alert `mglab-monthly` (EUR 30) stays active. No Log Analytics, no Defender plans, no public IP, no Bastion
(you reach the VM through the portal's serial console or run-command only if needed; nothing is exposed).

**Local tools:** Azure CLI, Bicep CLI, Python 3.10+ with `pip install -r requirements.txt`, PowerShell 7, the repo checked out.

## Prerequisites

- Lab subscription, `labadmin` signed in to the Azure CLI and portal (off camera). Providers: `az provider register --namespace Microsoft.Migrate`,
  `Microsoft.RecoveryServices`, `Microsoft.Compute`, `Microsoft.Network`.
- Size check: `az vm list-skus -l westeurope --size Standard_D2s_v5 -o table` (pass `-p vmSize=...` if restricted).
- Learn's prerequisites for A2A: the VM can reach the Site Recovery service endpoints (the default outbound access is enough in this lab);
  Windows VMs need the latest Windows updates for current root certificates.

## Setup (off camera)

1. **Tests first**
   ```powershell
   cd series/deep-dive/episodes/17-cloud-migration-platform
   python -m pytest -q                       # expect 58 passed
   ```
2. **Collect the real lab inventory** (needs lab; first run of `Get-LocalServerFacts`)
   ```powershell
   $cred = Get-Credential                    # lab Administrator, typed, not saved
   ./scripts/Get-ServerInventory.ps1 -ComputerName CON-DC01,CON-SRV01,CON-SRV02,CON-SQL01,CON-SQL02,CON-CLI01 -Credential $cred -OutFile build/lab-inventory.json
   ```
   **Check and write into the README:** does it work on Server Core (`Get-NetTCPConnection`, `Get-Counter`, `Get-ComputerInfo`)? Are CON-SQL01 and
   CON-SRV02 connected on 1433/5985 and does the planner group them sensibly? Set `-Role`/`-Criticality` per server if you want roles (run once per role).
3. **Merge with the fictional CMDB and write the import file** (the lab VMs are the real rows, the Contoso rows are fictional)
   ```powershell
   python -c "import json;a=json.load(open('build/lab-inventory.json'));b=json.load(open('data/contoso-cmdb.json'));print(json.dumps({'servers':a['servers']+b['servers'],'connections':a['connections']+b['connections']}))" > build/all.json
   cd src
   python -m migplan check ../build/all.json --landing-zone 10.60.0.0/16
   python -m migplan plan  ../build/all.json
   python -m migplan csv   ../build/all.json --out ../build/import.csv
   ```
4. **Deploy the landing zone**
   ```powershell
   $env:MGLAB_VM_ADMIN_PASSWORD = Read-Host -MaskInput "VM admin password"
   az deployment sub create -l westeurope -n mglab17 -f infra/main.bicep -p infra/main.bicepparam --query properties.outputs -o json
   ```
   **Check:** the deployment succeeds and the time it took; the VM is running; the vault is in North Europe.
5. **Azure Migrate project** (portal, Learn: Azure Migrate > Create project, resource group `rg-mglab-deep-dive-17`, geography Europe). Discover >
   **Import using CSV** > upload `build/import.csv`. **Check:** status Completed or the warnings (download the warning CSV and write what it says).
6. **Assessment** (portal): Assess > Azure VM > discovery source **Imported servers**, target location West Europe. Create one with sizing criteria
   **as-is** and one **performance-based**. Write down the comfort factor shown in the assessment properties (the README says the default is unverified).
7. **Enable replication** (portal, Learn A2A tutorial): VM `con-app01` > Operations > Disaster recovery > target region **North Europe**, use the existing vault
   `rsv-mglab-dr` and target network `vnet-target` in Advanced settings. Wait for initial replication to finish (note the time in the README).
8. **Fetch the protected items for the gate** (the api-version is from the REST reference; newer versions exist)
   ```powershell
   $sub = az account show --query id -o tsv
   az rest --method get --url "https://management.azure.com/subscriptions/$sub/resourceGroups/rg-mglab-deep-dive-17-dr/providers/Microsoft.RecoveryServices/vaults/rsv-mglab-dr/replicationProtectedItems?api-version=2025-08-01" > build/items.json
   cd src ; python -m migplan gate ../build/items.json
   ```
   **Check:** the JSON has the fields the gate reads (`properties.replicationHealth`, `allowedOperations`, `providerSpecificDetails.rpoInSeconds`,
   `lastRpoCalculatedTime`, `lastSuccessfulTestFailoverTime`). If `items.json` is empty or the list needs the fabric and container in the path, use the
   path from the REST reference and fix `README.md`. Before a test failover the gate must say NOT READY (no successful test failover): capture that too.
9. **Test failover** (portal, Learn drill tutorial): choose a non-production target network (`vnet-target`), latest recovery point. When the job succeeds,
   run the gate again (expect READY once the RPO is fresh), then **Cleanup test failover**.

## Screens to capture (1920x1080, browser zoom 100 %, terminal font large)

| Scene | Capture | File |
|---|---|---|
| `import-screen` | Azure Migrate > Discovery and assessment > Discovered servers > Import based tab, import status Completed | `screens/import.jpg` |
| `assessment-screen` | The Azure VM assessment summary (readiness counts, monthly estimate) and the readiness tab with recommended sizes | `screens/assessment.jpg` |
| `replication-screen` | Vault > Replicated items > `con-app01` > Overview: health, status Protected, RPO and time computed, Failover readiness | `screens/replication.jpg` |
| `failover-screen` | Split: portal test failover job succeeded + terminal `python -m migplan gate items.json` output | `screens/failover.jpg` |

State in the narration what you actually saw (counts, RPO, durations). If the gate says NOT READY, show that and say why.

## Masking

Run `pipeline/mask.js` before portal captures. Mask the subscription id, tenant id and name, resource ids, the vault's resource id and any storage account
name. The Windows credential and the VM password are never on screen (prompted, `-MaskInput`). Mask real lab VM IP addresses only if you want to hide
the 10.50.0.0/24 plan; they are fictional anyway. No kubeconfig, token or access key exists in this episode.

## Tear-down

```powershell
# 1. stop protection first (Learn: this stops Site Recovery billing for the VM)
#    portal: VM con-app01 > Disaster recovery > Disable Replication ; also remove the Site Recovery extension if you reuse the VM
# 2. delete every group of the episode
az group list --query "[?starts_with(name,'rg-mglab-deep-dive-17')].name" -o tsv
az group delete -n rg-mglab-deep-dive-17 --yes
az group delete -n rg-mglab-deep-dive-17-dr --yes
# if the vault refuses to delete, remove the replicated items and the Site Recovery configuration first, then retry
# 3. local files
Remove-Item build -Recurse -ErrorAction SilentlyContinue
Remove-Item Env:MGLAB_VM_ADMIN_PASSWORD
```

Then list the groups again: also delete any group Site Recovery created for the replica disks if its name starts differently (check each group's resources
before deleting). Confirm in the portal that the Azure Migrate project is gone with its group. No Entra objects, licences or tenant settings are created
in this episode; the Windows credential was never stored.
