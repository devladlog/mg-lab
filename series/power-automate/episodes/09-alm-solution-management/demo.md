# Demo shot list: DEVLADLOG Power Automate #9, ALM and solution management

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs | none (the Hyper-V lab is not used) |
| Power Platform | **`DEV`** (exists, Dataverse). A second environment **`TEST`**: Production or Sandbox type with a Dataverse database. Developer environments can no longer be created (LAB.md), so check **Power Platform admin center → Resources → Capacity** first. If there is no Dataverse capacity for a second environment, create **TEST as a Trial environment** (30 days, free) instead and say so in the video description |
| SharePoint | Site `IT Helpdesk` with list **IT Requests** (from episode 1: Title, Status choice New/Triaged/Done) used by DEV, and a second site **`IT Helpdesk Test`** with a copy of the list (*Save list as template*, or create the same columns) used by TEST. The two site URLs are what the environment variable `IT site URL` changes between |
| Lab users | `labadmin` (recording account): maker, importer, **owner of the connections in DEV and TEST**. `alex.demo` (Alex Demo): requester, creates the test items. `taylor.demo` (Taylor Demo): the **service desk mailbox** (CC on every acknowledgement) |
| Azure DevOps | Existing organization `devladlog` (LAB.md): **private project `mglab-alm`**, deleted in tear-down. Install the free **Power Platform Build Tools** extension from the Marketplace (needs permission to install extensions in the organization). Free Microsoft-hosted grant: 1 parallel job, 60 min per run. Cost 0 |
| Entra ID | One app registration + service principal created by `pac admin create-service-principal` for the pipeline's Power Platform service connections. Cost 0. Client secret expires; delete the app in tear-down |
| Licences | Standard connectors only (SharePoint, Office 365 Outlook): covered by the lab E5 licences. No premium trial needed. Cost 0 |
| Recording machine | The Windows lab laptop: browser (make.powerapps.com, Azure DevOps, SharePoint, Outlook on the web) with `pipeline/mask.js`; terminal with `pac` (Power Platform CLI), Python 3.10+, PowerShell 7, git |

Everything in `src/` and `tests/` runs locally (see README). **Needs tenant**: every item below that says so.

## Prerequisites check (before recording)

