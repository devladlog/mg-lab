# DEVLADLOG Power Automate #13: Business process flows that guide the work

A **Purchase request process** business process flow (BPF) on a Dataverse table, continuing the purchasing scenario of
episodes 2 to 4 (same personas, same 5,000 EUR threshold), plus everything around it that can be built and proven
without a tenant:

| Stage | Steps (columns) | Gate |
|---|---|---|
| Submit | Amount, Justification, Needed by | Amount and Justification required |
| Manager review | Amount (optional, see gotcha 1), Manager decision | Manager decision required |
| *Condition* | Amount ≥ 5,000 **and** Manager decision = Approved | Yes → Finance review, No → Order |
| Finance review | Finance decision, flow step *Request finance approval* | Finance decision required |
| Order | PO number | required |
| Close | Received (Choice: Yes / No, partial / No, missing) | required |

A BPF has no logic of its own. We add three things around it: a **flow step** (cloud flow that asks finance and
completes the process log), a **flow that copies the active stage to the request** (for views), and a **script that
moves instances from code** (Web API).

| Path | What it is |
|---|---|
| [`src/process/purchase-request-process.json`](src/process) | The *design* of the process as data (stages, steps, branch, flow step, global workflow). The designer stays the source of truth for the real definition; this file is what the checks run against |
| [`src/bpfkit/`](src/bpfkit) | `validate.py` (14 rules from Learn), `engine.py` (instance: stage gating, branching, next/previous, abort/finish), `webapi.py` (Web API payloads), CLI (`python -m bpfkit validate / walk / payload`) |
| [`src/scripts/Set-BpfStage.ps1`](src/scripts) | PowerShell: list stages/instances, **Next / Previous** (RetrieveActivePath + PATCH `activestageid` and `traversedpath`), **Abort / Reactivate / Finish**. Token from `$env:DATAVERSE_TOKEN`, `-WhatIf` supported. **Needs tenant** to run for real |
| [`src/solution/`](src/solution) | Unpacked solution `PurchaseBpf` (`pac solution unpack` layout): the flow step *Finance review step* and *Copy active stage to request*, 2 connection references |
| [`src/tools/build_flows.py`](src/tools) | Writes the two flow JSON files (so the shapes stay reviewable in Python) |
| [`src/flowkit/`](src/flowkit) | Lint + expression engine + dry-run simulator from episodes 1 to 12; this episode adds `Parse JSON` to the simulator |
| [`src/samples/`](src/samples) | Requests (1,800 / 12,500 EUR / incomplete), stage ids (zero GUIDs), the flow-step payload, mocks |
| [`tests/`](tests) | 36 pytest tests (one of them runs the 11 Pester tests of the script); [`script.yaml`](script.yaml) draft script (15 scenes) · [`demo.md`](demo.md) shot list |

## Run it

```bash
cd series/power-automate/episodes/13-business-process-flows
python -m pytest                      # 36 passed in ~37 s (includes pac solution pack and the Pester suite)
pwsh -NoProfile -Command "Invoke-Pester ./tests/Set-BpfStage.Tests.ps1"   # 11 passed (Pester 6.2, PowerShell 7.6)

cd src
python -m bpfkit validate process/purchase-request-process.json            # OK
python -m bpfkit walk process/purchase-request-process.json --record samples/request-large.json --steps next,next,next,next,finish
python -m bpfkit payload process/purchase-request-process.json --record samples/request-large.json \
    --stage-ids samples/stage-ids.json --steps next,next          # prints the PATCH bodies
python -m flowkit lint solution/Workflows/*.json
pac solution pack --zipfile ../out/PurchaseBpf.zip --folder solution --packagetype Unmanaged
```

Result on the build machine (2026-11-21): `36 passed`, Pester `Tests Passed: 11, Failed: 0`, `pac solution pack` OK.
Everything runs locally: no sign-in, no network. The PowerShell script is executed for real; only
`Invoke-RestMethod` is mocked.

## What we learned / gotchas

1. **A branching rule only sees the stage right before it.** Learn (branching tutorial): *"Branching rule must be based
   on the steps in the stage that immediately precedes it."* Amount is typed in *Submit*, but the condition sits after
   *Manager review*, so *Manager review* needs *Amount* as an (optional) step too. `BPF006` in `bpfkit validate`
   reproduces it. **To confirm in the designer** (demo.md step 4) before the episode says it's what the designer does.
2. **A required Two Options step only passes on Yes.** Learn: required steps bound to a Two Options column "must have
   Yes (true) as their value, otherwise they're considered empty"; use a Choice if No is valid too. That is why
   *Received* is a Choice. Implemented in `engine.is_empty`, warning `BPF008`.
