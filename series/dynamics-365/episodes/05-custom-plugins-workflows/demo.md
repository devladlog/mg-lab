# Demo shot list — DEVLADLOG Dynamics 365 #5: Custom Plugins & Workflows

Already run in the build container: `dotnet test src/MGLab.D365.Plugins.Tests` (28 passed), `dotnet build
src/MGLab.D365.Plugins -c Release` (net462 DLL, unsigned: no key in the repo), `python3 -m pytest -q tests` (31 passed,
Web API stubbed) and `python3 -m apikit check`. **Nothing has run against Dataverse yet: all five `screen` scenes need
the lab tenant.** Numbers in the narration (scores, counts) must be replaced by what the lab really shows.

## Lab environment

No VMs and no Azure resources: cloud tenant only, recorded from a terminal and the browser on the recording laptop.

| Item | Notes | Cost |
|---|---|---|
| Power Platform environment **`DEV`** (Dataverse, exists) | **Why DEV:** the Project Request table, its data and the `MGLabDataverse` solution from episodes 1–4 live there; a custom table needs no Dynamics 365 app; episode 6 builds on this one in the same place | none |
| Dynamics 365 **"Sales trial"** environment (exists, ends ~21 Dec 2026) | Only for the second half of screen 5 (`workflows --all`): it ships the managed processes of a real Dynamics 365 app. Record it **before 21 Dec 2026**; if it has expired, drop that half | none (trial) |
| Episodes 1 and 3 done in DEV | `mgl_projectrequest` with the 18 imported records, Business Justification column | none |
| Lab users | `labadmin` (recording, System Customizer or System Administrator in DEV), `alex.demo` with episode 2's *Project Requester* role (or any role with read/write on Project Request) for the form screen | none (E5 + D365 trial licences exist) |
| Recording laptop | .NET 8 SDK, Python 3.10+ with `pip install --user -r requirements.txt`, terminal (dark, font 18+), browser with `pipeline/mask.js` | none |
| Strong-name key | `sn -k src/MGLab.D365.Plugins/MGLab.D365.Plugins.snk` on the laptop (never committed) | none |

## Setup (before recording)

1. Build the signed assembly on the laptop: `dotnet build src/MGLab.D365.Plugins -c Release -m:1` (check the build says
   nothing about a missing key: the `.snk` must be in `src/MGLab.D365.Plugins/`).
2. `export DATAVERSE_URL=https://<lab DEV>.crm4.dynamics.com` (sign in interactively as `labadmin`).
3. **Trace logging on** (DEV only): in the app, *Settings → Administration → System Settings → Customization tab →
   Enable logging to plug-in trace log = All* (Learn: Tracing and logging > Enable trace logging).
   Turn it back to *Off* or *Exception* in tear-down.
4. **Keep successful jobs for the recording:** in `plugins.json` set `"asyncautodelete": false` on both steps
   **only for the recording** (the deploy then shows them as updated if already deployed). Put it back to `true`
   and deploy again in tear-down.
5. **A classic workflow to find (screen 5):** in DEV → Solutions → MGLabDataverse → New → Automation → Process →
   **Workflow**. Name *Recalculate risk (classic)*, table *Project Request*, keep *Run this workflow in the background*
   checked. Start when: *Record fields change* → Budget. Add one step *Stop Workflow* (status Succeeded). Save,
   **do not activate** (it stays Off; it exists only to be found and replaced).
6. Add **Risk Score** (`mgl_riskscore`, created by the first deploy) to the Project Request main form, read-only, next
   to Budget. Publish. (Do this right after recording screen 1.)
7. Make sure PR-0004 has Budget 42,000, a due date about 10 days ahead and Business Justification empty, so the
   score visibly jumps when the budget goes to 75,000 on screen 3.

## Screens to capture (match the `screen` scenes in script.yaml)

