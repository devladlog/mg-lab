# DEVLADLOG Azure #3 — Azure DevOps & CI/CD: a pipeline that knows when to stop

Episode 2 built the contoso reference workload (Bicep: App Service → private endpoints → storage + Key Vault, plus a
.NET 10 readiness probe) and wrote its guardrails as tests. This episode ships it with **Azure Pipelines**:

- **One YAML pipeline, four stages**: `ci` → `lab` → `prod_plan` → `prod`, built from three stage templates
- **CI = one script** (`ci.sh`) that runs the same on a laptop and on a Microsoft-hosted agent: pipeline contract,
  pytest, episode 2 guardrails, Bicep lint, xUnit, PSRule for Azure, then the probe package as a pipeline artifact
- **No secrets**: one Azure Resource Manager service connection per environment, using **workload identity
  federation**, each scoped to its own resource group
- **What-if as a gate**: every deployment runs `az deployment group what-if --no-pretty-print` first; a small
  Python gate blocks deletes and changes to protected properties (network access, keys, NSG rules, role
  assignments, app identity) unless the run was queued with *Accept protected changes* ticked
- **Approvals where they belong**: on the `contoso-prod` environment, not in YAML. Checks run *before* a stage
  starts, so the prod what-if has its own stage and the approver reads its summary first
- **The pipeline is tested too**: a contract checker expands the templates and fails the build on the mistakes
  that otherwise only show up in Azure DevOps (missing template parameters, runtime service connection names,
  deployment jobs without `checkout: self`, prod without a plan stage, YAML `pr:` triggers on Azure Repos)

```
 push to main ─► ci ──────────────► lab ───────────────► prod_plan ─────────────► prod
                 contract, pytest    deployment job        what-if + gate only      deployment job
                 guardrails, lint    env contoso-lab       summary + artifact       env contoso-prod
                 xUnit, PSRule       what-if → gate →      (sc-contoso-prod,        [Approval + Exclusive lock]
                 probe.zip artifact  deploy → zip → /healthz no checks on it)        what-if → gate → deploy → /healthz
 pull request ─► ci only (Build validation branch policy on main; the deploy stages are limited to refs/heads/main)
```

| Path | What it is |
|---|---|
| [`pipelines/azure-pipelines.yml`](pipelines/azure-pipelines.yml) | Trigger (main + path filters), `pr: none`, runtime parameter `acceptProtectedChanges`, the four stages |
| [`pipelines/templates/ci-stage.yml`](pipelines/templates/ci-stage.yml) | .NET 10 SDK, Python 3.12, pinned Bicep CLI + PSRule, `ci.sh`, JUnit + TRX publishing, `probe` artifact |
| [`pipelines/templates/deploy-stage.yml`](pipelines/templates/deploy-stage.yml) | Deployment job on an environment, `checkout: self`, `AzureCLI@2` → `deploy.sh` |
| [`pipelines/templates/plan-stage.yml`](pipelines/templates/plan-stage.yml) | Regular job: `deploy.sh --plan-only`, summary uploaded to the run, what-if JSON as artifact |
| [`pipelines/scripts/ci.sh`](pipelines/scripts/ci.sh) | The whole CI stage as one script (7 steps) |
| [`pipelines/scripts/deploy.sh`](pipelines/scripts/deploy.sh) | what-if → gate → `az deployment group create` → `az webapp deploy` → `curl --fail` on `/healthz` |
| [`pipelines/gate-policy.json`](pipelines/gate-policy.json) | Blocked change types, protected properties per resource type, known-noise paths |
| [`src/whatif_gate`](src/whatif_gate) | The gate: parses the what-if result, Markdown summary, `##vso` logging commands, exit 0 / 1 / 2 |
| [`src/pipeline_contract`](src/pipeline_contract) | Template expander + 10 rules (T1, T2, S1–S3, J1, K1, K2, R1, X1) for the pipeline YAML |
| [`tests/`](tests) | 44 pytest tests: gate (21), contract (16, each rule proven by mutating a copy), `deploy.sh` with a fake `az`/`curl` (7) |
| [`tests/fixtures/whatif-*.json`](tests/fixtures) | What-if documents written to the Learn schema (see the note below) |

## Run it here (no Azure, no Azure DevOps)