3. **Learn contradicts itself on branch depth**: five levels in the branching tutorial, ten in the create tutorial.
   The validator warns above five (`BPF014`). We didn't test which one the designer enforces.
4. **A flow step stays "Processing" unless the flow completes the process log.** Learn (*Flow step considerations*):
   add *Update a row* on **Process Logs** with `FlowsWorkflowLogId`; the user also needs read access to *System Jobs*.
   Our flow writes `processsessions` (`statecode` 1, `statuscode` 4 *Completed*; 6 *Failed* on timeout) and has a
   handler for a timed-out approval, otherwise the step would hang for ever (`test_a_timed_out_approval_fails_the_step…`).
5. **`When a row is added, modified or deleted` can't filter on a lookup column.** `activestageid` is a lookup, so the
   *Select columns* filter would silently never fire. The copy-stage flow filters on `traversedpath` (text, changed on
   every stage move) and `statecode` instead (`test_copy_flow_does_not_filter_on_the_lookup_column`).
6. **From code you can only move one stage forward or back**, and `traversedpath` must be kept in step. Creating an
   instance on a stage other than the first also needs `traversedpath`. `SetProcess` can no longer switch processes.
   Finished is only possible at the last stage, Abort anywhere (`statecode` 1 / `statuscode` 3).
7. **A workflow on *Stage Exit* of the last stage never runs.** Use a global workflow *Process Completed / Abandoned*
   (`BPF011`; our design has one).
8. **Plumbing**: the BPF table is created when you activate the process and, by default, only System Administrator and
   System Customizer can use it (grant roles); the BPF table must be added to the solution manually before export; since
   August 2022 BPFs can only be created from a solution in Power Apps, not from Power Automate outside solution explorer.

### What was not verified here

- **The BPF definition itself.** A BPF is stored as designer-generated process data (stages in `processstage`, the
  definition in `workflow`); we did not hand-author that. The recording session builds it in the designer following
  `process/purchase-request-process.json` and, if possible, exports it into `src/solution/` (then add a test).
- Designer conventions we could not confirm on Learn: the trigger `operationId` `SubscribeOnDemand` of *When a row is
  selected* (`subscriptionRequest/*` keys), `subscriptionRequest/message: 3` for *Update* and `scope: 4` for
  *Organization*, and the option values `444460000/1` (publisher prefix 44446 from `Solution.xml`).
- Learn's example reads the row with *Get a row by ID* on the **process table** using `BPFFlowStageTableRowID`; that id
  is the row of the stage's table, so our flow reads `cts_purchaserequests`. Confirm in the lab.
- Learn's UI text says *Status Value* **Succeeded** for the Process Logs row; the `processsession` table reference
  lists *Completed* (4). We use the documented column values; confirm what the flow step turns green on.
- The navigation property `bpf_purchaserequestid` and the entity set `cts_purchaserequestprocesses` follow Learn's naming
  pattern; read the real ones from `$metadata` / `EntityDefinitions?$filter=IsBPFEntity eq true` (demo.md step 5).
- `Set-BpfStage.ps1` was tested on PowerShell 7.6 only (written without 7-only syntax, not run on Windows PowerShell 5.1).

## References

- [Business process flows overview (limits, stage gating, Two Options, flows)](https://learn.microsoft.com/power-automate/business-process-flows-overview)
- [Tutorial: Create a business process flow](https://learn.microsoft.com/power-automate/create-business-process-flow)
- [Tutorial: Enhance business process flows with branching](https://learn.microsoft.com/power-automate/enhance-business-process-flows-branching)
- [Work with business process flows using code (BPF table, traversedpath, state, RetrieveActivePath)](https://learn.microsoft.com/power-automate/developer/business-process-flows-code)
- [RetrieveActivePath function](https://learn.microsoft.com/power-apps/developer/data-platform/webapi/reference/retrieveactivepath)
- [Create instant flows in business process flows (flow step, payload schema, process log)](https://learn.microsoft.com/power-automate/create-instant-flows)
- [Best practices in using business process flow columns (copy the active stage)](https://learn.microsoft.com/power-automate/best-practices-entity-attributes)
- [Trigger flows when a row is added, modified, or deleted (lookup columns in Select columns)](https://learn.microsoft.com/power-automate/dataverse/create-update-delete-trigger)
- [Trigger flows for selected rows](https://learn.microsoft.com/power-automate/dataverse/row-selected)
- [Process Session table reference](https://learn.microsoft.com/power-apps/developer/data-platform/reference/entities/processsession)
- Blog Complete Guide: <https://www.devladlog.com/articles/power-automate/2026-04-01-business-process-flows-complete-guide-2026/>
