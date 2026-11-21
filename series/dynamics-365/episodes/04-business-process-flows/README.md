# DEVLADLOG Dynamics 365 #4 — Business Process Flows

A **Project Approval** business process flow on the Project Request table from [episode 1](../01-dataverse-deep-dive/),
designed in the BPF designer (no code), and **bpfkit**, a small Python tool for the parts a designer doesn't give you:

```
Submit ──(Budget ≥ 50,000?)── yes ──> Finance Review ──> Approve ──> Close
                  └────────── no  ─────────────────────>┘
```

- **stages**: find the definition (`workflow`, category 4), its instance table, the lookup to our record and the stages
- **status**: every BPF running on a record (`RetrieveProcessInstances`) and the record's real path with markers
  (`RetrieveActivePath`, which evaluates the branch against the record's current data)
- **next / back / finish / abandon**: the only moves Learn allows — one stage forward on the active path or back to the
  previous one, with `activestageid` and `traversedpath` updated together; Finished only at the last stage
- **backfill**: records with no instance of this BPF (for example the 18 imported in episode 1, before the BPF existed),
  listed, then created at the first stage with `--apply`
- **report**: where requests wait, straight from the BPF table (active stage, days in stage, stuck over a per-stage
  threshold; `--fail-on-stuck` exits 1 for a scheduled check)

The *Finance Review* stage uses the *Business Justification* column added in [episode 3](../03-dynamics-365-customization/).

| Path | What it is |
|---|---|
| [`bpf.json`](bpf.json) | BPF name, table, entity set, alternate key, first stage, stage order for the report, stuck thresholds |
| [`src/bpfkit/definition.py`](src/bpfkit/definition.py) | `workflows` (category 4, Activated) → `uniquename` = instance table → `EntitySetName`, ManyToOne lookup + navigation property → `processstages` |
| [`src/bpfkit/path.py`](src/bpfkit/path.py) | Pure stage-move rules: forward on the active path, back to the previous visited stage, traversed path, consistency checks, state names |
| [`src/bpfkit/instances.py`](src/bpfkit/instances.py) | Record by alternate key, instances, `RetrieveProcessInstances`, `RetrieveActivePath`, move / finish / abandon / reactivate, create |
| [`src/bpfkit/backfill.py`](src/bpfkit/backfill.py) | Records without an instance; first stage cross-checked against existing traversed paths; keeps going after a failure |
| [`src/bpfkit/report.py`](src/bpfkit/report.py) | Stage report from BPF table rows |
| [`src/bpfkit/webapi.py`](src/bpfkit/webapi.py), [`auth.py`](src/bpfkit/auth.py) | Web API client (429 + Retry-After, update-only PATCH) and MSAL token provider, as in episodes 1 and 3 |
| [`sample/project-approval-instances.json`](sample/project-approval-instances.json) | 18 fictional instances in Web API shape, for the offline report |
| [`tests/`](tests/) | 29 pytest tests; the Web API is a recording stub answering like the Learn examples |

## Run and test (no tenant)

```bash
cd series/dynamics-365/episodes/04-business-process-flows
python3 -m pip install --user -r requirements.txt
python3 -m pytest -q tests                                              # 29 passed
cd src
python3 -m bpfkit report --from-json ../sample/project-approval-instances.json --now 2027-01-15
```
```
Project Approval: 18 instances (1 aborted, 15 active, 2 finished)

stage            active  oldest    avg  stuck
Submit                4      9d    3.0  1 over 5 d
Finance Review        3     10d    6.0  2 over 3 d
Approve               6     13d    5.2  2 over 5 d
Close                 2      2d    1.5

  PR-0011    Submit           since 2027-01-06 (9 d)
  PR-0004    Finance Review   since 2027-01-05 (10 d)
  ...
```

## Against an environment (needs tenant)

The BPF must exist and be **activated** (see [demo.md](demo.md)); the identity needs read/write on the BPF table.
```bash
export DATAVERSE_URL=https://<org>.crm4.dynamics.com
cd src
python3 -m bpfkit stages
python3 -m bpfkit backfill                  # list records without an instance
python3 -m bpfkit backfill --apply          # create them at "Submit"
python3 -m bpfkit status --code PR-0004
python3 -m bpfkit next --code PR-0004 --dry-run
python3 -m bpfkit next --code PR-0004
python3 -m bpfkit report --fail-on-stuck
```

## What we learned / gotchas

- **Activation creates a table.** Instances live in `<prefix>_<uniquename>` (here `mgl_projectapproval`), with
  `activestageid`, `activestagestartedon`, `traversedpath`, `statecode`/`statuscode` and a lookup to the record.
  bpfkit reads the entity set and the lookup's navigation property from metadata; Learn says to look the navigation
  property up rather than assume it.
- **Don't trust the order of `processstages`.** Learn's own example returns S1, S3, S2. The path a record follows comes
  from `RetrieveActivePath`, evaluated against its data: with a budget under 50,000 it skips Finance Review.
- **Only one step at a time.** Move to the next stage of the active path or back to the previous one, and send
  `traversedpath` with `activestageid`. Creating an instance at a stage other than the first also needs a traversed
  path. *Finished* (`statecode 0`, `statuscode 2`) is only possible at the last stage; *Aborted* is 1/3.
- **If the data changes the branch, the active stage can fall off the active path** (a request in Finance Review whose
  budget is lowered). bpfkit refuses to move it rather than writing an inconsistent traversed path.
- **The BPF table has its own security.** It's organization-scoped and, when created, only System Administrator and
  System Customizer have access. Other roles (episode 2's *Project Requester*) need privileges on *Project Approval*
  or users see no process bar.
- **Records that existed before activation** weren't given an instance when they were created (the default BPF is
  applied on create). `backfill` lists and fixes them. For bulk imports you can also *skip* the BPF on create by
  setting `ProcessId` to an empty GUID (Learn; code-only, not available in the UI).
- **The legacy columns on the record** (`processid`, `stageid`, `traversedpath`) are deprecated: use the BPF table.
  Report on the BPF table too (Learn's recommended option); our `report` does exactly that.
- **Design rules:** a branch condition must use steps from the stage right before it; a rule combines conditions
  with AND or OR, not both; client API changes don't trigger branch evaluation. Limits: 30 stages per process,
  30 steps per stage, 5 tables per process, 10 activated BPFs per table by default.
- Since August 2022 BPFs are created and edited from a solution in Power Apps, not from Power Automate's own list.
  Creating them needs a Power Apps or Power Automate per-user licence or a Dynamics 365 plan with BPF use rights.
- **Not verified yet** (marked in demo.md): the exact field names `RetrieveProcessInstances` returns over the Web API
  (bpfkit reads `name` and `processstageid` defensively), the traversed path the platform writes after a backward
  move, and whether a stage move through the API enforces the stage's required steps.

## References
- [Work with business process flows using code](https://learn.microsoft.com/power-automate/developer/business-process-flows-code) (instance table, create/move/finish/abort, RetrieveProcessInstances, RetrieveActivePath, ProcessId override, security, limits)
- [RetrieveProcessInstances function](https://learn.microsoft.com/power-apps/developer/data-platform/webapi/reference/retrieveprocessinstances), [RetrieveActivePath function](https://learn.microsoft.com/power-apps/developer/data-platform/webapi/reference/retrieveactivepath)
- [Tutorial: Create a business process flow](https://learn.microsoft.com/power-automate/create-business-process-flow) (solution designer, licensing, security roles, order, activate)
- [Tutorial: Enhance business process flows with branching](https://learn.microsoft.com/power-automate/enhance-business-process-flows-branching)
- [Best practices in using business process flow columns](https://learn.microsoft.com/power-automate/best-practices-entity-attributes) (report on the BPF table)
- [Workflow table reference](https://learn.microsoft.com/power-apps/developer/data-platform/reference/entities/workflow) (category 4 = Business Process Flow, statecode 1 = Activated)
- [getActivePath (Client API)](https://learn.microsoft.com/power-apps/developer/model-driven-apps/clientapi/reference/formcontext-data-process/activepath/getactivepath)
- Blog: [Business Process Flows — Complete Guide](https://www.devladlog.com/articles/dynamics-365/2025-10-30-business-process-flows-complete-guide-2025/)
