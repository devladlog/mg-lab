# Demo shot list: DEVLADLOG Deep Dive #8, DevSecOps pipeline

Code and test scenes in `script.yaml` are real (from `app/`). The four `screen` scenes need the lab.
**Status: needs tenant, Azure subscription, a throwaway GitHub repo and an Azure DevOps project.** Offline: 7 xUnit tests,
31 pytest tests, actionlint, zizmor (offline), hadolint, detect-secrets, `bicep build` and `bicep lint` pass.
**Not yet run:** the workflow, the Docker build, Trivy, the Bicep deployment, `azure-pipelines.yml`. Record each outcome in the README.

## Lab environment

Recorded on the lab laptop: Edge (GitHub, Azure DevOps, Azure portal), Windows Terminal. No Hyper-V VM needed.

**Azure** (lab subscription, one resource group `rg-mglab-deep-dive-08`, West Europe)

| Resource | SKU | Cost for the recording window |
|---|---|---|
| Container Registry `acrmgl08<token>` | **Basic**, admin user off | small daily charge (check the [pricing page](https://azure.microsoft.com/pricing/details/container-registry/) on the day) |
| Container Apps environment + app `ca-mgl08-purchase-status` | **Consumption**, 0.25 vCPU, min replicas 0 | free grant then per-second usage; scale to zero between takes |
| Log Analytics workspace | PerGB2018, 30 days | cents for a recording |
| 2 user-assigned identities, 1 federated credential | n/a | free |

Budget alert `mglab-monthly` stays active. Delete the group the same day.

**GitHub:** a public throwaway repository (code scanning and dependency review are free on public repos), environment
`prod-lab` with the lab account as required reviewer; environment secrets `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`,
`AZURE_SUBSCRIPTION_ID`, variables `ACR_NAME`, `APP_NAME`, `RESOURCE_GROUP`. **Azure DevOps:** a throwaway project in the lab
organization, a service connection `sc-mgl08-wif` (workload identity federation), environment `prod-lab` with an approval,
pipeline variables `acrName`, `appName`, `resourceGroup`.
Lab users: only the lab Administrator (recording account, Owner on the subscription). No licences needed.

## Setup (off camera)

1. Tests: run the block under "Test locally" in `README.md`; expect 7 and 31 passed.
2. Deploy the infrastructure (as lab Administrator, `az login` off camera):
   ```bash
   az group create -n rg-mglab-deep-dive-08 -l westeurope
   az deployment group create -g rg-mglab-deep-dive-08 -f app/infra/main.bicep -p githubOwner=<throwaway GitHub account> --query properties.outputs
   ```
   Check and write into the README: the deployment succeeds (AcrPull propagation, see README), the federated credential
   subject ends in `:environment:prod-lab`, ACR admin user is disabled in the portal.
3. Put the output ids into the GitHub environment; push `app/` to the repo as the repository root.
4. Dry run: open a PR, let it go green, merge, approve `prod-lab`, confirm the app shows the image digest.

## Screens to capture (1920x1080, browser zoom 100 %)

| Scene id | File | What must be on screen |
|---|---|---|
| `run-screen` | `screens/actions-run.jpg` | GitHub Actions run of `secure-pipeline` on main: all jobs green, the `prod-lab` approval step visible |
| `gate-screen` | `screens/gate-fail.jpg` | A PR branch where a deliberately old base digest or a waiver past its date makes `vuln_gate.py` fail; the job summary table with finding, package, fixed version |
| `attest-screen` | `screens/attestation.jpg` | Repository > Attestations for the pushed digest, plus the Security tab with CodeQL enabled |
| `ado-screen` | `screens/ado-run.jpg` | Azure DevOps run of `azure-pipelines.yml`: Build and Deploy stages, the environment approval; service connection page with "Workload identity federation" visible |

Order: green run on main first, then the failing PR branch, then the attestation, then Azure DevOps.

## Masking

Run `pipeline/mask.js` before portal captures. Mask the tenant name and id, subscription id, registry host, client ids, the
GitHub account name and the Azure DevOps organization name. The OIDC token is never printed; do not enable step debug logging.

## Tear-down

```bash
az group delete -n rg-mglab-deep-dive-08 --yes --no-wait
```
Delete the throwaway GitHub repository and the Azure DevOps project (this removes the service connection); the
federated credentials go with the identities. Nothing was stored: no client secret exists to revoke.
