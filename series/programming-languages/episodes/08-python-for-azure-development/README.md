# DEVLADLOG Code #8 - Python for Azure Development

Series: `programming-languages` (DEVLADLOG Code). Blog: <https://www.devladlog.com/articles/programming-languages/2025-06-10-python-for-azure-development-complete-guide-2025/>

Contoso's project requests (the same `requests.csv` and `approvers.json` scenario as the earlier episodes) are parsed with
pure Python rules and written as one JSON approval pack per request to **Azure Blob Storage**, with no key, no connection
string and no secret anywhere: Microsoft Entra ID plus one data role. Writes are idempotent, and there is a sync and an
async path.

## What is here
| Path | What |
|---|---|
| `src/contoso_azure/domain.py` | Pure rules: `Decimal` budgets, priority (>= 50,000 High, >= 250,000 Board), row validation with error ids and row numbers, routing, pack document. No Azure imports. |
| `src/contoso_azure/auth.py` | `build_credential`: `dev` is `DefaultAzureCredential` without the managed-identity probe; `azure` is exactly `ManagedIdentityCredential`. |
| `src/contoso_azure/config.py` | Settings from environment variables, validated before any network call (URL, container naming rules). |
| `src/contoso_azure/clients.py` | Retry and timeout policy; client factories (real account, and Azurite for tests). |
| `src/contoso_azure/store.py`, `store_async.py` | Blob store: `upload_blob(overwrite=False)` turned into `PackStatus.EXISTS`; async version with a semaphore and `asyncio.TaskGroup`. |
| `src/contoso_azure/errors.py` | Turns 403 `AuthorizationPermissionMismatch` and friends into messages that name the fix. |
| `src/contoso_azure/pipeline.py`, `cli.py` | `seed`, `process`, `list` commands (`--use-async`, `--overwrite`, `--emulator` for local tests). |
| `infra/main.bicep` | Storage account (Standard_LRS, shared key off, TLS 1.2, no public blob access), containers `requests` and `packs`, Storage Blob Data Contributor assignment. |
| `tests/` | 46 tests: domain, config, auth, errors, CLI, and 10 integration tests against the Azurite emulator. |
| `demo/gotchas.py`, `demo/expected-output.txt` | Runnable gotchas (no Azure) and the real captured local output. |
| `script.yaml`, `demo.md` | Video script (14 scenes, 789 narration words) and shot list. |

## Run it
```bash
python -m venv .venv && . .venv/bin/activate        # Windows: .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m pytest -q -m "not integration"            # 36 tests, no emulator needed
ruff check . && mypy src
```
Integration tests need the Azurite blob emulator (Node.js). Install it into a project folder, not globally, and point to it:
```bash
npm install --prefix /tmp/azurite azurite
AZURITE_BIN=/tmp/azurite/node_modules/.bin/azurite-blob python -m pytest -q    # 46 passed
```
Without `AZURITE_BIN` or `azurite-blob` on the PATH, the 10 emulator tests are skipped (checked: `36 passed, 10 skipped`).

Against a real account (after `az login` and the role assignment, see `demo.md`):
```bash
export CONTOSO_STORAGE_ACCOUNT_URL=https://<account>.blob.core.windows.net
contoso-azure seed samples/requests.csv
contoso-azure process
contoso-azure list
```
Against the emulator: `contoso-azure --emulator seed samples/requests.csv` (and the same for `process` and `list`).

Verified here (Python 3.13.18, azure-identity 1.27.0, azure-storage-blob 12.31.1, Azurite 3.38.0, Bicep 0.49.2):
`46 passed`, `ruff` clean, `mypy` strict clean on 11 source files, `bicep build` and `bicep lint` clean, and a fresh venv
install with `pip install -e ".[dev]"`. **Not verified here:** anything against real Azure (no sign-in or subscription in
the build environment), Windows, Python 3.12, the managed identity path (`--auth azure`, only runs inside Azure), and the
exact text of the real 403 response, which the tests simulate.

## Gotchas (all hit while building)
- **A signed-in Owner is still denied.** Owner, Contributor and Storage Account Contributor manage the account but give no
  blob data access through Entra ID. You need a data role such as Storage Blob Data Contributor.
- **Role changes are not instant.** Learn says up to 10 minutes for blob data access.
- **`--emulator [URL]` swallowed the subcommand.** An optional-value flag in `argparse` takes the next word, so
  `--emulator seed file.csv` failed. Fixed: `--emulator` is a flag and `--emulator-url` is separate (see `tests/test_cli.py`).
- **Container names have rules** (3-63 lowercase letters, digits and single hyphens): a one-letter name failed in the first
  smoke test, so the config validates them before any request.
- **Excel's "CSV UTF-8" starts with a byte order mark.** Decoded as `utf-8` the first column is renamed and every row
  fails; decode with `utf-8-sig`.
- **`Decimal` is not JSON serializable.** The pack stores the budget as a string; a float would lose exactness.
- **`TaskGroup` raises `ExceptionGroup`,** even for one failure: `except ResourceNotFoundError` does not catch it,
  `except*` does.
- **Blob names are case-sensitive.** `IT/...` and `it/...` are different blobs; the route carries the canonical department
  spelling from the approvers file.
- **`DefaultAzureCredential` is for development.** Learn recommends a specific credential once deployed; `auth.py` does so.
- **Azurite is not Azure.** Great for fast tests, but it cannot show an RBAC problem, so no demo screen uses it.

## References
- Quickstart, Blob Storage client library for Python (passwordless, Storage Blob Data Contributor, `DefaultAzureCredential`): <https://learn.microsoft.com/azure/storage/blobs/storage-quickstart-blobs-python>
- Credential chains in the Azure Identity library for Python (usage guidance for `DefaultAzureCredential`): <https://learn.microsoft.com/azure/developer/python/sdk/authentication/credential-chains>
- Authorize access to blobs by using Microsoft Entra ID (management roles do not grant data access; propagation delay): <https://learn.microsoft.com/azure/storage/blobs/authorize-access-azure-active-directory>
- Assign an Azure role for access to blob data: <https://learn.microsoft.com/azure/storage/blobs/assign-azure-role-data-access>
- Prevent Shared Key authorization for an Azure Storage account (`allowSharedKeyAccess: false`): <https://learn.microsoft.com/azure/storage/common/shared-key-authorization-prevent>
- Use the Azurite emulator for local Azure Storage development: <https://learn.microsoft.com/azure/storage/common/storage-use-azurite>
- Azure Storage Blobs client library for Python: <https://learn.microsoft.com/python/api/overview/azure/storage-blob-readme>
- Blog article (generic overview, no code reused): <https://www.devladlog.com/articles/programming-languages/2025-06-10-python-for-azure-development-complete-guide-2025/>
