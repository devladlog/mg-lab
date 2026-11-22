# Demo shot list — DEVLADLOG .NET #4 Dependency Injection & DI Containers

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs / Power Platform | none |
| Lab users | `labadmin` (the recording account): `az login` off camera, portal for the Log stream |
| Azure | Resource group **`rg-mglab-net-04`** in **West Europe** (the deploy script's default region), created by the deploy script with `RG=rg-mglab-net-04` exported (the script's built-in default is `rg-mglab-net04`): App Service plan **Free F1, Linux** + one web app, SQLite file in `/home` (no database resource, €0). Tear-down: `az group delete --name rg-mglab-net-04` |
| Licences / trials | none beyond the subscription |
| Recording machine | The Windows lab laptop: WSL (Ubuntu) bash with .NET SDK 10.0.1xx, Azure CLI, `curl`, `jq`, `zip` (the `deploy/*.sh` scripts are bash); browser on the host for the portal and `localhost` screens (WSL forwards localhost ports) |

Code and tests were built and run in the container (`dotnet test -m:1`: 39 passed, three runs in a row).
`deploy/local-demo.sh` was run against the local API; output in [`deploy/local-demo.output.txt`](deploy/local-demo.output.txt).
The startup-validation failure was run for real; output in [`deploy/startup-validation.output.txt`](deploy/startup-validation.output.txt).
`PACKAGE_ONLY=1 ./deploy/deploy-appservice.sh` was run (18 MB zip; published app in Production: `/healthz` Healthy,
`/diagnostics/lifetimes` 404, `POST /api/digest/send` 200).
**Needs tenant:** `azure-log-stream`, `azure-validation` (Azure subscription). `lifetimes` and `startup-validation` don't.

## Prerequisites
| What | Notes | Cost |
|---|---|---|
| .NET SDK 10.0.1xx, `curl`, `jq`, `zip` | `dotnet tool restore` installs `dotnet-ef` 10.0.15 locally | free |
| Azure subscription (lab) with the €10 budget alert | App Service plan **Free F1, Linux**; no database resource (SQLite in `/home`) | €0 |
| Masking | `pipeline/mask.js` in the portal; blur app name/host, subscription, account | — |

## Setup

### Local (screens 1 and 2) — no tenant
```bash
cd series/net/episodes/04-dependency-injection-di-containers
dotnet tool restore
dotnet test -m:1                                                       # expect Passed: 39
cd src/ProjectRequests.Api
rm -f requests.db
dotnet dotnet-ef database update --context SqliteRequestsDbContext
dotnet run --launch-profile http                                       # leave running; digest logged every minute
```

### Azure (before screen 3) — needs tenant
```bash
az login                                                               # not on camera
az account set --subscription <lab subscription>
export RG=rg-mglab-net-04
APP=contoso-requests-<4 digits> ./deploy/deploy-appservice.sh          # ends with "Healthy"
./deploy/local-demo.sh https://<host>                                  # creates 2 requests (step 1 says Development only)
```

## Screens (match the `screen` scenes in script.yaml)

1. **`screens/lifetimes.jpg`** — *What the container actually hands out* (no tenant)
   - Second terminal, dark theme, font ≥ 18 pt: `./deploy/local-demo.sh` (only step 1 needs to be in frame).
   - In frame: two JSON lines. Transient differs endpoint vs consumer; scoped and dbContext equal within a line and
     different between lines; singleton identical in both. Optional: highlight boxes in the edit.

2. **`screens/startup-validation.jpg`** — *A bad setting, caught at startup* (no tenant)
   - Stop the running app. `cd src/ProjectRequests.Api && Notifications__Channel=webhook dotnet run --launch-profile http`
     then `echo $?` (on the Windows laptop, in PowerShell: `dotnet run --launch-profile http` then `$LASTEXITCODE`).
   - In frame: `Hosting failed to start`, `OptionsValidationException ... 'WebhookUrl' ... must be an absolute https
     URL when Channel is 'webhook'`, and the exit code: `134` on Linux, `-532462766` (0xE0434352, unhandled .NET
     exception) on Windows. The narration says no number. Crop the stack trace lines if the terminal is crowded.

3. **`screens/azure-log-stream.jpg`** — *The worker, live on App Service* (**needs tenant**)
   - Portal: web app → **Monitoring → Log stream** (or `az webapp log tail -g rg-mglab-net-04 -n <app>`).
   - Wait for a tick (interval 1 minute): `Digest worker run: 2 pending request(s)`, `Digest: 2 request(s) waiting
     more than 0 day(s) for a decision`, `FIN: 1 request(s), 12,000 total, oldest …`, `OPS: …`.
   - **Mask** app name, subscription, account.

4. **`screens/azure-validation.jpg`** — *Break the configuration on purpose* (**needs tenant**)
   - Keep the log stream open. `APP=<app> ./deploy/deploy-appservice.sh break` (changing an app setting restarts the app).
   - In frame: `Hosting failed to start` + the `OptionsValidationException` for `WebhookUrl`; browsing to `/healthz`
     shows the App Service error page. Then `./deploy/deploy-appservice.sh fix` and show `Digest worker run` again
     (second capture or a cut).
   - **Mask** app name and host.

## Tear-down
```bash
az group delete --name rg-mglab-net-04 --yes --no-wait
rm -f src/ProjectRequests.Api/requests.db
rm -rf deploy/out
```
Confirm in the portal that the resource group is gone (the SQLite file in `/home` goes with the app).
