# Demo shot list — DEVLADLOG .NET #1 Minimal APIs

Everything in `src/` and `tests/` was built and tested in the container (`dotnet test`: 22 passed). The local
screens (`local-smoke`, `openapi`) need no tenant. **Needs tenant (Azure subscription):** `live-smoke`, `readonly`,
`restart-empty`.

## Prerequisites
| What | Notes | Cost |
|---|---|---|
| .NET SDK 10.0.1xx | `dotnet --version` | free |
| Azure CLI, signed in to the **lab** subscription | `az login` (done by the recorder, never on screen) | free |
| Resource group + App Service plan **Free F1, Linux** + web app | created by `deploy/deploy-appservice.sh` | €0 (F1). Check the €10 budget alert exists anyway |
| `zip`, `curl` | used by the scripts | free |
| Masking | `pipeline/mask.js` for the portal; crop/blur terminal host names | — |

Pick a neutral app name, e.g. `APP=contoso-requests-<4 random digits>`. Never show the subscription name, tenant
name, account e-mail or resource IDs.

## Setup
```bash
cd series/net/episodes/01-minimal-apis
dotnet test -m:1                                  # expect Passed: 22
dotnet run --project src/ProjectRequests.Api      # leave running for the two local screens
```

## Screens (match the `screen` scenes in script.yaml)

1. **`screens/local-smoke.jpg`** — *The walk-through, locally*
   - Second terminal, dark theme, font ≥ 18 pt: `./deploy/smoke.sh http://localhost:5207`
   - Frame must show: step 1 `<- HTTP 400` with `Title`, `Budget`, `RequestedBy` errors; step 2 the `Justification`
     error; step 3 the 201 body with `"priority":"High"`; step 4 `<- HTTP 409` "You can't decide your own request."
   - Reference output: [`deploy/smoke-local.output.txt`](deploy/smoke-local.output.txt). Nothing to mask.

2. **`screens/openapi.jpg`** — *OpenAPI: every status code, documented*
   - Browser at `http://localhost:5207/openapi/v1.json` with the JSON viewer. Collapse everything, then expand
     `openapi` (3.1.1) and `paths → /api/requests/{id}/decision → post → responses` showing 200, 400, 404, 409, 503.
   - Stop `dotnet run` afterwards.

3. **`screens/live-smoke.jpg`** — *Live on App Service* (**needs tenant**)
   - `APP=contoso-requests-XXXX ./deploy/deploy-appservice.sh` (≈ 2–4 min). Capture the tail: `==> https://…/healthz`
     and `Healthy`.
   - Then `./deploy/smoke.sh https://<host>` and capture step 3 (201, High) and step 5 (200, Approved).
   - **Mask** the host name except `.azurewebsites.net`. Leave this request in place for screen 5.

4. **`screens/readonly.jpg`** — *Pause writes without a deploy* (**needs tenant**)
   - Portal → the web app → **Settings → Environment variables → App settings** → set `Api__ReadOnly` to `true` →
     **Apply** (or `az webapp config appsettings set -g rg-mglab-net01 -n $APP --settings Api__ReadOnly=true`).
   - Terminal next to it:
     `curl -i -X POST https://<host>/api/requests -H "Content-Type: application/json" -d '{"title":"CRM rollout","budget":75000,"requestedBy":"alex.demo@contoso.com"}'`
     → `HTTP/1.1 503`, `Retry-After: 120`, title "The API is in read-only mode."; then `curl -i https://<host>/api/requests` → 200.
   - **Mask** subscription, resource group path/IDs, host name. Use `pipeline/mask.js` on the portal.

5. **`screens/restart-empty.jpg`** — *The catch: a setting change restarts the app* (**needs tenant**)
   - `curl -s https://<host>/api/requests` → `[]` (the request from screen 3 is gone: the setting change restarted
     the app and the store is in memory). Optional: Log stream showing the restart. Mask the host name.

## Tear-down
```bash
az group delete --name rg-mglab-net01 --yes --no-wait
rm -rf deploy/out
```
Confirm in the portal that the resource group is gone.