```bash
python3 -m pytest tests -q                      # 44 passed
PYTHONPATH=src python3 -m pipeline_contract pipelines/azure-pipelines.yml --approval-env contoso-prod
#   ci         needs []  (jobs)
#   lab        needs [ci]  (deploy -> contoso-lab)
#   prod_plan  needs [lab]  (plan)
#   prod       needs [prod_plan]  (deploy -> contoso-prod)
#   4 files, 4 stages, 0 problems

# The whole CI stage (needs bicep, dotnet 10, zip, pwsh + PSRule.Rules.Azure 1.47.0 in PSModulePath)
pwsh -c 'Save-Module PSRule.Rules.Azure -RequiredVersion 1.47.0 -Path /tmp/psmodules -Repository PSGallery'
PSModulePath=/tmp/psmodules pipelines/scripts/ci.sh /tmp/ci-out
```

Verified in this container (Python 3, pytest 9.1.1, PyYAML 6.0.3, Bicep CLI 0.49.2, .NET SDK 10, PowerShell 7.6,
PSRule 2.9.0 + PSRule.Rules.Azure 1.47.0): `ci.sh` exits 0 in about 30 seconds —
contract 0 problems · **44 passed** (this episode) · **15 passed** (episode 2 guardrails) · Bicep lint clean ·
**xUnit 7 passed** · PSRule lab 118 pass / 0 fail / 6 suppressed, prod 123 pass / 0 fail / 1 suppressed ·
`probe.zip` ≈ 2 MB. `deploy.sh` ran end to end against a fake `az` and `curl` (call order, exit codes, nothing
deployed when the gate says no).

**Not run here:** anything in Azure DevOps or Azure (service connections, environments, approvals, the real
what-if, the deployment). There is no local runner for Azure Pipelines YAML, which is why the contract checker
exists; the recorder runs the real pipeline (see [demo.md](demo.md)).

> **About the what-if fixtures.** They are hand-written to the documented `WhatIfOperationResult` schema
> (`changes[].changeType`, `resourceId`, `delta[].path/propertyChangeType/before/after/children`), not captured
> from Azure. The gate accepts both the Azure CLI shape (`changes` at the top) and the REST shape
> (`properties.changes`). The recorder saves a real one from the `prod_plan` artifact; add it as a fixture.

## Set up and run in Azure DevOps (needs the tenant)

Short version (details, cost and screens in [demo.md](demo.md)):

1. Resource groups `rg-contoso-lab` and `rg-contoso-prod`, with episode 2's governance (policy) deployed by a person.
2. Two ARM service connections, **App registration (automatic) + Workload identity federation**, scope = resource
   group: `sc-contoso-lab`, `sc-contoso-prod`. Then give each identity **Role Based Access Control Administrator**
   on its group, with a condition limited to the two data roles (the template creates role assignments; the
   automatic setup only grants Contributor).
3. Environments `contoso-lab` (no checks) and `contoso-prod` (**Approvals** + **Exclusive lock**) — create them
   **before** the first run.
