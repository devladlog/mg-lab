# DEVLADLOG Deep Dive #17: Cloud migration platform (Azure Migrate and Site Recovery)

Contoso's data centre lease is ending and fourteen servers have to move. Two questions decide the project: **in what order**, and
**can we fail over safely**. This episode builds the tooling around both: a PowerShell collector and a Python planner that prepare
the inventory for **Azure Migrate** and group servers into waves by their network dependencies, a Bicep landing zone, and a
readiness **gate** that reads **Azure Site Recovery** (Azure to Azure) and says whether a machine is ready to fail over.

```
PowerShell collector ─► inventory.json ◄─ fictional Contoso CMDB (data/contoso-cmdb.json)
                              │ python -m migplan check | plan | csv
                              ▼
        Azure Migrate import CSV (headers = Microsoft's template) ─► Azure Migrate project ─► Azure VM assessment
                              │
                              ▼ waves: foundation (shared services) ► pilot ► waves by dependency group
   source VNet 10.60.0.0/16 (West Europe): private-only test VM  ──Site Recovery A2A──►  vault + VNet 10.61.0.0/16 (North Europe)
                              │                                            │
                              └── az rest …/replicationProtectedItems ──► python -m migplan gate  (READY / NOT READY)
```

| Path | What it is |
|---|---|
| [`scripts/Inventory.psm1`](scripts/Inventory.psm1), [`Get-ServerInventory.ps1`](scripts/Get-ServerInventory.ps1) | Collector for Windows servers: CIM facts, firmware type, utilisation sample, established TCP connections. Converters are pure functions; `Get-LocalServerFacts` is the only part that touches the machine. `-FromFacts` converts saved facts (runs on Linux) |
| [`src/migplan/inventory.py`](src/migplan/inventory.py) | Inventory model and dependency edges (infrastructure ports ignored) |
| [`src/migplan/readiness.py`](src/migplan/readiness.py) | Pre-flight checks: required CSV fields, OS name against Learn's supported list, end-of-support warning, disk limit, address overlap with the landing zone |
| [`src/migplan/sizing.py`](src/migplan/sizing.py) | First-guess VM size (as-is and performance-based with a comfort factor) from the Dsv5/Esv5 specs on Learn |
| [`src/migplan/waves.py`](src/migplan/waves.py) | Foundation, pilot and waves from dependency groups; blocked servers and oversized groups are reported |
| [`src/migplan/migrate_csv.py`](src/migplan/migrate_csv.py) | Writes the Azure Migrate import CSV (UTF-8 BOM, CRLF); extra disks follow the template's column pattern |
| [`src/migplan/drgate.py`](src/migplan/drgate.py) | Failover gate over the Site Recovery `replicationProtectedItems` list |
| [`data/contoso-cmdb.json`](data/contoso-cmdb.json) | Fictional 14-server Contoso inventory with connections, roles, criticality (one blocker, three end-of-support servers) |
| [`data/import-template-headers.txt`](data/import-template-headers.txt) | The header row of Microsoft's import template (downloaded from the link on Learn) |
| [`infra/main.bicep`](infra/main.bicep), [`modules/`](infra/modules), [`main.bicepparam`](infra/main.bicepparam) | Subscription-scope landing zone: source RG + VNet + NSG + private-only Windows Server 2022 VM; DR RG + Recovery Services vault + target VNet |
| [`tests/`](tests) | 58 pytest tests (including Bicep contracts and the PowerShell round trip) and 9 Pester tests |

```bash
cd src
python3 -m migplan check ../data/contoso-cmdb.json --landing-zone 10.60.0.0/16   # findings + first size guess; exit 1 on a blocker
python3 -m migplan plan  ../data/contoso-cmdb.json                              # foundation, pilot, waves
python3 -m migplan csv   ../data/contoso-cmdb.json --out import.csv             # servers without blockers
python3 -m migplan gate  items.json                                             # READY / NOT READY from az rest output
```

## Test locally (no Azure, no tenant)

```bash
pip install -r requirements.txt
python3 -m pytest -q                         # 58 passed (about 10 s)
```

The pytest run needs `bicep` and `pwsh` (PowerShell 7) on the PATH; those tests skip if they are missing. The PowerShell test also runs
the Pester suite ([`tests/Inventory.Tests.ps1`](tests/Inventory.Tests.ps1), 9 tests, Pester 6.2.0 in the build container; set
`PESTER_MODULE` to a `Pester.psd1` if it is not installed). Also clean: `bicep build infra/main.bicep` and `bicep lint infra/main.bicep`.

What is proven, and what is not:

- **Proven offline:** the planner logic, the CSV (headers identical to the template, BOM, CRLF, mandatory columns filled), the gate (each check failing
  alone), the Bicep contracts (regions differ, address spaces do not overlap each other or `10.50.0.0/24`, no public IP, no inbound rule from the
  internet, `adminPassword` is a secure parameter without a default, no real GUIDs or tenant names), and that the collector's JSON feeds the planner.
- **Not proven offline:** `Get-LocalServerFacts` (needs Windows: CIM, `Get-NetTCPConnection`, `Get-Counter`, `Get-ComputerInfo`); the Bicep deployment;
  that the VM image and size are accepted by Site Recovery; the gate against a real vault (its fixtures are shaped after the REST reference, not captured
  from a vault). See "Not verified" below.

## Deploy and run (needs the lab Azure subscription)