### 1. `screens/apikit-deploy.jpg` — "Deploy, then deploy again" (**needs tenant**)
```bash
cd src
python3 -m apikit deploy
python3 -m apikit deploy
```
Expected first run: `+ column mgl_riskscore (whole number 0-100)`, `+ assembly MGLab.D365.Plugins (... bytes, sandbox,
database)`, two `+ plug-in type` lines, `+ custom API mgl_AssessProjectRequest (3 response properties)`, two `+ step`
lines with two `+ post-image` lines, `9 created, 0 updated, 0 unchanged`. Second run: `0 created, 0 updated, 9 unchanged`.
**Verify and note in README** (section "Not verified yet"):
- after the first run, open the solution: the assembly, both steps and the custom API should be in `MGLabDataverse`.
  If the assembly or steps are only in the Default Solution, add them with *Add existing* and note it;
- whether the second run really reports the assembly as unchanged (it compares `content`; if Dataverse doesn't return
  it, the assembly line will be `~ ... new content` every time — then reword the narration to "nothing else changes");
- the post-image registers with `messagepropertyname = Target` for the **Create** step (Learn lists Target for Create;
  if the platform rejects it, try `Id` and record which one worked).

### 2. `screens/apikit-call.jpg` — "Call it like any other message" (**needs tenant**)
```bash
python3 -m apikit call --code PR-0004
```
Expected (values depend on the lab data): `RiskScore NN  RiskLevel ...`, reason lines, `stored mgl_riskscore: (empty)`
or a number if the async step already ran for it. Then, off camera: `python3 -m apikit backfill` and
`python3 -m apikit backfill --apply` to score the 18 imported records (note the count in README).

### 3. `screens/form-riskscore.jpg` — "Change the budget, watch the score" (**needs tenant**)
Private browser window, signed in as **Alex Demo**. Project Requests app → PR-0004 → Budget 42,000 → 75,000, save.
Wait ~10–30 s, refresh: Risk Score updated. Capture the form with the new score visible (and, if possible, a second
frame before the refresh). Expected with the setup above: from a low value to 75 (30 budget + 25 no justification +
20 due soon) or 90 if the account has 2+ other open requests. Use the real number.

### 4. `screens/apikit-jobs-trace.jpg` — "System jobs and the trace log" (**needs tenant**)
```bash
python3 -m apikit jobs
python3 -m apikit trace --top 4
```
Expected: the Update step with one or more `Succeeded` jobs (auto-delete is off for the recording), then trace rows for
`RiskScoreRefreshPlugin` (async, depth 1, "Risk score 42 -> 75 (High)" style line) and `AssessProjectRequestApi`
(depth 2 when called from the async plug-in). **Note in README** the real depth values.
Optional B-roll: the same job in *Settings → System Jobs*.

### 5. `screens/apikit-workflows.jpg` — "What classic workflows do you still have?" (**needs tenant**)
```bash
python3 -m apikit workflows                               # DEV: the classic workflow from setup step 5
DATAVERSE_URL=https://<sales trial>.crm4.dynamics.com python3 -m apikit workflows --all --table account
```
Expected in DEV: `1 classic workflow(s)/action(s) (unmanaged only; --all for managed)` and
`mgl_projectrequest  Recalculate risk (classic)  Workflow (Background)  Off -> cloud flow, Dataverse trigger on update
(columns mgl_budget)`. In the Sales trial: whatever managed processes the app ships for Account — record them as they
are and adjust the narration ("the list is longer"). Mask both URLs.

## Masking checklist
- Environment URLs and org names (terminal, address bar), tenant name, user UPN and avatar.
- Only fictional data (episode 1 records, Contoso accounts) and lab users on screen. GUIDs are environment-specific:
  blur them if preferred.

## Tear-down
1. `plugins.json`: set `asyncautodelete` back to `true` and run `python3 -m apikit deploy` (if the episode stays), or
   `python3 -m apikit remove` if episode 6 is not going to be recorded next (episode 6 **needs** the custom API and the
   score column — keep them until it's done).
2. Plug-in trace logging back to *Off* (or *Exception*).
3. Delete the classic workflow *Recalculate risk (classic)* from the solution.
4. Remove Risk Score from the form only if the column is deleted; `remove` keeps the column (it holds data). To delete
   it: maker portal → Tables → Project Request → Columns → Risk Score → Delete.
5. Restore PR-0004's budget (42,000) if later episodes rely on episode 1's values.
