# DEVLADLOG Dev Tools #5 — CI/CD pipeline setup: from pull request to production, proven

The orders API from [episode 4](../04-docker-for-developers/) gets one **GitHub Actions** workflow that takes it
from a pull request to a running container in Azure App Service, and only calls a deploy "done" when the live app
answers with the commit that was just built.

```
 pull request ─► guardrails ┐
                 build-test ┼─► e2e                                         (checks only)
 push to main ─► guardrails ┘     └─► publish ─────────────────────► deploy ──────────────────────► smoke
                 ep.1 checks     locked restore   real image +         GHCR, sha-<commit> tag,      environment "production"
                                 build, xUnit,    real SQL Server       build provenance             (required reviewer),
                                 TRX summary      (ep.4 compose.yaml)   attestation                  OIDC to Azure, no secret
```

- **build-test**: .NET SDK from `global.json`, NuGet cache keyed on **lock files**, `dotnet restore --locked-mode`,
  xUnit with a TRX report turned into the job summary and kept as an artifact.
- **e2e**: `scripts/e2e.sh` (the same script on a laptop) generates a throwaway SA password, runs episode 4's
  `compose.yaml` with `--build --wait`, runs the **SQL Server integration tests** against the real database, refuses
  a run where they were skipped, then smoke-tests the API container.
- **publish** (main only): builds the image once with Buildx (GitHub cache), pushes `ghcr.io/<owner>/<repo>:sha-<commit>`
  with `GITHUB_TOKEN`, and pushes a signed **build provenance attestation** for its digest.
- **deploy** (main only): job on the `production` environment (required reviewer, branch `main`), `azure/login`
  with **OpenID Connect** to a user-assigned managed identity, `azure/webapps-deploy` with that image, then
  `tools/smoke.py --read-only` until `/healthz` reports this commit.
- Azure side in one Bicep file: Linux App Service plan (B1) + Web App for Containers, the identity, a federated
  credential for the exact GitHub subject, and **Website Contributor on the resource group only**.

