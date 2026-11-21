# DEVLADLOG Power Automate #9: From DEV to TEST without touching the flow

The **IT Request Notices** solution, two releases of it, and the local material that proves it can move from DEV to
TEST (and on to production) **with its own values, its own connections and the right import mode**, before it
touches a second environment.

Episode 1's flows have the site address typed into the trigger. That works in DEV and nowhere else. Here the same
kind of flow lives in a solution and is built to be deployed:

- **Flow `Acknowledge IT request`**: SharePoint *When an item is created* on IT Requests (trigger condition: not
  `[test]...`), then an Outlook email to the requester with the service desk in CC. Site, list and mailbox are
  **environment variables**; the subject ends with `[<environment label>]`, so a TEST email says TEST. Both
  connectors go through **connection references**.
- **Release 1.0.0.0** (`src/releases/1.0.0.0`) also has `Weekly stale summary` and the variable `cts_StaleDays`.
  **Release 1.1.0.0** (`src/solution`) removes both: episode 1's daily digest already covers it. That removal is what
  makes **Update vs Upgrade** matter.
- **`almkit`**: a checker for the unpacked solution, the deployment settings files and the version, and a diff that
  says whether the release needs an *Upgrade*.
- **Deployment settings** per environment (`src/deploy/settings.test.json`, `settings.prod.json`) with `${TOKENS}`
  for what only the target knows; `almkit render-settings` fills them from the pipeline's variables and stops when
  one is missing.
- **Two Azure DevOps pipelines** with the Power Platform Build Tools v2 tasks (`export-from-dev.yml`,
  `release.yml` + `deploy-steps.yml`) and **`Deploy-Solution.ps1`**, the same steps for a laptop.

| Path | What it is |
|---|---|
| [`src/solution/`](src/solution) | Release **1.1.0.0**, unpacked (`pac solution unpack` layout): 1 flow, 4 environment variables, 2 connection references. `<Managed>2</Managed>` (see gotcha 1) |
| [`src/releases/1.0.0.0/`](src/releases/1.0.0.0) | Release 1.0.0.0: 2 flows, 5 environment variables, same connection references |
| [`src/tools/build_solution.py`](src/tools/build_solution.py) | Writes both folders, so JSON, XML, variables and references stay consistent |
| [`src/almkit/`](src/almkit) | `model.py` reads a solution folder; `checks.py` has the rules A01-A09 (solution), S01-S06 (settings), V01-V02 (version); `settings.py` renders `${TOKENS}`; `diff.py` plans Update or Upgrade. `python -m almkit check / diff / render-settings` |
| [`src/deploy/`](src/deploy) | `settings.test.json`, `settings.prod.json` (templates) |
| [`src/pipelines/`](src/pipelines) | `export-from-dev.yml` (set version, export unmanaged and managed, unpack Both, check, commit), `release.yml` (check, pack managed once, deploy to test then prod) and `deploy-steps.yml` (render settings, import, apply upgrade) |
| [`src/scripts/Deploy-Solution.ps1`](src/scripts/Deploy-Solution.ps1) | Packs managed and runs `pac solution import` with the settings file; `-Mode Update` or `Upgrade` |
| [`src/flowkit/`](src/flowkit) | Lint + dry-run harness from episodes 1-8 (the flows are linted and run with mocks) |
| [`tests/`](tests) | 61 pytest tests (+ 8 Pester tests run by one of them): solution and flows (7), checks (14), settings (16), diff and versions (8), pipelines (8), `pac` (6), PowerShell (2) |
| [`script.yaml`](script.yaml) | Draft video script (16 scenes) · [`demo.md`](demo.md) shot list for the lab tenant |

## Run it

Needs Python 3.10+ with `pytest` and `pyyaml`. `pac` and `pwsh` (with Pester 5+) are optional: their tests are skipped
when they are missing.

```bash
cd series/power-automate/episodes/09-alm-solution-management
python -m pytest                      # 61 passed in ~58 s (pac 2.16.1, pwsh 7.6, Pester 6.2)

cd src
python -m flowkit lint solution/Workflows/*.json                            # OK
python -m almkit check solution --previous releases/1.0.0.0 \
       --templates deploy/settings.test.json deploy/settings.prod.json      # 0 error(s), 0 warning(s)
python -m almkit diff releases/1.0.0.0 solution                             # flow removed ... import mode: UPGRADE
IT_SITE_URL=... SERVICEDESK_MAILBOX=... CONN_SHAREPOINT=... CONN_OFFICE365=... \
  python -m almkit render-settings deploy/settings.test.json --solution solution --out /tmp/settings.json
pac solution pack --zipfile ../out/ITRequestNotices_managed.zip --folder solution --packagetype Managed
python tools/build_solution.py        # rewrites solution/ and releases/ (idempotent)
```

