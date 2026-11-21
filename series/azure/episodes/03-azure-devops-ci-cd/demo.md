# Demo shot list — DEVLADLOG Azure #3, A pipeline that knows when to stop

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs / tenant apps | none |
| Azure DevOps | An Azure DevOps organization connected to the lab tenant (Microsoft Entra), **not yet listed in `series/LAB.md`**: free tier, linked to the lab subscription for billing (hosted parallelism), one **private** project `contoso-platform` with the mg-lab repo imported. Free Microsoft-hosted minutes cover the runs (one run ≈ 10–15 min) |
| Lab users | `labadmin` (the recording account): Project Administrator, Owner on the two resource groups; **`alex.demo` (Alex Demo)** as the `contoso-prod` approver (sign in as Alex in a second browser profile to approve/reject, or keep labadmin as approver and the "requester can't approve" option off) |
| Azure | Two resource groups in **Sweden Central**: **`rg-contoso-lab`** and **`rg-contoso-prod`**. Exception to the `rg-mglab-<series>-<ep>` rule: the names are part of the pipeline under test (`pipelines/azure-pipelines.yml`, its tests and fixtures); renaming them means changing code, so they stay and are deleted in tear-down. Lab: episode 2's lab profile (B1 plan, 2 private endpoints, 2 private DNS zones, LRS storage, Key Vault, Log Analytics), well under €1 for ~1 hour. Prod: what-if only on an empty group (free); **reject** the prod approval |
| Entra | Two app registrations created by the automatic service connections (deleted in tear-down) |
| Licences / trials | none beyond the subscription and the free Azure DevOps tier |
| Recording machine | The Windows lab laptop: Azure DevOps and the Azure portal in the browser; WSL (Ubuntu) bash with Azure CLI for the setup commands |

Everything below **needs the lab tenant** (Azure DevOps organization + Azure subscription), except the local checks.
The episode builder ran only the local checks (`ci.sh`, 44 + 15 pytest, 7 xUnit, PSRule, Bicep lint) and `deploy.sh`
against a fake `az`. No Azure DevOps or Azure resources were created.

## Prerequisites

| What | Notes |
|---|---|
| Azure DevOps organization + a **private** project (e.g. `contoso-platform`) | New public projects can't be created any more. Free Microsoft-hosted tier (1 parallel job, 60 min per job, 1,800 min per month) needs the organization **linked to an Azure subscription for billing**; without it runs fail with "No hosted parallelism has been purchased or granted" |
| The mg-lab repo in the project | Repos → Import repository (from the GitHub URL), branch `main`. Azure Repos Git is what this episode shows (branch policy for PRs) |
| Azure subscription with the €10 budget alert | You need **Owner** (or User Access Administrator) on the two resource groups to set up the service connections and role assignments |
| Permissions in Azure DevOps | Project Administrator (branch policy, environments, service connections) |
| Cost | Lab: episode 2's lab profile (B1 plan, 2 private endpoints, 2 private DNS zones, LRS storage, Key Vault, Log Analytics), well under €1 for a ~1 hour recording if torn down the same day. **Prod: only the what-if runs**, against an empty group (free). Approving prod would deploy P1v3 ×2 zone-redundant: **reject** on camera unless you have budget and tear down immediately. Pipeline minutes: one run ≈ 10–15 min of the free 1,800 |

## Setup (needs tenant)

### 1. Resource groups + governance (a person, not the pipeline)
```bash
az login                 # labadmin, off camera
for E in lab prod; do
  az group create -n rg-contoso-$E -l swedencentral --tags workload=contoso environment=$E owner=platform-team -o none
  az deployment group create -g rg-contoso-$E --name governance \
    --parameters series/azure/episodes/02-cloud-architecture/infra/env/governance.bicepparam \
    --parameters allowedLocations='["swedencentral"]' -o none
done
```

### 2. Service connections (Project settings → Service connections)
For each of `lab` and `prod`: **New service connection → Azure Resource Manager → App registration (automatic) →
Workload identity federation**, scope **Subscription → resource group `rg-contoso-<env>`**, name `sc-contoso-<env>`.
Do **not** tick "Grant access permission to all pipelines" (authorize the pipeline on first run instead).
Do **not** add checks to `sc-contoso-prod` (the plan stage uses it unattended).