4. New pipeline → existing YAML → `series/azure/episodes/03-azure-devops-ci-cd/pipelines/azure-pipelines.yml`.
5. Branch policy on `main`: Build validation → this pipeline (that's how pull requests are validated).

## What we learned / gotchas

- **Approvals happen before the stage, not before the job.** Learn: all checks on all resources used in a stage
  must pass *before the stage starts*. A what-if inside the prod stage would run after the approval, so the plan
  is its own stage (`prod_plan`) and the approver reads its summary on the run's Extensions tab first. Contract
  rule S3 fails the build if a stage that deploys to an approval environment doesn't depend on a plan stage for the
  same service connection. Corollary: put the approval on the **environment**, not on `sc-contoso-prod`, or the
  plan stage would wait for approval too.
- **The first run can create the environment, without checks.** If the YAML refers to an environment that
  doesn't exist and Azure Pipelines knows who you are (pipeline wizard, web editor), it creates it — with no
  approval. Create `contoso-prod` and its checks before saving the pipeline.
- **Azure Repos ignores `pr:` in YAML.** PR validation is a **Build validation** branch policy. `pr: none` is in
  the file so nobody thinks otherwise; rule R1 fails on anything else.
- **A deployment job doesn't check out your repo** (the default for `jobs.deployment` is `checkout: none`), but it
  does download all pipeline artifacts automatically. Our deploy steps need `deploy.sh` and the Bicep files, so
  `checkout: self` is explicit; rule J1 catches it if someone removes it (we did, in a test).
- **Service connections must be known at compile time.** Template parameters are fine; `$(serviceConnection)` isn't
  (Learn, on checks: "Service connections cannot be specified by variable"). Rule K1.
- **The automatic service connection grants Contributor; this template also creates role assignments.** Contributor
  can't write `Microsoft.Authorization/roleAssignments`, so the identity also needs Role Based Access Control
  Administrator, constrained with a condition to the two data roles episode 2 assigns.
- **The Azure CLI's Bicep isn't on PATH.** `az` installs its own Bicep CLI and doesn't add it to PATH; episode 2's
  tests call `bicep` directly, so the CI stage installs a pinned standalone `bicep` (0.49.2).
- **Our own CI wrote into someone else's folder.** The first `ci.sh` run left `bin/`, `obj/` and `__pycache__`
  inside the episode 2 folder. Now `dotnet test`/`publish` use `--artifacts-path` under the output folder and
  `PYTHONDONTWRITEBYTECODE=1` is set.
- **What-if is a prediction.** Learn documents noise (properties reported as changed that won't change) and that
  nondeterministic functions such as `newGuid()` and secure parameter values aren't evaluated. The gate turns
  unevaluated expressions into warnings and has an `ignore_paths` list for false positives you've actually seen.
  Related: episode 2's `probeSecretValue` defaults to `newGuid()`, so every deployment from this pipeline writes a
  new value for that secret (harmless here, the probe only reads its name — worth knowing for real secrets).
- **Delete only appears in complete mode.** In the default incremental mode, resources missing from the template
  show as `Ignore`, not `Delete`. The gate still blocks `Delete` (complete-mode deployments, or a future switch to
  deployment stacks).
- **Free tier needs a linked subscription.** Microsoft-hosted: one free parallel job, up to 60 minutes per job and
  1,800 minutes per month for private projects, granted once the organization is linked to an Azure subscription
  for billing. Without it, runs fail with "No hosted parallelism has been purchased or granted".

## References
- Blog: [Azure DevOps & CI/CD — Complete Guide](https://www.devladlog.com/articles/azure/2026-01-08-azure-devops-cicd-complete-guide-2026/)
- [Define approvals and checks](https://learn.microsoft.com/azure/devops/pipelines/process/approvals) (checks before the stage starts, check categories, exclusive lock, "Service connections cannot be specified by variable")
- [Create and target environments](https://learn.microsoft.com/azure/devops/pipelines/process/environments) (automatic creation, security roles)
- [Deployment jobs](https://learn.microsoft.com/azure/devops/pipelines/process/deployment-jobs) and [steps.checkout](https://learn.microsoft.com/azure/devops/pipelines/yaml-schema/steps-checkout) (no automatic checkout)
- [steps.download](https://learn.microsoft.com/azure/devops/pipelines/yaml-schema/steps-download) (automatic artifact download in deployment jobs, `$(Pipeline.Workspace)/<artifact>`)
- [pr definition](https://learn.microsoft.com/azure/devops/pipelines/yaml-schema/pr) and [Build validation branch policy](https://learn.microsoft.com/azure/devops/repos/git/branch-policies#build-validation)
- [Connect to Azure with an ARM service connection](https://learn.microsoft.com/azure/devops/pipelines/library/connect-to-azure) (workload identity federation recommended; Entra issuer; Azure DevOps issuer retires 1 July 2027)
- [Troubleshoot ARM service connections](https://learn.microsoft.com/azure/devops/pipelines/release/azure-rm-endpoint) (the automatic setup assigns Contributor)
- [Delegate role assignment management with conditions](https://learn.microsoft.com/azure/role-based-access-control/delegate-role-assignments-portal)
- [Runtime parameters](https://learn.microsoft.com/azure/devops/pipelines/process/runtime-parameters) and [template parameters](https://learn.microsoft.com/azure/devops/pipelines/process/template-parameters)
- [AzureCLI@2](https://learn.microsoft.com/azure/devops/pipelines/tasks/reference/azure-cli-v2), [PublishTestResults@2](https://learn.microsoft.com/azure/devops/pipelines/tasks/reference/publish-test-results-v2)
- [Logging commands](https://learn.microsoft.com/azure/devops/pipelines/scripts/logging-commands) (`task.logissue`, `task.uploadsummary`, escaping)
- [Bicep what-if](https://learn.microsoft.com/azure/azure-resource-manager/bicep/deploy-what-if) (`--no-pretty-print`, change types, noise, unevaluated expressions) and [Deployments - What If (REST)](https://learn.microsoft.com/rest/api/resources/deployments/what-if)
- [Install Bicep tools](https://learn.microsoft.com/azure/azure-resource-manager/bicep/install) (Azure CLI doesn't add Bicep to PATH)
- [Configure and pay for parallel jobs](https://learn.microsoft.com/azure/devops/pipelines/licensing/concurrent-jobs) and [Microsoft-hosted agents](https://learn.microsoft.com/azure/devops/pipelines/agents/hosted)
