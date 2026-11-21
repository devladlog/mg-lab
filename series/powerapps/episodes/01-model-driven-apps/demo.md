# Demo shot list — DEVLADLOG Power Apps #1, Model-driven apps

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs / Azure | none |
| Tenant environment | Power Platform environment **`DEV`** (Dataverse; not a developer environment). Created here: publisher `contoso`, solution *Equipment Desk*, tables Equipment and Loan, model-driven app, site map, web resource (kept for episodes 2–4, removed in tear-down after the series) |
| Lab users | `labadmin` (the recording account) with System Administrator or System Customizer in `DEV`; signs in to Azure CLI off camera for the access token. Borrower values in the test loans are the lab users' addresses `alex.demo@contoso.com` / `sam.demo@contoso.com` as plain text (fictional domain) |
| Licences / trials | **Power Apps Premium** (in the lab) for `labadmin` and any lab user who runs the app; cost 0 |
| Recording machine | The Windows lab laptop: maker portal / Power Apps Studio / the running app in the browser with `pipeline/mask.js`; WSL (Ubuntu) bash with Node 22.18+ and Azure CLI for the provisioning script |

Everything under `src/` was built and tested locally (`npm test`: 38 passed). The steps below **need the lab tenant**
and have not been run there yet: the recorder is the first real run, so watch the console output of step 3.

## Prerequisites
| What | Notes | Cost |
|---|---|---|
| MG Lab **DEV** environment with Dataverse | Use the existing lab DEV environment. Learn: unmanaged developer environments (the ones the Developer Plan created) are deprecated — no new ones since 15 Nov 2026, suspension from 15 Dec 2026. Don't build the demo in one. | existing |
| `labadmin` (recording user) with **System Administrator** or **System Customizer** in DEV | Learn: required to create apps | — |
| Power Apps **premium** licence (or trial) for the recording user | Learn: makers need a licence to build model-driven apps; every user running one needs premium | existing / trial |
| Azure CLI on the recording machine, signed in as the recording user | for the access token only (`az account get-access-token`) | — |
| Node 22.18+ | runs the TypeScript directly | — |

## Setup (off camera)
1. `cd src && npm ci --no-audit --no-fund && npm test && npm run build` → expect `pass 38`, bundle ~6 KB.
2. `npm run plan` → 39 requests, 19 writes. (Capture this terminal for the `dryrun` scene if a fresh take is wanted.)
3. Provision:
   ```bash
   export DATAVERSE_URL=https://<lab-dev-org>.crm4.dynamics.com     # never on screen
   export DATAVERSE_TOKEN=$(az account get-access-token --resource $DATAVERSE_URL --query accessToken -o tsv)
   node provision/provision.ts --webresource dist/contoso_/scripts/loanform.js --role "Basic User"
   ```
   Expected: `created publisher contoso` … `published tables and app` … `granted app to role 'Basic User'`.
   **If a step fails:** note the exact Dataverse message, fix the payload in `src/provision/metadata.ts`, add a test,
   re-run (the script is idempotent). Report it as a real gotcha in the README. Fallback if the site map/app steps fail:
   create the app in the app designer (New → App → Model-driven, add Equipment and Loans pages) and say so in the
   narration — don't present designer work as script output.
4. Run it a second time: expect `0 created` (everything `exists`, site map `updated`). Good proof for the idempotency line.
5. Loan main form → **Events → On Load → + Event handler**: library `contoso_/scripts/loanform.js`, function
   `Contoso.LoanForm.onLoad`, check **Pass execution context as first parameter**. Add the Equipment lookup, Borrower
   email, Loan date, Due date, Returned on and Notes to the form if the default form lacks them. **Save and publish.**
6. Test data (fictional, in the app): equipment `CT-0042 Laptop` (Laptop, Available), `CT-0107 Monitor`, `CT-0311 Phone`;
   loans for `alex.demo@contoso.com` and `sam.demo@contoso.com`, one of them with a due date **three days ago** and no
   returned date (for the overdue banner).

## Screens to capture (match `screen` scenes in script.yaml)
| Scene | File | What must be on screen |
|---|---|---|
| `solution` | `screens/solution.jpg` | Solutions → Equipment Desk → Objects: tables Equipment and Loan, app Equipment Desk, site map, web resource `contoso_/scripts/loanform.js` |
| `designer` | `screens/app-designer.jpg` | Modern app designer: navigation with area *Equipment Desk*, group *Lending*, pages Equipment and Loans; preview of the Loans view with the test loans |
| `handler` | `screens/form-handler.jpg` | Form designer, Loan main form, On Load handler dialog with library, function name and the **Pass execution context** checkbox (highlight it) |
| `live` | `screens/due-date-error.jpg` | Running app, New Loan: defaults filled, loan name auto-filled, due date before loan date → red field notification "Due date can't be before the loan date."; save attempt blocked |
| `live` (cutaway) | `screens/overdue-banner.jpg` | Existing loan due three days ago: yellow banner "Overdue by 3 days. Contact the borrower." |

Optional terminal captures: `npm test` (38 passed) and the provisioning run (with the URL masked).

## Masking
- Environment name/URL, org URL in the terminal (`DATAVERSE_URL`), user name/avatar, tenant name in the header.
- Never show the access token: don't `echo $DATAVERSE_TOKEN`, clear the terminal before recording.
- Use `pipeline/mask.js` in the browser; `series_label: "POWER APPS"` is set in `script.yaml`.

## Tear-down
1. Remove the app's role association if it shouldn't stay (app → Share).
2. Solutions → Equipment Desk → **Delete** removes only the solution container; to remove the components delete the
   app, site map, web resource and the two tables (Loan first: the lookup restricts deleting Equipment rows, and the
   relationship goes with the Loan table).
3. Optionally delete the `contoso` publisher if nothing else uses it.
4. Sign out of Azure CLI on the recording machine (`az logout`) if it was signed in only for this.
