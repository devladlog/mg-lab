# DEVLADLOG Dynamics 365 #5 — Custom Plugins & Workflows

Server-side logic for the **Project Request** table from [episode 1](../01-dataverse-deep-dive/), the 2026 way:

- a **custom API** `mgl_AssessProjectRequest` (an *Action* bound to `mgl_projectrequest`) with a C# plug-in as its main
  operation: a risk score 0–100, a level (Low / Medium / High) and the reasons, from budget, Business Justification
  ([episode 3](../03-dynamics-365-customization/)), due date and the account's other open requests
- an **asynchronous plug-in** (post-operation, Create + Update with filtering attributes, post-image) that calls that
  same custom API and keeps a new **Risk Score** column fresh: the job a classic background workflow used to do
- **apikit**, a Python tool that registers all of it with the Web API inside the solution (idempotent), calls the API,
  backfills old records, reads system jobs and the plug-in trace log, and lists the **classic workflows and actions**
  still in an environment with where each one should go

MG Lab main-series [episode 4](../../../../episodes/04-dataverse-plugin-csharp/) already covers a synchronous
pre-operation validation plug-in and its unit tests; this episode doesn't repeat that. The threshold of 50,000 is the
same one used by episode 3's business rule and episode 4's BPF branch.

| Classic process | Where it goes now | In this episode |
|---|---|---|
| Background workflow | Cloud flow, or an async plug-in for pure data logic | `RiskScoreRefreshPlugin` (async) |
| Real-time workflow | Synchronous plug-in, business rule or Power Fx | (MG Lab #4) |
| Custom process action | Custom API | `mgl_AssessProjectRequest` |
| Custom workflow activity | Custom API (flows can call actions; they can't run custom workflow activities) | same API, used by a flow in [episode 6](../06-integration-with-power-platform/) |

| Path | What it is |
|---|---|
| [`src/MGLab.D365.Plugins/ProjectRisk.cs`](src/MGLab.D365.Plugins/ProjectRisk.cs) | Pure rules: no Dataverse calls, clock passed in; `NearestDate` for the User-local date column (see gotchas) |
| [`src/MGLab.D365.Plugins/AssessProjectRequestApi.cs`](src/MGLab.D365.Plugins/AssessProjectRequestApi.cs) | Custom API main operation (stage 30): reads 4 columns, counts other open requests (capped), sets 3 output parameters |
| [`src/MGLab.D365.Plugins/RiskScoreRefreshPlugin.cs`](src/MGLab.D365.Plugins/RiskScoreRefreshPlugin.cs) | Async post-operation: calls the custom API, compares with the post-image, writes `mgl_riskscore` only when it changed |
| [`src/MGLab.D365.Plugins/PluginBase.cs`](src/MGLab.D365.Plugins/PluginBase.cs) | Services, tracing, unexpected errors → traced `InvalidPluginExecutionException`; shared column names |
| [`src/MGLab.D365.Plugins.Tests/`](src/MGLab.D365.Plugins.Tests/) | 28 xUnit + Moq tests; compile the plug-in sources against the .NET 8 Dataverse SDK, so they run on Linux |
| [`plugins.json`](plugins.json) | Single source of truth: solution, assembly, plug-in types, custom API, column, steps |
| [`src/apikit/registration.py`](src/apikit/registration.py) | Bodies for assembly, types, custom API (deep insert), steps, post-image, integer column + Learn's rules as checks |
| [`src/apikit/deploy.py`](src/apikit/deploy.py) | `deploy` (create or update, in order, in the solution; refuses immutable changes), `remove` |
| [`src/apikit/ops.py`](src/apikit/ops.py) | `call`, `backfill`, `jobs` (asyncoperation by step), `trace` (plugintracelog, `startswith(typename, ...)` as in Learn), `workflows` (classic inventory + hints) |
| [`src/apikit/webapi.py`](src/apikit/webapi.py), [`auth.py`](src/apikit/auth.py) | Web API client (429 + Retry-After, update-only PATCH) and MSAL token provider, as in episodes 1–4 |
| [`tests/`](tests/) | 31 pytest tests; the Web API is a recording stub, plus an in-memory registry so `deploy` can run twice |

## Run and test (no tenant)

```bash
cd series/dynamics-365/episodes/05-custom-plugins-workflows
dotnet test src/MGLab.D365.Plugins.Tests -m:1          # Passed: 28
dotnet build src/MGLab.D365.Plugins -c Release -m:1    # bin/Release/net462/MGLab.D365.Plugins.dll (unsigned without .snk)
python3 -m pip install --user -r requirements.txt
python3 -m pytest -q tests                             # 31 passed
cd src && python3 -m apikit check                      # plugins.json against Learn's rules, offline
```
```
custom API mgl_AssessProjectRequest: Action, bound to mgl_projectrequest, 3 response properties, private=False
step Create  PostOperation Asynchronous  post-image mgl_riskscore
step Update  PostOperation Asynchronous  filtering mgl_budget,mgl_duedate,mgl_justification,mgl_customeraccountid  post-image mgl_riskscore
OK
```

**Signing key:** Dataverse needs a strong-name signed assembly. `MGLab.D365.Plugins.snk` isn't committed; the build signs
only when it exists. Create your own (`sn -k MGLab.D365.Plugins.snk` on Windows, or Visual Studio → Properties → Signing)
in `src/MGLab.D365.Plugins/` before building the DLL you deploy.

## Against an environment (needs tenant)

Prerequisites: episodes 1 and 3 in `DEV` (table, data, Business Justification column), solution `MGLabDataverse`
(publisher prefix `mgl`), an identity with System Customizer or System Administrator.

```bash
export DATAVERSE_URL=https://<org>.crm4.dynamics.com      # + AZURE_* for an app user, or interactive sign-in
cd src
python3 -m apikit deploy            # column, assembly, 2 types, custom API, 2 async steps + post-images
python3 -m apikit deploy            # second run: "0 created, 0 updated, 9 unchanged"
python3 -m apikit call --code PR-0004
python3 -m apikit backfill          # records saved before the step existed (dry run)
python3 -m apikit backfill --apply
python3 -m apikit jobs              # system jobs of the async steps; --failed for failures only
python3 -m apikit trace             # needs plug-in trace logging (Exception or All)
python3 -m apikit workflows         # classic workflows/actions (unmanaged); --all includes managed ones
python3 -m apikit remove            # tear-down (keeps the mgl_riskscore column: it holds data)
```

## What we learned / gotchas

- **Some custom API choices are permanent.** Binding type, bound table, *Is Function*, *Allowed Custom Processing Step
  Type*, *Enabled for Workflow* and the unique names and types of parameters and properties can't be changed after
  they're saved (Learn: CustomAPI tables). `deploy` compares what's deployed with `plugins.json` and refuses with
  "delete the custom API and deploy again" instead of pretending a PATCH worked. A test covers it.
- **Action, not Function, if a flow will call it.** Learn: the Dataverse connector currently only performs actions.
  Our API changes nothing, which would suggest a function, but episode 6 calls it from Power Automate.
- **Don't make it private if your own plug-ins call it.** Learn recommends *Is Private* = true before shipping a managed
  solution, and also lists "private messages can't be used in plug-ins" as a known issue. `RiskScoreRefreshPlugin`
  calls the API through `IOrganizationService.Execute`, so `check` refuses `isprivate: true` for this config.
- **Workflow-enabled custom APIs can't use StringArray, Entity or EntityCollection.** We return the reasons as one
  `String` (joined with `; `), which keeps that door open and is easy to show in a flow or a Teams message.
- **A bound API needs the fully qualified name over the Web API**:
  `POST mgl_projectrequests(<id>)/Microsoft.Dynamics.CRM.mgl_AssessProjectRequest`. The `Target` parameter is
  created by the platform for Entity binding; don't define it yourself (`check` refuses it).
- **Async steps: post-operation only.** Learn: asynchronous plug-ins can only be registered for PostOperation. They run
  through the asynchronous service as system jobs (`asyncoperation`), filtered per step with
  `_owningextensionid_value eq <step id>`.
- **No loop, no useless updates.** The async step filters on budget, due date, justification and account; it writes
  only `mgl_riskscore`, which isn't one of them, so it can't trigger itself. And it writes only when the score changed
  (compared with a post-image), because a Dataverse flow trigger with *Select columns* runs when a listed column is in
  the update even if the value is the same (Learn) — that matters in episode 6.
- **Auto-delete hides successes.** Learn recommends *Delete AsyncOperation if StatusCode = Successful*; with it, only
  failed or unfinished jobs stay in System Jobs. The recording turns it off temporarily so the jobs screen has rows
  (demo.md) and turns it back on.
- **Trace log rows live 24 hours** and hold 10 KB of text per run (oldest lines dropped). Turn trace logging on for
  debugging only.
- **A date that moves (found while writing tests).** Episode 1 created `mgl_duedate` with `Format: DateOnly` and no
  `DateTimeBehavior`, which defaults to **User local**. A date a Lisbon user picks in summer is stored as 23:00 UTC the
  day before. Learn: "Avoid Date only format with User local behavior." The plug-in uses the nearest UTC midnight
  (right for users between UTC−12 and UTC+12, and harmless for real Date-only values); the proper fix is a one-time
  switch of the column to *Date only* behavior plus `ConvertDateAndTimeBehavior` for existing rows.
- **Assembly versions:** changing only build or revision is an in-place update; changing major or minor makes it a
  different assembly and existing steps keep pointing at the old one (Learn: assembly versioning). `deploy` refuses a
  major/minor change instead of uploading over it.
- **Classic workflows can't be created from code in Dataverse** (Learn: workflows must be created and updated with the
  workflow designer), but they can be *read*: `workflows` queries `category eq 0 or 3`, `type eq 1` and suggests a
  target for each.
- **Not verified yet** (marked in demo.md): whether `pluginassemblies` returns `content` for the unchanged-assembly check
  (if not, every deploy re-uploads, harmlessly), that `MSCRM.SolutionUniqueName` adds the assembly and steps to the
  solution (check the solution after the first deploy; otherwise *Add existing*), that the Create step's post-image
  accepts `messagepropertyname = Target` (Learn's table lists Target for Create), and that steps can be filtered by
  `_eventhandler_value` (the plug-in type lookup).

## References
- [Create and use custom APIs](https://learn.microsoft.com/power-apps/developer/data-platform/custom-api) (binding, function vs action, Dataverse connector only performs actions, private, workflow-enabled types, main-operation plug-in, known issues)
- [CustomAPI tables](https://learn.microsoft.com/power-apps/developer/data-platform/custom-api-tables) (type values, properties that can't change after creation)
- [Create a custom API with code](https://learn.microsoft.com/power-apps/developer/data-platform/create-custom-api-with-code) (deep insert body)
- [Compare custom process action and custom API](https://learn.microsoft.com/power-apps/developer/data-platform/custom-actions#compare-custom-process-action-and-custom-api)
- [Register a plug-in](https://learn.microsoft.com/power-apps/developer/data-platform/register-plug-in) (async = PostOperation only, entity images, assembly versioning)
- [Asynchronous service](https://learn.microsoft.com/power-apps/developer/data-platform/asynchronous-service) (system job states, auto-delete recommendation)
- [Register a webhook — query failed asynchronous jobs for a step](https://learn.microsoft.com/power-apps/developer/data-platform/register-web-hook#query-failed-asynchronous-jobs-for-a-given-step)
- [Tracing and logging](https://learn.microsoft.com/power-apps/developer/data-platform/logging-tracing) (24 hours, 10 KB)
- [SdkMessageProcessingStep](https://learn.microsoft.com/power-apps/developer/data-platform/reference/entities/sdkmessageprocessingstep), [SdkMessageProcessingStepImage](https://learn.microsoft.com/power-apps/developer/data-platform/reference/entities/sdkmessageprocessingstepimage), [PluginAssembly](https://learn.microsoft.com/power-apps/developer/data-platform/reference/entities/pluginassembly) table references
- [Replace classic Microsoft Dataverse workflows with flows](https://learn.microsoft.com/power-automate/replace-workflows-with-flows) (capability comparison, synchronous workflows and performance)
- [Microsoft Dataverse real-time workflows](https://learn.microsoft.com/power-apps/maker/data-platform/overview-realtime-workflows) (New > Automation > Process > Workflow)
- [Sample: Workflow operations](https://learn.microsoft.com/power-apps/developer/data-platform/org-service/samples/workflow-operations) (workflows must be created with the designer in Dataverse)
- [Process (Workflow) table](https://learn.microsoft.com/power-apps/developer/data-platform/reference/entities/workflow) (category, mode, type, trigger columns)
- [Behavior and format of the date and time column](https://learn.microsoft.com/power-apps/maker/data-platform/behavior-format-date-time-field) and [by using code](https://learn.microsoft.com/power-apps/developer/data-platform/behavior-format-date-time-attribute)
- [Trigger flows when a row is added, modified, or deleted](https://learn.microsoft.com/power-automate/dataverse/create-update-delete-trigger) (select columns fire even when the value is the same)
- Blog: [Custom Plugins & Workflows — Complete Guide](https://www.devladlog.com/articles/dynamics-365/2025-10-23-custom-plugins-workflows-complete-guide-2025/)