Runbook, costs, masking and tear-down in [`demo.md`](demo.md). Short version:

```powershell
$env:MGLAB_VM_ADMIN_PASSWORD = Read-Host -MaskInput "VM admin password"       # never written to a file
az deployment sub create -l westeurope -n mglab17 -f infra/main.bicep -p infra/main.bicepparam
```

## What we learned / gotchas

- **Imported servers cannot be migrated.** Learn (import tutorial): "You can't migrate servers imported using a CSV file". The import is for assessment and
  business cases; migrating needs the appliance (discovery) and a replication method.
- **Mandatory CSV columns** are Server name, Cores, Memory (In MB) and OS name. OS names must contain one of the names on Learn's list. Learn lists Windows Server
  2008, 2008 R2, 2012 and 2012 R2 as end of support: they import fine, but plan the upgrade. Up to 20,000 servers and 20 disks per server.
- **The domain controller trap.** If every connection counts, every domain member depends on the domain controller and the whole estate becomes one group.
  `INFRA_PORTS` (DNS, Kerberos, LDAP, SMB, RPC, remoting, time) are ignored and shared services form a foundation step. A test proves that without the
  filter one group of at least 13 servers appears.
- **Sizing depends on the assessment settings.** Learn: as-is sizing uses allocated cores and memory; performance-based uses used resources times a comfort
  factor. With an imported CSV, utilisation you type is used, and servers without it are sized as-is. `sizing.py` uses **1.3**, the value in Learn's example;
  the assessment's default was not verified. Treat `sizing.py` as an early guess; the real assessment also looks at disks, IOPS and more.
- **Site Recovery A2A vault region.** Learn: create the vault in any region except the source region. The Bicep puts it in North Europe. Vaults in
  South Central India and North East US 5 are not supported for A2A.
- **Billing.** Learn pricing page: each protected instance is free for the first 31 days; storage, transfer and test-failover compute are still billed.
  Disabling replication stops Site Recovery billing for the VM (Learn quickstart, clean-up section). A crash-consistent recovery point is taken every five minutes
  (not configurable) and kept 24 hours by default (Learn tutorial).
- **The gate's thresholds are ours.** 15 minutes RPO, 60 minutes since the RPO was calculated, 90 days since a successful test failover. The field names
  (`replicationHealth`, `allowedOperations`, `lastSuccessfulTestFailoverTime`, `providerSpecificDetails.rpoInSeconds` and `.lastRpoCalculatedTime`) come from the REST reference.
- **The connection list is a snapshot.** `Get-NetTCPConnection -State Established` shows what is connected at that moment. Run the collector repeatedly (a
  month-end batch job will not show up on a quiet afternoon) or use Azure Migrate's dependency analysis for real data.
- **Not here:** the agent-based replication appliance (Learn: 8 vCPU, 16 GB RAM, 600 GB cache disk) is too heavy for the laptop lab, so there is no on-premises
  to Azure replication in this episode. The Site Recovery part is Azure to Azure; the migration half stops at assessment.

## Not verified (needs the lab or a tenant)

- The Bicep deployment (`az deployment sub create`), including the `2022-datacenter-g2` image with `Standard_D2s_v5`, and Site Recovery accepting that VM.
- `Get-LocalServerFacts` on the lab's Server Core VMs (`Get-NetTCPConnection`, `Get-Counter` availability there).
- The Azure Migrate import accepting the generated file, and its warnings (the template header row is real; the rows were not uploaded).
- The gate against a real vault: the value strings of `protectionState` and `testFailoverState` were not verified, so the gate does not use them.
- Replication time, the RPO the vault reports, and the test failover duration: the narration of the screen scenes must be corrected after the recording.
- The assessment's default comfort factor, and whether the monthly estimate agrees with `sizing.py`.

## References

- [Tutorial: Build a business case or assess servers using an imported CSV file](https://learn.microsoft.com/azure/migrate/tutorial-discover-import)
- [Assessment overview (migrate to Azure VMs): sizing and comfort factor](https://learn.microsoft.com/azure/migrate/concepts-assessment-calculation)
- [Prepare the agent-based replication appliance](https://learn.microsoft.com/azure/migrate/migrate-replication-appliance)
- [Tutorial: Set up disaster recovery for Azure VMs](https://learn.microsoft.com/azure/site-recovery/azure-to-azure-tutorial-enable-replication)
- [Tutorial: Run a disaster recovery drill for Azure VMs](https://learn.microsoft.com/azure/site-recovery/azure-to-azure-tutorial-dr-drill)
- [Quickstart: Set up disaster recovery to a secondary Azure region](https://learn.microsoft.com/azure/site-recovery/azure-to-azure-quickstart)
- [Use the Recovery Services dashboard](https://learn.microsoft.com/azure/site-recovery/site-recovery-monitor-and-troubleshoot)
- [Replication Protected Items, List (REST)](https://learn.microsoft.com/rest/api/site-recovery/replication-protected-items/list)
- [Get-NetTCPConnection](https://learn.microsoft.com/powershell/module/nettcpip/get-nettcpconnection), [Get-ComputerInfo](https://learn.microsoft.com/powershell/module/microsoft.powershell.management/get-computerinfo)
- Complete Guide on the blog: [Cloud migration platform: Azure Migrate, Site Recovery, hybrid cloud](https://www.devladlog.com/articles/deep-dive/2025-10-20-cloud-migration-platform-azure-migrate-site-recovery-hybrid-cloud/)
