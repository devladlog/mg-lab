# Demo shot list — DEVLADLOG Dev Tools #5, CI/CD pipeline setup

Already real (build machine, 21 Nov 2026): the workflow excerpts, the lock-file NU1004 output, the "skipped is not
passed" output, the Bicep, `dotnet test` (21 passed, 4 skipped) and `pytest` (91 passed), including the build-test
job's own commands run end to end and the smoke test against the API they built. **Recorded here for the first
time:** the workflow on GitHub-hosted runners, Docker Compose with SQL Server on the runner, the SQL Server
integration tests, the GHCR push and attestation, the OIDC login, the App Service deployment.
Status: **needs GitHub + the lab Azure subscription**.

## Lab environment

| What | Details | Cost |
|---|---|---|
| GitHub | The same account as `github.com/devladlog/mg-lab`. One **public** throwaway repo `orders-app-ci-demo`, created and deleted in this episode. Public because required reviewers, environment secrets and artifact attestations need a public repo on the Free/Pro/Team plans (GitHub docs). | none (GitHub-hosted runners) |
| GitHub Packages | Container package `orders-app-ci-demo` in GHCR, created by the first run, made **public** once (App Service pulls it anonymously), deleted at tear-down. | none |
| Azure resource group `rg-mglab-devtools-05` (West Europe) | `asp-<appName>`: App Service plan **B1 Linux** · `<appName>`: Web App for Containers · `id-<appName>-deploy`: user-assigned managed identity + federated credential `github-production` · role assignment Website Contributor on the group | B1 Linux EUR 0.0162/hour (Retail Prices API, 21 Nov 2026): about EUR 0.10 for a 6-hour window. Identity, role assignment: no charge |
| Recording laptop (Windows 11) | Browser signed in to GitHub (recording account) and the Azure portal (`labadmin`); Windows Terminal with **git**, **GitHub CLI** (`gh auth login`, scopes `repo`, `workflow`, `read:packages`; `delete_repo` and `delete:packages` added at tear-down), **Azure CLI** (`az login` as `labadmin`), Python 3. No Docker needed on the laptop: the containers run on GitHub's runner. | none |

`<appName>` must be globally unique, e.g. `contoso-orders-<4 random letters>`. Keep the owner and repo names
lower case (GHCR image names must be lower case; the workflow uses `ghcr.io/${{ github.repository }}`).

## Setup (off camera, in this order)

The order matters: the `production` environment, its reviewer and its secrets must exist **before** the first push
to `main`, or the first deploy runs without the gate.

```powershell
# 0. variables
$owner = "<github-owner>"; $repo = "orders-app-ci-demo"; $app = "contoso-orders-<xxxx>"
$rg = "rg-mglab-devtools-05"

# 1. empty public repo (no push yet)
gh repo create "$owner/$repo" --public --description "DEVLADLOG Dev Tools #5 demo (throwaway)"

# 2. the exact OIDC subject for this repo (new repos get the immutable owner@id/repo@id format)
gh api "repos/$owner/$repo" | python tools/oidc_subject.py --environment production
#   run from a copy of src/orders-app; note the printed subject
```

3. Azure (Windows Terminal, `az login` as `labadmin`, lab subscription selected):

```powershell
az group create -n $rg -l westeurope
az deployment group create -g $rg -f infra/main.bicep -p appName=$app githubSubject="<subject from step 2>" `
  --query properties.outputs
```

Keep the outputs (`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `AZURE_WEBAPP_NAME`,
`AZURE_RESOURCE_GROUP`, `url`) off screen. Wait a few minutes after creating the federated credential (Learn:
propagation can make the first token request fail with AADSTS70021).

4. GitHub → repo **Settings → Environments → New environment** `production`:
   - **Required reviewers**: the recording account. Leave **Prevent self-review** off (the same person merges and
     approves in this demo).
   - **Deployment branches and tags**: Selected branches → `main`.
   - Then from the terminal:

```powershell
gh secret set AZURE_CLIENT_ID       --env production --repo "$owner/$repo" --body "<output>"
gh secret set AZURE_TENANT_ID       --env production --repo "$owner/$repo" --body "<output>"
gh secret set AZURE_SUBSCRIPTION_ID --env production --repo "$owner/$repo" --body "<output>"
gh variable set AZURE_WEBAPP_NAME    --env production --repo "$owner/$repo" --body $app
gh variable set AZURE_RESOURCE_GROUP --env production --repo "$owner/$repo" --body $rg
```

5. Push the code and let the first run happen (warm-up, not recorded):

