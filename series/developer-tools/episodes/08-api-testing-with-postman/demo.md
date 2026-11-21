# Demo shot list — DEVLADLOG Dev Tools #8, API testing with Postman

Already real (build machine, 21 Nov 2026): the API with its OpenAPI document, the collection, both Newman runs, the gates, the regression
(`MaxPageSize` 100 → 1000 fails exactly one test), the zero-tests gotcha, the workflow's contract. `dotnet test`: 23 passed, 4 skipped; `pytest`: 45 passed.
**Recorded here for the first time:** the Postman desktop app (import, Tests tab, Collection Runner), the API as a container on Docker Desktop, the script in
Windows Terminal, the workflow on GitHub-hosted runners. Status: **needs the recording laptop, a Postman account and GitHub**. No Azure, no lab VMs.

## Lab environment

| What | Details | Cost |
|---|---|---|
| Recording laptop (Windows, the lab host) | Docker Desktop (WSL 2 backend), Node.js 22 LTS, .NET SDK 10 (`global.json` asks for 10.0.100, `rollForward: latestFeature`), Python 3, Git for Windows (Git Bash gives `bash` and `curl`; WSL works too), GitHub CLI (`gh`), Windows Terminal. All screens are recorded here. | none |
| Postman desktop app | Latest version from postman.com, **free plan**. The app needs a sign-in: create one account with the lab Microsoft 365 user `labadmin`'s mailbox (never the owner's own account), and note the sign-up in the lab inventory. Before recording, open *Resource usage* in the app and check that Collection Runner is available (Postman's docs say runner runs are unlimited on 2026 plans). | none |
| GitHub | Same account as `github.com/devladlog/mg-lab`. One **public** throwaway repo `orders-app-api-tests`, created and deleted in this episode. Hosted runners (public repo: free). | none |
| The API under test | Container `contoso/orders-api:dev`, built on the laptop from `src/orders-app/Dockerfile` (single container, SQLite in `/data`, **Production** mode), published on `127.0.0.1:8080`. No SQL Server needed. | none |

Postman is not a Microsoft product, so the Postman facts in this episode come from Postman's own documentation (see the README references), not from Microsoft Learn.

## Prepare (before recording, off camera)

```bash
# Git Bash, WSL or PowerShell with Git on the PATH; from a clone of mg-lab
cd series/developer-tools/episodes/08-api-testing-with-postman/src/orders-app
(cd api-tests && npm ci --no-audit --no-fund)                 # Newman 6.2.3 from the lock file
docker build -t contoso/orders-api:dev .                       # restore is locked: packages.lock.json already has Microsoft.AspNetCore.OpenApi
docker run --rm -d --name orders-api -p 127.0.0.1:8080:8080 contoso/orders-api:dev
curl http://localhost:8080/openapi/v1.json | head -c 300       # the document is served by the container
curl http://localhost:8080/healthz                             # "version":"dev", "inContainer":true
```

Not verified on the build machine (no Docker daemon there): `docker build` of this folder. Episode 4/5's Dockerfile is unchanged, the locked restore
for `-a x64` and `-a arm64` was checked, and `api-tests/` is in `.dockerignore`. If the build fails, fix it before recording and report it.

Check once, off camera: **does importing `openapi.v1.json` give requests with no tests?** The narration of the *import* scene says the assertions are ours to write
(Postman's docs mention folders, requests and response examples, not tests). If the import adds tests, change that sentence.

## Screens (match the `screen` scenes in script.yaml)

1. **`screens/import.jpg` — Postman · Import**
   - New empty workspace (name it `orders-api-demo`). *Import* → drop `api-tests/openapi.v1.json`.
   - Show the import options (collection only vs. specification with a collection), choose *collection*, then the generated collection: folders, `/healthz`, `/orders`, `/orders/{id}`.
   - Open one request (`POST /orders`) and a saved example. Open its *Tests* tab: empty. (This is the point of the scene.)
   - Then import `orders-api.postman_collection.json` and `environments/local.postman_environment.json` for the rest of the demo (import them as a second collection named "Contoso Orders API").

2. **`screens/runner.jpg` — Postman · results and Collection Runner**
   - Select the environment **local** (`baseUrl` = `http://localhost:8080`).
   - Open *Contoso Orders API → Orders → Create order*. Show the *Pre-request Script* and *Tests* tabs, press **Send**: *Test Results* shows 5 passing.
     Open the *Variables* tab on the collection: `orderId` and `createdOrder` are filled.
   - *Run collection* (Runner): tick **Health, Orders, Validation** (leave *Data-driven* off), Run. Show all requests green and the totals (31 assertions with `expectedVersion` empty).
   - Optional, if the account allows a custom data file in the Runner: run **Data-driven** with `data/invalid-orders.json` (6 iterations). If Postman asks for a paid plan,
     skip it in the app and show the same run in the terminal (screen 3 does). Do not buy a plan.
   - Mask: account name and email, workspace owner.

3. **`screens/regression.jpg` — Windows Terminal · the script, green then red**
   ```bash
   cd series/developer-tools/episodes/08-api-testing-with-postman/src/orders-app
   bash scripts/run-api-tests.sh ; echo "exit code: $?"
   ```
   - Capture: "Starting the API on http://127.0.0.1:<port>", both Newman tables (0 failed), the two gate lines `junit-main.xml: 31 passed, 0 failed ...` and `junit-data.xml: 24 passed ...`, `exit code: 0`.
   - Stop the container first if port 8080 is needed elsewhere (the script picks a free port, so it doesn't conflict).
   - Edit `src/Contoso.Orders.Api/Orders.cs` in VS Code: `MaxPageSize = 100;` → `MaxPageSize = 1000;`. Run the script again. Capture the one failed assertion
     (`cap: asking for 500 returns at most 100`), the failure summary at the end of the Newman run, the gate line `✗ failed: cap: asking for 500 returns at most 100`, `exit code: 1`.
   - Undo the edit (`git checkout -- src/Contoso.Orders.Api/Orders.cs` or Ctrl+Z).
   - Windows note: run it in Git Bash or WSL. If `dotnet run` is slow to start, the script waits up to 60 s for `/healthz`.

4. **`screens/ci.jpg` — GitHub · Actions**
   ```bash
   mkdir /c/work && cp -r src/orders-app /c/work/orders-app-api-tests    # without node_modules: delete it from the copy first
   cd /c/work/orders-app-api-tests && rm -rf api-tests/node_modules
   git init -b main && git add . && git commit -m "chore: import the orders API with its Postman collection"
   gh repo create orders-app-api-tests --public --source=. --push
   git switch -c test/show-the-gates
   echo "# Changelog" > CHANGELOG.md && git add . && git commit -m "docs: add a changelog" && git push -u origin test/show-the-gates
   gh pr create --fill
   ```
   - The workflow runs `bash scripts/run-api-tests.sh`, so the file mode doesn't matter on Windows. Line endings: `.gitattributes` forces LF for `*.sh` and `*.py`.
   - Capture the run page `api-tests`: the steps *Lint the collection and the environments* (`✓ 10 requests, 1 environment(s): no problems`),
     *Every documented operation and response has a test* (the 4-row table, all `ok`, `✓ 4 operations, all covered`),
     *Run the collection against the API built from this commit* (Newman output; the gate lines show **32** and **24** because CI sets `EXPECTED_VERSION` to the commit),
     then the run summary with the artifact **api-test-results** (`junit-main.xml`, `junit-data.xml`).
   - Optional, 10 seconds: push a commit that adds a new endpoint to the API without a request and show the coverage step failing. Not scripted; only if time allows.
   - Mask the owner name if it isn't the public `devladlog` account.

## Optional b-roll: the Postman CLI (not in the script)

Postman recommends it in place of Newman. **Not verified by me** (its npm postinstall downloads a binary and I did not install it on the shared build machine).
On the laptop: `npm install -g postman-cli` (or the PowerShell installer from Postman's install page), then
`postman collection run api-tests/orders-api.postman_collection.json -e api-tests/environments/local.postman_environment.json -i Health -i Orders -i Validation`.
Postman's docs say a local file path needs no sign-in and `-i` runs only the named folders. If it runs, keep it as 10 seconds of b-roll over the "Newman or the CLI" sentence;
if it asks to migrate the v2.1 file, `postman collection migrate` is the documented route; if anything fails, leave it out and write it into the README gotchas.

## Tear-down

- `docker rm -f orders-api` and `docker rmi contoso/orders-api:dev`.
- Postman: delete the workspace `orders-api-demo` (and the imported collections and environment inside it). The free account stays; its sign-up is recorded in the lab inventory.
- GitHub: `gh repo delete devladlog/orders-app-api-tests --yes`; delete `C:\work\orders-app-api-tests`.
- Repo working copy: `rm -rf src/orders-app/api-tests/node_modules src/orders-app/api-tests/results src/orders-app/src/*/bin src/orders-app/src/*/obj src/orders-app/tests/*/bin src/orders-app/tests/*/obj`, and `git checkout` any file edited for the regression scene.
