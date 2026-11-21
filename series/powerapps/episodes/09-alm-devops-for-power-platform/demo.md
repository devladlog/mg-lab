# Demo shot list — DEVLADLOG Power Apps #9, ALM and DevOps for Power Platform

The scripts, the settings templates, the pipeline YAML and the linter were tested locally (`python3 -m pytest -q` in `tests/`: 84 passed; real `pac` 2.16.1,
offline). Everything below **needs the lab tenant** and has not been run there: the service connections, both pipelines, the solution checker, the import and upgrade,
the approval, the connections. The solution source in `src/solution/EquipmentDesk` is a hand-written skeleton in the layout `pac solution unpack` writes
(one environment variable, two connection references); step 3 replaces it with the real unpack of the lab solution.

## Lab environment
No VM. Everything is recorded on the **lab Windows host** (the recording laptop): browser on the lab tenant (Power Apps, Power Platform admin center, Azure DevOps)
and a terminal. Credentials are never written in any file; the recorder signs in as `labadmin`.

| What | Notes | Cost |
|---|---|---|
| Lab **DEV** environment with episodes 1-8: solution **Equipment Desk** (tables, model-driven app, canvas app, flow **SendLoanReminder** from episode 6 with its two connection references `contoso_EquipmentDeskDataverse` / `contoso_EquipmentDeskOutlook`) | the solution must have publisher `contoso` (prefix `contoso`), unique name `EquipmentDesk` | existing |
| **TEST** and **PROD** environments: two new Dataverse environments named for the recording (e.g. `MG Lab TEST`, `MG Lab PROD`, region Europe, **no** Dynamics 365 apps, security group none) | Learn (About trial environments, Create environments): a Trial (standard) environment lasts 30 days, one per user, no copy/backup/reset, and doesn't consume paid capacity; Trial (subscription-based) is created by tenant admins and an offer-based trial entitles the tenant to three. A Power Apps trial allows one standard trial. If only one can be made, make TEST a trial and PROD a trial (subscription-based) from the D365 Sales trial, or record both from subscription-based trials. Create them the day of the recording, delete after | 0 (trials; no paid capacity) |
| Recording user `labadmin`: Power Platform admin / System Administrator in the three environments, Power Apps Premium trial, Exchange Online mailbox | creates the environments, the connections and the service principals | existing |
| **Service principals**: one Entra app registration + client secret per environment (DEV, TEST, PROD), made with `pac admin create-service-principal --environment <id>` | the command registers the app, adds it as System Administrator application user and prints tenant id, application id, secret (shown once, **off camera**). Learn recommends a service connection with workload identity federation; the secret route is the documented fallback and the quicker one for a recording. Delete the apps in tear-down | 0 |
| **Azure DevOps** organization of the lab (see `series/LAB.md`): extension **Power Platform Build Tools** (Marketplace, free; the org owner installs it), a **new private project** (name masked on screen), one Azure Repos Git repository, 2 YAML pipelines, 2 variable groups, 2 environments, 3 service connections | Microsoft-hosted agents `ubuntu-latest`; the free grant (1 parallel job, 1,800 min/month, see `series/LAB.md`) is active. Budget about 3 runs of 10-15 minutes. Delete the project in tear-down | 0 (inside the free grant) |
| Connections in TEST and PROD: one **Microsoft Dataverse** and one **Office 365 Outlook** connection each, created by `labadmin` in that environment and **shared with the service principal's application user** (Can use) | Learn: OAuth connections can only be explicitly shared with a user representing a service principal. Their ids come from the connection URL (Data > Connections > the connection) | 0 |
| On the laptop: `pac` (Power Platform CLI), `git`, optionally VS Code | for the SPN command, the `git clone`/push of `src`, and the local test run | free |

Pipeline files assume the **repo root is the contents of this episode's `src` folder** (`solution/`, `settings/`, `scripts/`, `pipelines/` at the top).

## Things to confirm in the lab (fix code/tests/README if they differ)
1. The real unpack of the DEV solution passes `Test-SolutionSource.ps1` (S01-S11). Whatever fires: is the rule wrong or the export? In particular: the name of the
   file with current environment variable values (S08 looks for `*environmentvariablevalue*`), whether connection references carry anything but the documented
   fields (S10), and whether `Solution.xml` says `Managed` 2 after `Unpack as Both` (it did with pac 2.16.1).
2. The Build Tools **Export Solution** task creates the `export/` folder under `$(Agent.TempDirectory)` by itself, and `Unpack Solution` with `SolutionType: Both`
   finds `EquipmentDesk_managed.zip` next to `EquipmentDesk.zip`.
3. **Power Platform Checker** runs from `ubuntu-latest` with the `mglab-dev` connection, accepts the `*_managed.zip` wildcard, and `ErrorLevel: HighIssueCount`.
4. **Import** with `HoldingSolution: True` (the template passes the pipeline parameter) works on an environment that already has the solution; what it does on a first
   install (not verified: for the first run set the parameter `upgradeExisting` to **false**).
5. The deployment settings file works with the token-filled file: environment variable value applied, both connection references bound, flow turned on after import.
6. The approval check on environment `equipmentdesk-prod` holds the Prod stage; the build validation policy on `main` runs a PR build whose Test/Prod stages are skipped.
7. The run name format gives `Build.BuildNumber` like `20261121.1` and `Set-SolutionVersion` produces `1.0.20261121.1`.
8. The flow, when it was created by `FlowDeploy` (episode 6) from `clientdata`, can be edited in the designer to use the environment variable (Dynamic content). Copy the
   solution unpack back into `src/solution` (step 3) so the repo shows what the lab really has.

