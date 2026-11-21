# Demo shot list - DEVLADLOG Code #8 Python for Azure, without a single key

Built and tested in the container (46 tests, ruff and mypy strict clean, `bicep build` and `bicep lint` clean). The Azure
screens below were **not** captured in the container: they need the lab subscription and a signed-in `az`, which the
container does not have. Reference output for everything that was run locally (tests, CLI against the Azurite emulator,
gotchas): [`demo/expected-output.txt`](demo/expected-output.txt). Azurite is for the automated tests only: **no screen shows
the emulator**.

## Lab environment
| What | Details | Cost |
|---|---|---|
| Machine | The Windows recording laptop (host). No VM needed. | - |
| Python | 3.12 or newer (tested here on 3.13.18). `python -m venv .venv`, then `.venv\Scripts\Activate.ps1`, then `pip install -e .` | free |
| Azure CLI | Installed on the laptop; **the recorder signs in with `az login` and selects the lab subscription**. No credential is ever typed on screen or saved to a file. | free |
| Azure subscription | The lab subscription (needs tenant). The signed-in user must be allowed to create resources and role assignments (Owner on the resource group is enough). | - |
| Resource group | `rg-mglab-code-08`, region **West Europe** | - |
| Storage account | `infra/main.bicep`: StorageV2, **Standard_LRS**, shared key access off, TLS 1.2, no public blob access, containers `requests` and `packs`. About 15 KB of data and a few hundred requests. | estimated well under 0.01 EUR for the session (pay-as-you-go storage and transactions; check the pricing page on the day) |
| Windows Terminal | dark theme, font 18 pt or larger, ~150 columns, prompt `> ` | free |

## Setup (once, before recording) - needs tenant
```powershell
cd C:\lab\mg-lab\series\programming-languages\episodes\08-python-for-azure-development   # neutral path
python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -e ".[dev]"
python -m pytest -q -m "not integration"      # rehearsal without Azurite: expect 36 passed, 10 deselected
az login                                       # interactive, by the recorder
az group create -n rg-mglab-code-08 -l westeurope
$me = az ad signed-in-user show --query id -o tsv
$sa = "stcontosomglab" + (Get-Random -Minimum 1000 -Maximum 9999)    # 3-24 lowercase letters and digits, globally unique
az deployment group create -g rg-mglab-code-08 -f infra\main.bicep -p storageAccountName=$sa principalId=$me assignRole=false --query properties.outputs.blobEndpoint.value -o tsv
$env:CONTOSO_STORAGE_ACCOUNT_URL = "https://$sa.blob.core.windows.net"     # a URL, not a secret
```
This first deployment creates the account and containers but **no role**, so screen 1 shows the 403. After that take,
grant access (the same deployment with `assignRole=true`, or the Learn quickstart command):
```powershell
az deployment group create -g rg-mglab-code-08 -f infra\main.bicep -p storageAccountName=$sa principalId=$me assignRole=true -o none
```
Role changes can take up to 10 minutes to take effect (Learn). Rehearse once, and wait before the "works" take.
`cls` before each capture. The environment variable holds only a URL, not a secret.

## Screens (match the `screen` scenes in script.yaml) - all needs tenant except screen 4

1. **`screens/denied.jpg`** - *Signed in, and still denied* (scene `denied`, also a Short). **Needs tenant.**
   - Deployed with `assignRole=false`. `contoso-azure seed samples\requests.csv`
   - Frame: `error: 403 AuthorizationPermissionMismatch: you are signed in, but your identity has no data-plane role. ...`
     (the friendly text from `errors.py`). Optionally show `az role assignment list --scope $scope -o table` empty first.
   - If Azure returns a different error code than the code expects, say so in the take: the text only appears for
     `AuthorizationPermissionMismatch`. Not verified against the real service yet.

2. **`screens/run.jpg`** - *One role, and it works* (scene `run`). **Needs tenant.**
   - Deploy with `assignRole=true` (command above), wait a few minutes, then `contoso-azure seed samples\requests.csv`,
     `contoso-azure process`, `contoso-azure list`.
   - Frame: `9 valid, 4 rejected, 1 without a route`, four `rejected row N: error_id` lines, `packs: 8 written, 0 already existed`,
     eight `packs/...json` names. Then portal: storage account, **Data storage > Containers > packs**, **mask the account name**.
   - The portal may show a banner about the authentication method: use "Microsoft Entra user account" (shared key is off).

3. **`screens/rerun.jpg`** - *The second run changes nothing* (scene `rerun`). **Needs tenant.**
   - `contoso-azure process` -> `packs: 0 written, 8 already existed`.
   - `contoso-azure process --use-async --concurrency 4 --overwrite` -> `packs: 8 written, 0 already existed`.
   - Portal: open `IT/PR-2026-0304.json`, frame three approvers (Alex, Sam, Taylor Demo).

4. **`screens/gotchas.jpg`** - *Three gotchas, running* (scene `gotchas`). **No tenant: pure Python on the laptop.**
   - `cls; python demo\gotchas.py`; compare with the last block of `demo/expected-output.txt`.
   - Frame: 0 versus 1 valid rows, the Decimal error, `NOT reached`, and `except* ... caught 1 error`.

The code scenes (`auth`, `client`, `idempotent`, `asyncio`, `taskgroup`) and the bullet scenes are slides with excerpts from
`src\contoso_azure`. The `tests` scene's claims (46 tests) are in `demo/expected-output.txt`.

## Masking
- Mask the storage account name and the subscription name or id in every frame: terminal prompt, portal URL bar and the
  portal overview. The terminal shows only `$env:CONTOSO_STORAGE_ACCOUNT_URL` if you echo it: do not echo it.
- Do not show `az account show` output, the tenant id or the signed-in user's e-mail. `az login` happens off camera.
- Data is fictional (`PR-2026-03xx`, Alex/Sam/Jordan/Riley/Taylor Demo as plain strings).
- Never run `az storage account keys list` on camera: the point of the episode is that there are no keys.

## Tear-down - needs tenant
```powershell
az group delete -n rg-mglab-code-08 --yes --no-wait
az group exists -n rg-mglab-code-08          # false after a few minutes
Remove-Item Env:CONTOSO_STORAGE_ACCOUNT_URL; deactivate
Remove-Item .venv -Recurse -Force
```
- Deleting the resource group removes the storage account and the role assignment. Check the portal that no
  `rg-mglab-code-08` is left, and that no storage account from this episode remains in the subscription.
- Nothing in the repo contains a key, a connection string for a real account, or an account name.