Then, per connection, add role assignment rights limited to the two data roles (Portal → resource group → Access
control → Add role assignment → **Role Based Access Control Administrator** → member: the connection's app
registration → Conditions: *Constrain roles* → Storage Blob Data Reader, Key Vault Secrets User).

### 3. Environments (Pipelines → Environments) — BEFORE creating the pipeline
- `contoso-lab`: no checks.
- `contoso-prod`: Approvals and checks → **Approvals** (approver: **Alex Demo** (`alex.demo`) or `labadmin`;
  if you have a second account, use the advanced option that stops the requester approving their own run) and
  **Exclusive lock**.

### 4. Pipeline
Pipelines → New pipeline → Azure Repos Git → mg-lab → **Existing Azure Pipelines YAML file** →
`/series/azure/episodes/03-azure-devops-ci-cd/pipelines/azure-pipelines.yml` → Save (don't run yet).
Rename it `contoso-workload`.

### 5. Branch policy
Repos → Branches → `main` → Branch policies → **Build validation** → `contoso-workload`, trigger Automatic,
Required. (Optional shot: open a PR that changes `gate-policy.json`; only `ci` runs.)

## Screens to capture (match the `screen` scenes in script.yaml)

### 1. `screens/pipeline-run.jpg` — scene `run` (needs tenant)
Run the pipeline on `main` (Run pipeline, leave *Accept protected changes* unticked). First run: authorize the
service connections / environments when prompted ("This pipeline needs permission…"); that prompt is a good extra
shot. Wait until `ci`, `lab` and `prod_plan` are green and `prod` shows **Waiting** + Review. Capture the run summary
with all four stages. Lab takes ~10 min on the first deployment (private endpoints); `/healthz` may need the retries
in `deploy.sh` — if it still fails, re-run the `lab` stage and say so in the episode.

### 2. `screens/tests-tab.jpg` — scene `tests` (needs tenant)
Same run → **Tests** tab: expect 66 passed (pytest 44 + 15 merged into one run, xUnit 7), 0 failed. If the count
differs, update the narration number.

### 3. `screens/approval.jpg` — scene `approve` (needs tenant)
Left: run → **Extensions** tab → "What-if gate: rg-contoso-prod: GO" (all Create on the empty prod group).
Right: click **Review** on `prod` → the approval dialog. Then **Reject** with comment "demo: prod stays empty".
Also download the `whatif-prod_plan` artifact and commit `whatif.json` as `tests/fixtures/whatif-real-prod.json`
(mask the subscription ID to zeros first) so the gate is tested against a real document.

### 4. `screens/environment-history.jpg` — scene `history` (needs tenant)
Environments → `contoso-prod` → Deployments tab (the rejected run is listed) and the **Approvals and checks** tab
(Approvals + Exclusive lock). Two captures side by side, or the checks tab only.

### Optional: the gate blocking for real (b-roll for scene `gate`)
In the portal, set the **lab** storage account's Networking → Public network access to *Enabled from all networks*.
Re-run the pipeline: `lab` fails at the gate with the two "protected change" errors and nothing is deployed. Re-run
with *Accept protected changes* ticked: it passes and the summary lists "Protected changes accepted for this run".
(If the real what-if shows different property paths than the fixture, update `tests/fixtures` and the scene.)

## Masking
- Organization and project names in the Azure DevOps URL bar and breadcrumb; user names and avatars except the
  fictional approver; the subscription ID and tenant ID in service connection details and in the what-if output.
- Resource name suffixes (`stcontosolab…`, `kv-contoso-lab-…`, `app-contoso-lab-…`) and `*.azurewebsites.net`.
- Never open the service connection's **Edit** pane on camera (it shows the issuer and subject identifier).
- Use `pipeline/mask.js` in the browser; `series_label: "AZURE"` is set in script.yaml.

## Tear-down (needs tenant)
```bash
az group delete -n rg-contoso-lab --yes
az group delete -n rg-contoso-prod --yes
az keyvault purge --name <kv-contoso-lab-…>      # lab vault has purge protection off (episode 2), so it can be purged
```
In Azure DevOps: delete the pipeline, both environments and both service connections. Then check Entra ID → App
registrations for the two apps the automatic setup created and delete any that are still there.
Remove the branch policy on `main` if the project stays.