## Steps
1. **Environments and identities (off camera).** Admin center: create TEST and PROD (above). Terminal: `pac auth create` (labadmin, interactive), then
   `pac admin create-service-principal --environment <DEV id>` and the same for TEST and PROD; note the three application ids and secrets in a password manager.
2. **Connections (off camera).** In TEST and PROD, as `labadmin`: Data > Connections > New: Dataverse and Office 365 Outlook. Share each with the service principal
   user (Share > enter the application name > Can use). Note the four connection ids.
3. **Environment variable and flow in DEV.** Solution **Equipment Desk** > New > More > Environment variable: display name **Reminder domain**, name `contoso_ReminderDomain`,
   Text, default `contoso.com`. Open **SendLoanReminder**, replace the hard-coded domain in the `Problem` expression (episode 6) with the variable from Dynamic content, save. Set the
   variable's **Current value** to the lab mail domain **off camera** to test the flow, then **Current value > ... > Remove from this solution** so it isn't exported (capture
   `solution-screen`). Check the two connection references are in the solution.
4. **Azure DevOps (partly off camera).** Install the Build Tools extension (org owner). Create a private project, a repo; clone it; copy the contents of `src` into the repo root; push `main`.
   Project settings > Service connections > New > **Power Platform** (service principal / client secret): `mglab-dev`, `mglab-test`, `mglab-prod` with each environment URL and the three
   secrets. Pipelines > Library > variable groups `equipmentdesk-test` (`TEST_CONNECTION_DATAVERSE`, `TEST_CONNECTION_OUTLOOK`) and `equipmentdesk-prod` (`PROD_CONNECTION_DATAVERSE`,
   `PROD_CONNECTION_OUTLOOK`), values from step 2. Pipelines > Environments > `equipmentdesk-test`, `equipmentdesk-prod` (on PROD: Approvals and checks > Approvals > `labadmin`).
   Project settings > Repositories > Security: allow **Create branch**, **Contribute**, **Read** for `<project> Build Service (<organization>)` (Learn: not the Project Collection Build
   Service Accounts). Create two pipelines from the existing YAML: `export-solution-to-git` (`pipelines/export-solution-to-git.yml`) and `build-and-release` (`pipelines/build-and-release.yml`).
   Allow the pipelines to use the service connections and environments when asked.
5. **Export (on camera).** Run `export-solution-to-git`. Show the steps and the mirror/lint output. Repos > Branches > `export/<run>` > Create a pull request: the diff of the real unpack against the skeleton
   (capture `export-screen`). Complete the PR into `main` (first time: the whole real source replaces the skeleton; if the lint fails, see "Things to confirm", fix, re-run).
6. **Build validation policy.** Repos > Branches > `main` > Branch policies > Build validation > `build-and-release`. (Not needed for the first run; shows the PR behaviour.)
7. **First install.** Run `build-and-release` manually with **Upgrade an already installed solution** = off. Build runs; Test deploys; the Prod stage waits for approval: approve with "TEST checked"
   (capture `release-screen`). Terminal on the laptop, optional capture: `python3 -m pytest -q` in `tests/` (84 passed).
8. **Second release, upgrade.** In DEV make a visible change (e.g. add a description to the environment variable), run the export pipeline, merge the PR, let `build-and-release` run with the
   parameter on (default). Show Test then approve Prod. Optional: remove a component in DEV, export again, and show it disappears in TEST after the upgrade.
9. **PROD proof.** Power Apps, PROD: Solutions > Equipment Desk is **Managed**, version `1.0.<build>.<rev>`, **Reminder domain** current value `contoso.com`; TEST: `test.contoso.com`; the flow is On
   (capture `prod-screen`). Optionally run the flow from the app against a test loan.

## Screens to capture (match `screen` scenes in script.yaml)
| Scene | File | What must be on screen |
|---|---|---|
| `solution-screen` | `screens/solution-dev.jpg` | DEV solution Equipment Desk: environment variable, two connection references, SendLoanReminder; variable default `contoso.com`, current value empty; flow `Problem` expression using the variable |
| `export-screen` | `screens/export-run.jpg` | Export pipeline run steps with the mirror/lint output; branch `export/<run>`; pull request diff |
| `release-screen` | `screens/release-run.jpg` | `build-and-release` run: Build green, Test green, Prod waiting for approval then green; Checker log; artifact `drop` with both zips |
| `prod-screen` | `screens/prod-managed.jpg` | PROD: solution Managed with the run's version; env var value `contoso.com` vs TEST `test.contoso.com`; flow On |

## Masking
- Environment names and URLs, tenant name, Azure DevOps organization and project names, user names and avatars, connection names and ids, service principal names, application ids, secrets (never on screen).
- Use `pipeline/mask.js` in the browser; `series_label: "POWER APPS"` is set in `script.yaml`. The lab mail domain never appears: the variable values on screen are `contoso.com` / `test.contoso.com`.

## Tear-down
1. Azure DevOps: delete the project (repo, pipelines, variable groups, environments, service connections go with it). Uninstall the extension only if the owner wants it gone.
2. Entra ID: delete the three app registrations (their secrets die with them) and the application users in the environments (admin center, Users).
3. Admin center: delete the TEST and PROD environments (and any 30-day trial that wasn't used). Their connections go with them.
4. DEV: keep the solution; the environment variable and the flow change stay (the flow now reads the variable). If episode 6's `FlowDeploy` is re-run it puts the hard-coded domain back, so don't.
5. Delete the local `pac` auth profiles (`pac auth clear`) and the password-manager entries.