`almkit check` on a copy with a site URL typed into the trigger, a connection bound directly and the folder unpacked
as unmanaged only:

```
ERROR   A02 Solution.xml: <Managed>0</Managed>: `pac solution pack --packagetype Managed` fails on this folder ...
ERROR   A05 ...json connectionReferences.shared_office365: binds a connection directly instead of a connection reference ...
ERROR   A06 ...json: a SharePoint URL typed into the flow ('https://contoso.sharepoint.com/sites/ITHelpdesk'): put it in an environment variable
3 error(s), 1 warning(s)
```

## How the material was made, and what still needs the tenant

The solution files follow the layout `pac solution unpack` writes (same as episodes 1-8), and the rules were written
from Learn (links below). `pac solution pack`, `create-settings` and `version` run for real in the tests; the
pipelines are checked against the task and input names on Learn, not run; the PowerShell script runs against a
stand-in `pac` that records its arguments (the stand-in exists only for the Pester tests; **the demo uses the real
`pac` and the real environments**).

**Needs tenant:** importing the solution (`pac solution import`), the settings with real connection IDs, the flows
turning on, the Azure DevOps runs (extension, service connection, variable groups, approvals), and every `screen`
scene. See [`demo.md`](demo.md).

## What we learned / gotchas

1. **A folder unpacked as unmanaged only can't be packed as managed.** We hit it: with `<Managed>0</Managed>`,
   `pac solution pack --packagetype Managed` stops with *Solution package type did not match requested type*
   (`tests/test_pac.py::test_managed_pack_fails_...`). Learn (SolutionPackager): the tool can't convert unmanaged to
   managed; you export the solution twice (`Name.zip`, `Name_managed.zip`) and unpack with `--packagetype Both`,
   then pack either type from that one folder. Our `src/solution` has `<Managed>2</Managed>` (the value the template
   comment calls *Both*) and packs as managed (`test_pack_unmanaged_and_managed`). Rule A02 checks it. The pipeline
   exports twice and unpacks with `SolutionType: Both` (Build Tools: *Unmanaged* is the recommended unpack type and
   *Managed* the recommended pack type; Learn doesn't explain how to get both from one unpack).
2. **Environment variables: definition in the solution, value in the environment.** Learn FAQ: "Should I include the
   value in my solution? No." Definitions are managed components, the values are unmanaged records. Our default values
   are placeholders (`contoso`); with only a default and no value, the import doesn't ask for anything
   (Learn troubleshooting), so a forgotten entry in the settings file silently runs with the default. Rules A06
   (nothing typed into the flow), A08 (no value files in the solution) and S02 (every variable has an entry) cover it.
3. **The settings file must match the solution, release after release.** `pac solution create-settings` writes every
   variable and connection reference with **empty** values (`Value`, `ConnectionId`) and extra metadata; the Learn
   example uses only `SchemaName`/`Value` and `LogicalName`/`ConnectionId`/`ConnectorId`. A file from 1.0.0.0 names
   `cts_StaleDays`, which 1.1.0.0 doesn't have (`test_settings_from_the_previous_release_...`); 1.1.0.0's file lacks
   it for 1.0.0.0. Learn says to get connection IDs from the connection's URL in the target environment. We don't know
   what the import does with an entry for a variable the solution doesn't have, so S02 reports it as an error.
4. **Update can't delete; Upgrade does.** Learn (update/upgrade, solution concepts): an **update** replaces the
   solution but "components that aren't in the newer solution won't be deleted"; an **upgrade** deletes components
   of the previous version that aren't in the new one; *stage for upgrade* (`--stage-and-upgrade`, or Build Tools
   `HoldingSolution` + *Apply Solution Upgrade*) defers the deletion. Release 1.1.0.0 removes a flow and a variable:
   `almkit diff` says UPGRADE (`test_release_1_1_removes_...`). A new version also has to be **higher** than the
   installed one (`test_version_must_go_up`, compared as numbers: 1.10 > 1.2).
5. **Flows after import.** Learn: the import tries to restore each flow to the state it had when exported; if it was
   on and every connection reference gets a connection, it is turned on. An update of an existing flow doesn't change its
   state. Importing turns flows off and on again, so small solutions limit the interruption.
6. **Connections have owners.** Learn: on import, connections in connection references must be owned by the owner of
   the reference or shared with them; a user who lacks permission to a connection can't turn the flow on
   (`ConnectionAuthorizationFailed`). In a pipeline the importer is the service principal. **We did not test whether
   a service principal can use user-owned SharePoint and Outlook connections**; demo.md plans the laptop path as the
   working one and records what the pipeline does.