```powershell
git clone "https://github.com/$owner/$repo.git"; cd $repo
Copy-Item -Recurse -Force <mg-lab>\series\developer-tools\episodes\05-ci-cd-pipeline-setup\src\orders-app\* .
Get-ChildItem -Force .github\workflows    # ci-cd.yml must be there (dot folders included)
git add -A; git commit -m "chore: import orders api"; git push -u origin main
```

   - The run: guardrails, build-test, e2e, publish green; deploy **Waiting**.
   - Before approving: GitHub → profile → **Packages** → `orders-app-ci-demo` → Package settings → Danger Zone →
     **Change visibility → Public** (can't be undone; the package is deleted at tear-down).
   - Approve the deployment, check the deploy job passes and `<url>/healthz` shows the commit SHA.
6. Prepare the PR for the first screen: `git switch -c feat/service-name`, add `service = "contoso-orders",` to the
   `/healthz` object in `Program.cs` (no test change needed), commit `feat(orders): name the service in healthz`,
   push the branch. Don't open the PR yet.

## Screens to capture

| Scene id | File | What must be on screen |
|---|---|---|
| `prchecks` | `screens/prchecks.jpg` | Open the PR (`gh pr create --fill` or the web UI). 1) PR **Checks** list: `guardrails`, `build-test`, `e2e` green; `publish` and `deploy` skipped. 2) The `e2e` job log, `scripts/e2e.sh` step expanded: `docker compose up` with `db` **Healthy**, the SQL Server tests (`Passed: 4`), the trx table, then the smoke lines ending `7 passed, 0 failed`. 3) The run **Summary** page: the Tests tables (unit and SQL Server) and the Smoke test list. |
| `package` | `screens/package.jpg` | After the merge run's publish job: the package page with tags `sha-<commit>` and `main` and the digest; the publish job **Summary** (image, digest, verify command). Then Windows Terminal: `gh attestation verify oci://ghcr.io/<owner>/orders-app-ci-demo@<digest> -R <owner>/orders-app-ci-demo` with the success output (signer workflow `.github/workflows/ci-cd.yml`). |
| `approval` | `screens/approval.jpg` | Merge the PR (squash; title is the commit message). Actions → the `ci-cd` run on `main`: graph with four green jobs and `deploy` **Waiting**; click **Review deployments**, tick `production`, comment "release", **Approve and deploy**. Capture before and after. |
| `live` | `screens/live.jpg` | The `deploy` job log: `azure/login` login succeeded with OIDC, `webapps-deploy` done, smoke step polling then `✓ /healthz ok and version <sha>` and `4 passed, 0 failed`. Then the environment URL (click it in the run graph) + `/healthz` in the browser: `"version"` = the merge commit SHA, `"database":"Sqlite"`, `"user":"app"`, next to the commit on GitHub. Optional: Azure portal → the web app → Deployment Center → Logs showing the image `ghcr.io/...:sha-<commit>`. |

## Checks to make during recording (fix README/tests if any differs)
1. The ubuntu runner has Docker Compose v2 with `--wait`: the e2e job reaches `db Healthy` and the SQL Server tests
   report `Passed: 4` (if the `trx_check` gate fails, read why before changing anything).
2. `azure/login` succeeds with the role on the **resource group** only. If it fails with "No subscriptions found",
   note the message; the fix is a Reader assignment on the subscription for the identity (broader), and README must
   say so.
3. `webapps-deploy` works with basic auth (FTP/SCM) disabled and returns a non-empty `webapp-url`; if the URL is
   empty, the smoke step fails fast: note it.
4. App Service picks up port 8080 from `WEBSITES_PORT`, the container starts within the 10-minute smoke budget; note
   how long the poll took (for the narration "keeps polling").
5. If the login fails with `AADSTS700213`, copy the subject from the message into the federated credential
   (`az identity federated-credential update`) and note which format GitHub sent; update the gotcha if needed.
6. `gh attestation verify` output wording; and that `docker/build-push-action`'s own provenance didn't conflict
   with `actions/attest` (both attach to the digest).
7. Note the run durations (e2e pulls the SQL Server image every run).

## Masking
- Azure: subscription ID, tenant ID, client ID (the job log masks the secrets, the portal doesn't), `labadmin`
  account picker, the Azure CLI deployment output (don't show it).
- GitHub: the account avatar/menu; the owner name if the recording account isn't the public devladlog account;
  the Environments page secret names are fine, values are never shown.
- The App Service default hostname is fictional (`contoso-orders-...`), fine to show.

## Tear-down
1. `az group delete -n rg-mglab-devtools-05 --yes` (plan, site, identity, federated credential, role assignment).
2. `gh auth refresh -s delete:packages,delete_repo`
3. `gh api -X DELETE /user/packages/container/orders-app-ci-demo` (for an organization owner:
   `/orgs/<org>/packages/container/orders-app-ci-demo`).
4. `gh repo delete <owner>/orders-app-ci-demo --yes` (removes the environment, its secrets, the runs and the
   GitHub Actions cache).
5. Remove the local clone; `gh auth refresh -r delete:packages,delete_repo` to drop the extra scopes.