1. `pac --version` and `python -m pytest` in this folder (61 passed). `pwsh -NoProfile -Command "Get-Module -ListAvailable Pester"` shows Pester 5 or later.
2. Capacity for TEST (see above). Create `TEST` and note its URL (never shown on screen).
3. In **both** environments, as `labadmin`, create the two connections: *Power Apps → Connections → New connection* → SharePoint, Office 365 Outlook. Open each connection and copy its **connection ID from the URL** (Learn: *Pre-populate connection references and environment variables*, step 2). The 32-hex-digit value is what the settings file needs.
4. Terminal variables for TEST (typed off camera, never on screen):
   `IT_SITE_URL` (the IT Helpdesk Test site URL), `SERVICEDESK_MAILBOX` (taylor.demo's address), `CONN_SHAREPOINT`, `CONN_OFFICE365` (TEST connection IDs).
   For the PROD stage of the pipeline demo use the same TEST values in the `alm-prod` group (there is no third environment; the Prod stage only has to reach "waiting for approval").

## Setup (≈ 45 min) **needs tenant**

1. **Publisher and solution in DEV.** *Solutions → New solution*: display name `IT Request Notices`, unique name `ITRequestNotices`, publisher *contoso* with prefix `cts` (create it if missing).
2. **Get release 1.0.0.0 into DEV.** Preferred (it also tests our hand-written flow JSON in the real service):
   ```bash
   pac auth create --name dev --environment <DEV url>        # interactive sign-in as labadmin, off camera
   cd series/power-automate/episodes/09-alm-solution-management/src
   pac solution pack --zipfile ../out/ITRequestNotices_1_0_0_0.zip --folder releases/1.0.0.0 --packagetype Unmanaged
   pac solution import --path ../out/ITRequestNotices_1_0_0_0.zip --settings-file <dev settings, see below>
   ```
   For DEV create a settings file with `pac solution create-settings --solution-zip ../out/ITRequestNotices_1_0_0_0.zip --settings-file ../out/settings.dev.json` and fill in the DEV connection IDs, the DEV site URL, label `DEV`, mailbox and stale days `5`.
   **If the import rejects the flows** (the flow JSON uses placeholder conventions we could not read from Learn), build the two flows by hand in the solution, following `src/releases/1.0.0.0/Workflows/*.json` (action names must match), then export and **replace `src/releases/1.0.0.0` and `src/solution` with the real unpacked export**, re-run `python -m pytest`, and note the differences in the README.
3. **Flows must be on in DEV** (connections signed in as labadmin). Create one test item as Alex Demo and check that the acknowledgement arrives (Alex) and the CC reaches Taylor.
4. **Export both types and unpack as Both** (this is the step the episode explains; it also settles an open question, see README):
   ```bash
   pac solution export --name ITRequestNotices --path ../out/ITRequestNotices.zip --overwrite
   pac solution export --name ITRequestNotices --path ../out/ITRequestNotices_managed.zip --managed --overwrite
   pac solution unpack --zipfile ../out/ITRequestNotices.zip --folder ../out/unpacked --packagetype Both
   grep -o "<Managed>.</Managed>" ../out/unpacked/Other/Solution.xml     # record the value: README assumes 2
   python -m almkit check ../out/unpacked --templates deploy/settings.test.json deploy/settings.prod.json
   ```
   Also run `unpack` once with `--packagetype Unmanaged` into a second folder and try `pac solution pack ... --packagetype Managed` on it: this is the error shown in scene `both` (capture the terminal for that scene if the text differs from README).
5. **Bump to 1.1.0.0 in DEV** (later, during the recording): delete the flow *Weekly stale summary* and the variable *Stale after days* from the solution, set version `1.1.0.0`, export both types, unpack as Both over `src/solution`. `git diff` should show what `python -m almkit diff releases/1.0.0.0 solution` shows.
6. **TEST site and list.** Create `IT Helpdesk Test` with the same IT Requests list; add `alex.demo` as a member.
7. **Azure DevOps (for scene `pipelinerun`).** Create project `mglab-alm`, push this episode's `src/` (folders `pipelines`, `deploy`, `solution`, `almkit`, `scripts`) as the repo root. *Project settings → Service connections → New → Power Platform* (service principal and client secret, from `pac admin create-service-principal`; the app also needs to be an application user in DEV and TEST). Create variable groups `alm-test` and `alm-prod` with `IT_SITE_URL`, `SERVICEDESK_MAILBOX`, `CONN_SHAREPOINT`, `CONN_OFFICE365` (mark the connection IDs secret) and `testServiceConnection` / `prodServiceConnection` (the service connection names). Create environments `test` and `prod`; add an **Approvals** check on `prod`. Create pipelines from `pipelines/export-from-dev.yml` and `pipelines/release.yml`.
   **Open question we could not verify** (README): the pipeline imports as a service principal, but Learn says the connections in a connection reference must be owned by the importer or shared with it. Run the Test stage once and look at the flow's state: if it is **Off** with a connection error, record that, and show the laptop path (scene `deploy`, signed in as labadmin) as the working one. Do not film a claim that the pipeline turned the flow on unless it did.

## Recording flow and screens (match the `screen` scenes in `script.yaml`)

| Scene id | File | What must be on screen |
|---|---|---|
| `solution` | `screens/solution.jpg` | DEV, solution **IT Request Notices**, version 1.1.0.0, *All* view: 1 cloud flow, 4 environment variables, 2 connection references. Mask URL and account |
| `pipelinerun` | `screens/pipeline.jpg` | Azure DevOps run of `release.yml`: Build and Test green, Prod waiting for approval; the Test stage log open on *Render the deployment settings* and *Import Upgrade*. Mask organization, URLs, connection IDs |
| `deploy` | `screens/deploy.jpg` | Terminal: `python -m almkit check ...` (0 errors), `python -m almkit render-settings deploy/settings.test.json --solution solution --out ../out/settings.test.json`, then `./scripts/Deploy-Solution.ps1 -SolutionFolder solution -SettingsFile ../out/settings.test.json -EnvironmentUrl $env:TEST_URL -Mode Update` ending with `Imported ITRequestNotices (Update)`. **Do not `cat` the rendered file** (it has the connection IDs). Clear the screen before capturing so no variable values are visible |
| `testenv` | `screens/test.jpg` | TEST, solution shown as **managed**, flow *Acknowledge IT request* **On**, connection references with connections, environment variable *Environment label* current value `TEST`. Second capture: Alex Demo adds an item `Second monitor`; Outlook on the web shows `IT request #<n> received [TEST]` |
| `leftover` | `screens/upgrade.jpg` | Three captures in one scene. (1) After **release 1.0.0.0 was installed in TEST** and then **1.1.0.0 imported as Update**: both flows listed. (2) After importing a **later build 1.1.1.0 as Upgrade** (`pac solution version --strategy Solution --solutionPath src/solution`, export both, unpack Both, `-Mode Upgrade`): only *Acknowledge IT request* remains and *Stale after days* is gone |

Steps for TEST, in order:
1. First install of 1.0.0.0: unpack/pack from `releases/1.0.0.0`, render settings (the release 1.0 file needs one more entry, `cts_StaleDays`, add it to a copy), `Deploy-Solution.ps1 -Mode Update` (a first install has nothing to upgrade; whether `--stage-and-upgrade` works on a first install is **not verified**, don't use it there).
2. `python -m almkit diff releases/1.0.0.0 solution` on camera (scene `upgrade` code).
3. Import 1.1.0.0 as `-Mode Update`: capture (1) of scene `leftover`.
4. Bump the build number, import as `-Mode Upgrade`: capture (2). **Open question** (README): Learn says an upgrade deletes components the new version no longer has, and that an update leaves them; we have not seen the exact result for a flow that an update left behind. If the flow is still there after the upgrade, keep that on camera, fix the scene narration and README.

## What to check after recording (and fix the README if it differs)

- The value `<Managed>` in the Solution.xml that `pac solution unpack --packagetype Both` writes (we assumed 2, from the template comment *Unmanaged(0)/Managed(1)/Both(2)*; our `src/solution` has 2 and packs as managed locally).
- Whether the flows imported as **On** in TEST for the laptop path, and for the pipeline path.
- Whether `environmentvariablevalues` files appear in a DEV export when DEV has a current value set (rule A08 flags any extra file in the variable's folder; the real file name isn't documented on Learn). Remove the current value in DEV before exporting, as Learn describes, and confirm the unpacked folder has only the definition file.
- That the flow JSON and the connector ID of our files import cleanly (setup step 2).

## Masking

- Run `pipeline/mask.js` in the browser; `series_label: "POWER AUTOMATE"`.
- Hide: tenant name, environment URLs and IDs, SharePoint site URLs, mailbox domains, connection IDs, the Azure DevOps organization name, the app registration's IDs, user principal names. Terminal captures: only the commands shown in this file, nothing with `$env:` values printed.

## Tear-down

1. Delete the solution `ITRequestNotices` in TEST (managed: delete removes its components) and in DEV; delete the TEST environment (or let the trial expire).
2. Delete the Azure DevOps project `mglab-alm` and the service connections; delete the Entra app registration created by `pac admin create-service-principal`.
3. Delete the SharePoint site `IT Helpdesk Test`; delete the TEST connections; remove the variable values from the shell (`Remove-Item Env:IT_SITE_URL, ...`).
4. `pac auth clear` on the recording machine.