7. **Build Tools: don't mix versions, and import has a 4-minute trap.** Learn: you can't mix task versions in a
   pipeline (a test enforces `@2` everywhere); the import task "will automatically timeout after 4 minutes" unless
   `AsyncOperation` is true, so both import and export use it (with `MaxAsyncWaitTime`).
8. **`pac solution version --strategy Solution`** raises the **build** number (1.1.0.0 becomes 1.1.1.0 in
   `test_pac_solution_version_...`); the revision stays as it was. Build Tools has *Set Solution Version* for DEV.
9. **Settings with secrets.** `${TOKENS}` keep connection IDs and tenant URLs out of Git; `render` JSON-escapes values
   (`test_a_value_with_a_quote_or_backslash...`) and the script refuses to import a file that still has a token.
   Connection IDs are not secrets in themselves; mark them secret in the variable group anyway.

### What was not verified here

- That the flow JSON and the connector IDs we wrote (`OpenApiConnection`, `shared_sharepointonline`,
  parameter names like `emailMessage/To`) import into the real service. Demo setup step 2 imports release 1.0.0.0 into
  DEV; if it fails, the real export replaces our files.
- What `pac solution unpack --packagetype Both` writes in `Solution.xml` (we assume `2`, as the template comment
  suggests) and the real file name of a current value in an unpacked variable folder (A08 flags any extra file).
- Whether `--stage-and-upgrade` works for a **first** install (we don't use it there), and what exactly happens to a
  flow that an *update* left behind when a later *upgrade* arrives (Learn says upgrade removes it; the demo shows it).
- That a service principal can import with user-owned SharePoint and Outlook connections and get the flows turned on
  (gotcha 6).
- The Azure Pipelines YAML: only its shape and the Learn task inputs are checked (`${{ if }}` blocks, deployment jobs,
  `persistCredentials` and the commit step need a real run; the build service needs *Contribute* on the repo).
- Power Platform pipelines (the in-product feature) are not covered in this episode.

## References

- [Pre-populate connection references and environment variables for automated deployments (deployment settings file, `create-settings`, connection ID from the URL)](https://learn.microsoft.com/power-platform/alm/conn-ref-env-variables-build-tools)
- [Microsoft Power Platform Build Tools tasks (Export, Unpack, Pack, Import, Apply Solution Upgrade, Set Solution Version, Checker; parameters, 4-minute timeout)](https://learn.microsoft.com/power-platform/alm/devops-build-tool-tasks)
- [Microsoft Power Platform Build Tools for Azure DevOps (v2 is CLI-based, no mixing of versions, service connections, `pac admin create-service-principal`)](https://learn.microsoft.com/power-platform/alm/devops-build-tools)
- [Environment variables overview and FAQ (values are unmanaged, "Should I include the value in my solution?")](https://learn.microsoft.com/power-apps/maker/data-platform/environmentvariables) · [Environment variables FAQ](https://learn.microsoft.com/power-apps/maker/data-platform/environment-variables-faq) · [Data source references based on environment variables aren't updated during solution import (default vs current value)](https://learn.microsoft.com/troubleshoot/power-platform/dataverse/working-with-solutions/dataverse-environment-variables)
- [Use a connection reference in a solution (turned on after import, ConnectionAuthorizationFailed, sharing connections)](https://learn.microsoft.com/power-apps/maker/data-platform/create-connection-reference)
- [Import a solution with cloud flows (flow state after import)](https://learn.microsoft.com/power-automate/import-flow-solution) · [Import solutions (Enable plug-in steps and flows)](https://learn.microsoft.com/power-apps/maker/data-platform/import-update-export-solutions)
- [Upgrade or update a solution (Upgrade, Stage for upgrade, Update; version numbers)](https://learn.microsoft.com/power-apps/maker/data-platform/update-solutions) · [Solution concepts (lifecycle: update, upgrade, patch)](https://learn.microsoft.com/power-platform/alm/solution-concepts-alm#solution-lifecycle)
- [SolutionPackager tool (managed and unmanaged, `Both`, `_managed.zip` naming)](https://learn.microsoft.com/power-platform/alm/solution-packager-tool) · [pac solution (pack, unpack, import, export, create-settings, version)](https://learn.microsoft.com/power-platform/developer/cli/reference/solution) · [pac auth (applicationId, clientSecret, tenant, environment)](https://learn.microsoft.com/power-platform/developer/cli/reference/auth)
- [Export a solution (cloud flows)](https://learn.microsoft.com/power-automate/export-flow-solution)
- Blog: [ALM & Solution Management: Complete Guide](https://www.devladlog.com/articles/power-automate/2025-07-09-alm-solution-management-complete-guide-2025/)