Azure Pipelines (stages, Azure DevOps environments, what-if gates) is [Azure #3](../../../azure/episodes/03-azure-devops-ci-cd/);
episode 1 introduced the guardrail checks and rulesets. This episode doesn't repeat them: it reuses episode 1's
checks as the first job and focuses on what a GitHub Actions pipeline for a container needs.

| Path | What it is |
|---|---|
| [`src/orders-app/.github/workflows/ci-cd.yml`](src/orders-app/.github/workflows/ci-cd.yml) | The pipeline: 5 jobs, actions pinned to commit SHAs, read-only token by default, PR runs cancelled when outdated, main never cancelled |
| [`src/orders-app/.github/dependabot.yml`](src/orders-app/.github/dependabot.yml) | Weekly PRs that bump the SHA pins (and their `# vX.Y.Z` comments) |
| [`src/orders-app/Directory.Build.props`](src/orders-app/Directory.Build.props) | `RestorePackagesWithLockFile` for every project |
| `src/orders-app/**/packages.lock.json` | The committed package graph (API project has sections for `linux-x64` and `linux-arm64`) |
| [`src/orders-app/scripts/e2e.sh`](src/orders-app/scripts/e2e.sh) | Password → `.env` (mode 600, masked) → `compose up --build --wait` → SQL Server tests → TRX gate → smoke → `down -v` |
| [`src/orders-app/tools/smoke.py`](src/orders-app/tools/smoke.py) | Polls `/healthz` for status **and version**, then exercises the API; `--read-only` for production; writes the job summary |
| [`src/orders-app/tools/trx_check.py`](src/orders-app/tools/trx_check.py) | TRX summary table for the job summary; `--min-passed`, `--no-skipped` |
| [`src/orders-app/tools/oidc_subject.py`](src/orders-app/tools/oidc_subject.py) | Prints the `sub` claim to put in the federated credential, from `gh api repos/<owner>/<repo>` |
| [`src/orders-app/infra/main.bicep`](src/orders-app/infra/main.bicep) | App Service plan + site (port 8080, `/healthz` health check, HTTPS only, FTP/SCM basic auth off), identity, federated credential, role assignment |
| [`src/orders-app/tests/.../SqlServerIntegrationTests.cs`](src/orders-app/tests/Contoso.Orders.Api.Tests/SqlServerIntegrationTests.cs) | 4 xUnit tests on a real SQL Server (own database per run), skipped when `ORDERS_SQLSERVER_TESTS` isn't set |
| `src/orders-app/` (rest) | Episode 4's app; changes: `/healthz` reports `version`, Dockerfile copies the lock file and restores `--locked-mode`, `ARG APP_VERSION`, compose passes it |
| [`tests/`](tests/) | 91 pytest tests (below) |
| [`tests/fixtures/actions/`](tests/fixtures/actions/) | `action.yml` of every pinned action at its pinned commit, plus `pins.json` (tag → SHA) |
| [`tests/schemas/`](tests/schemas/) | SchemaStore JSON schemas for workflows and `dependabot.yml`, vendored |
| [`tests/fixtures/trx/`](tests/fixtures/trx/) | Two TRX files written by `dotnet test` here (machine name replaced) |

## Run the tests

```bash
cd series/developer-tools/episodes/05-ci-cd-pipeline-setup
(cd src/orders-app && dotnet test)          # Passed! 21 passed, 4 skipped (the SQL Server tests, no SQL Server here)
python3 -m pytest -q tests                   # 91 passed (~30 s)
```

| Test file | What it proves |
|---|---|
| `test_workflow.py` (52) | Schema; job names = ids (required checks); the job graph; every action pinned to the recorded SHA with its version comment; every `with:` input exists in that action's `action.yml` and required ones are present; every `steps.x.outputs.y` / `needs.x.outputs.y` exists; contexts only where GitHub allows them; no `${{ }}` in `run:`; permissions per job; publish/deploy never on PRs; deploy = environment + no cancel + OIDC; the deployed tag, the build arg and the smoke `--version` are the same commit; plus a mutation test (typo in an input is caught) |
| `test_build_and_smoke.py` (9) | **Runs every `run:` step of the build-test job** in a clean copy (locked restore, Release build, tests, TRX summary into a fake `GITHUB_STEP_SUMMARY`), starts the API it built and smoke-tests it (pass, old version still running, wrong database, read-only writes nothing, nothing listening); locked restore for `-a x64` and `-a arm64`; NU1004 without `RuntimeIdentifiers`; NU1004 when a package is removed without updating the lock file |
| `test_e2e_script.py` (7) | `e2e.sh` with fake `docker`/`dotnet`/`python3`: step order, `.env` mode 600 and deleted, password meets the SQL Server policy and is never printed, `::add-mask::` is the first line in Actions, new password per run, logs + `down -v` on failure, refuses to overwrite an existing `.env` |
| `test_infra.py` (7) | `bicep build` + `bicep lint` clean; federated credential issuer/audience/subject; Website Contributor at resource-group scope; `WEBSITES_PORT` = Dockerfile `EXPOSE` = 8080; health check path is a real route; HTTPS only, FTPS off, basic auth off; outputs are identifiers only and match the names the workflow reads |
| `test_tools.py` (11) | `trx_check` on real TRX files (skips counted correctly, all-skipped SQL run fails the gate, job summary); `oidc_subject` legacy/immutable/auto, the documented shapes, case kept, CLI |
| `test_image_inputs.py` (5) | The guardrails job's three `run:` steps pass in a fresh git repo of the app; episode 4's linter still clean; build context has the lock file and props; locked restore before the source copy; `APP_VERSION` reaches `/healthz` through ARG/ENV and Compose |

Also verified here: the same restore/build/test with **.NET SDK 10.0.404** (the latest 10.0 SDK, which
`setup-dotnet` installs for `rollForward: latestFeature`), installed into a temp folder: locked restore OK,
0 warnings, 21 passed / 4 skipped.

**Not run here (no Docker daemon, no GitHub, no Azure):** the workflow on GitHub runners, `docker compose`, the SQL
Server tests against a real SQL Server, the image push, the attestation, the Azure login and deployment. They run
for real in the recording, see [demo.md](demo.md). `actionlint` isn't installed on the shared build machine; the
contract tests above cover our rules, and the recording runs the real workflow.

## Set it up (needs GitHub + Azure; full steps in demo.md)

```bash
# 1. a public repo with the contents of src/orders-app, then:
gh api repos/<owner>/<repo> | python3 tools/oidc_subject.py --environment production
# 2. Azure
az group create -n rg-mglab-devtools-05 -l westeurope
az deployment group create -g rg-mglab-devtools-05 -f infra/main.bicep \
  -p appName=<unique-name> githubSubject='<subject from step 1>'
# 3. GitHub environment "production": required reviewer, deployment branch main,
#    secrets AZURE_CLIENT_ID / AZURE_TENANT_ID / AZURE_SUBSCRIPTION_ID, variables AZURE_WEBAPP_NAME / AZURE_RESOURCE_GROUP
# 4. after the first publish: make the GHCR package public (App Service pulls it without credentials)
```

## What we learned / gotchas

- **A lock file breaks the Dockerfile's restore unless it knows the architectures.** `dotnet restore -a $TARGETARCH
  --locked-mode` failed with `NU1004: The project's runtime identifiers have changed`. Adding
  `<RuntimeIdentifiers>linux-x64;linux-arm64</RuntimeIdentifiers>` to the API project puts a section per RID in
  `packages.lock.json`; both architectures now restore locked (tested, and the failure is tested too).
- **An XML comment can't contain `--`.** Our first `Directory.Build.props` mentioned `--locked-mode` in a comment.
  `dotnet restore` printed "Restored" and produced no lock file; only `dotnet msbuild -getProperty` showed
  `MSB4024 ... An XML comment cannot contain '--'`.
- **setup-dotnet's cache needs lock files**, and with `rollForward: latestFeature` it installs the highest matching
  SDK (10.0.404 today), not the 10.0.100 written in `global.json` (setup-dotnet README). Learn warns that implicit
  package versions can differ between SDKs and break locked restore; we checked with 10.0.404: no difference.
- **Skipped isn't passed, and the TRX counters don't say "skipped".** `dotnet test --filter Category=SqlServer`
  with every test skipped exits **0**. The TRX file marks each test `NotExecuted`, but its `<Counters>` element says
  `notExecuted="0"`; skipped = `total - executed`. `trx_check.py --min-passed 4 --no-skipped` makes the e2e job fail
  if the SQL Server tests didn't actually run.
- **`set -o pipefail` + `tr </dev/urandom | head` = exit 141.** The first password generator killed `e2e.sh` with
  SIGPIPE before it did anything (the fake-docker test caught it). It now reads exactly 16 bytes with `head -c 16`.
- **The GitHub OIDC subject changed format in 2026.** Repositories created, renamed or transferred after
  15 July 2026 present `repo:<owner>@<owner-id>/<repo>@<repo-id>:environment:production`, older ones
  `repo:<owner>/<repo>:environment:production`. The federated credential must match exactly, case-sensitively, no
  wildcards. A wrong subject is accepted when you create the credential and fails only at login, with
  `AADSTS700213: No matching federated identity record found for presented assertion subject '<subject>'` — the
  message contains the subject GitHub sent, so copy it from there if `oidc_subject.py`'s guess is wrong.
- **With `environment:` on the job, the subject is the environment, not the branch.** That's why the credential is
  for `environment:production` and why environment protection (reviewer, `main` only) is the real gate: the
  environment secrets are released only after approval.
- **Learn recommends secrets for the three Azure IDs**, environment secrets in public repositories. They aren't
  credentials (there is no client secret), but keeping them in the environment means a workflow that skips the
  approval can't even try.
- **GHCR packages start private and don't inherit the repository's visibility** (GitHub docs: permissions are
  inherited, visibility isn't). App Service pulls the image anonymously, so the package is made public once, after
  the first push. Public can't be made private again; the tear-down deletes the package.
- **"Deployment succeeded" means the setting changed.** App Service then pulls and starts the new container; until
  then the old one answers. The smoke step polls `/healthz` until `version` equals `github.sha` (10-minute budget),
  and only then reads the API. A test shows the failure while the "old version" is still running.
- **App Service and SQLite:** the app keeps its SQLite file in `/data` inside the container
  (`WEBSITES_ENABLE_APP_SERVICE_STORAGE=false`); Learn says the `/home` share can't hold SQLite locks. The data
  resets on every deploy, fine for a demo. Production would use Azure SQL.
- **Contexts aren't available everywhere.** `env` works in a job's `outputs` and `environment.url` but not in its
  `if`; `secrets` isn't available in `environment.url`. The test carries the availability table from the GitHub docs.
- **`env.IMAGE` must be lowercase for GHCR**; `ghcr.io/${{ github.repository }}` is fine only because the owner and
  repo names used here are lowercase (checked in demo.md).

## References
- Blog: [CI/CD Pipeline Setup — Complete Guide](https://www.devladlog.com/articles/developer-tools/2025-12-06-cicd-pipeline-setup-complete-guide-2025/)
- Microsoft Learn: [Use the Azure Login action with OpenID Connect](https://learn.microsoft.com/azure/developer/github/connect-from-azure-openid-connect) (`id-token: write`, secrets for the IDs, environment secrets in public repos, audience `api://AzureADTokenExchange`) ·
  [Configure a user-assigned managed identity to trust an external identity provider](https://learn.microsoft.com/entra/workload-id/workload-identity-federation-create-trust-user-assigned-managed-identity) (exact subject, no wildcards, 20 credentials max) ·
  [Configure an app to trust an external identity provider](https://learn.microsoft.com/entra/workload-id/workload-identity-federation-create-trust) (subject formats for environment, ref, pull request) ·
  [Flexible federated identity credentials](https://learn.microsoft.com/entra/workload-id/workload-identities-flexible-federated-identity-credentials) (GitHub immutable subject format from 15 July 2026) ·
  [Azure Databricks: workload identity federation for GitHub Actions](https://learn.microsoft.com/azure/databricks/dev-tools/auth/provider-github) (immutable environment subject example) ·
  [What's new for authentication: case-sensitive FIC matching, AADSTS700213](https://learn.microsoft.com/entra/identity-platform/reference-breaking-changes#august-2024) ·
  [Important considerations for federated identity credentials](https://learn.microsoft.com/entra/workload-id/workload-identity-federation-considerations) (propagation delay)
- Microsoft Learn, App Service: [Deploy a custom container to App Service by using GitHub Actions](https://learn.microsoft.com/azure/app-service/deploy-container-github-action) ·
  [Configure a custom container](https://learn.microsoft.com/azure/app-service/configure-custom-container) (`WEBSITES_PORT`) ·
  [App Service on Linux FAQ](https://learn.microsoft.com/troubleshoot/azure/app-service/faqs-app-service-linux-new) (ports 80/8080, SQLite on `/home`, start time limit) ·
  [Azure built-in roles: Website Contributor](https://learn.microsoft.com/azure/role-based-access-control/built-in-roles/web-and-mobile#website-contributor)
- Microsoft Learn, NuGet/.NET: [Locking dependencies](https://learn.microsoft.com/nuget/consume-packages/package-references-in-project-files#locking-dependencies) (`RestorePackagesWithLockFile`, `--locked-mode`, SDK variance) ·
  [dotnet restore](https://learn.microsoft.com/dotnet/core/tools/dotnet-restore) ·
  [Run an ASP.NET Core app in Docker](https://learn.microsoft.com/aspnet/core/host-and-deploy/docker/building-net-docker-images) (sample `aspnetapp` on 8080)
- GitHub docs: [OpenID Connect reference](https://docs.github.com/en/actions/reference/security/oidc) (subject syntax, immutable format) ·
  [Immutable subject claims changelog](https://github.blog/changelog/2026-04-23-immutable-subject-claims-for-github-actions-oidc-tokens/) ·
  [Deployments and environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments) (required reviewers on public repos for Free/Pro/Team, environment secrets after approval, prevent self-review) ·
  [Contexts reference](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts) (context availability) ·
  [Working with the Container registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry) ·
  [Package access control and visibility](https://docs.github.com/en/packages/learn-github-packages/configuring-a-packages-access-control-and-visibility) ·
  [Artifact attestations](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations) (public repos on Free/Pro/Team, `actions/attest`, `gh attestation verify oci://`) ·
  [Dependabot supported ecosystems](https://docs.github.com/en/code-security/dependabot/ecosystems-supported-by-dependabot/supported-ecosystems-and-repositories) (SHA-pinned actions and version comments)
- Action manifests and README: [actions/setup-dotnet](https://github.com/actions/setup-dotnet) (cache needs `packages.lock.json`, `rollForward` handling) and the other actions at the commits in `tests/fixtures/actions/pins.json`
- Docker docs: [docker compose up](https://docs.docker.com/reference/cli/docker/compose/up/) (`--wait`, `--wait-timeout`)
- Pricing: App Service B1 Linux, West Europe, EUR 0.0162/hour (Azure Retail Prices API, 21 Nov 2026)
