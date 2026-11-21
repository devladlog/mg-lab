# Demo shot list — DEVLADLOG Dynamics 365 #4: Business Process Flows

## Lab environment

No VMs and no Azure resources: cloud tenant only, recorded from the browser and a terminal on the recording laptop.

| Item | Notes | Cost |
|---|---|---|
| Power Platform environment `DEV` (Dataverse, exists) | Custom table only, no Dynamics 365 app needed | none |
| Licence with BPF use rights | Learn: Power Apps or Power Automate per-user licence, or a Dynamics 365 plan with BPF rights. The lab's **Power Apps Premium** covers the maker and the test users | none (trial) |
| Episodes 1 and 3 done in `DEV` | `mgl_projectrequest` with 18 records (episode 1) and the **Business Justification** column (episode 3, keep it). Episode 3's business rule can stay | none |
| Episode 2's lab users (Alex Demo, Sam Demo) and *Project Requester* role (optional) | For the security check; otherwise skip that part | none |
| A model-driven app with Project Request | Same app as episodes 2–3 | none |
| Identity | `labadmin` (the recording account) with System Customizer (to design/activate) — the tool itself only needs read/write on the BPF table and read on metadata | none |
| Python 3.10+ with `pip install --user -r requirements.txt`; browser with `pipeline/mask.js` | Recording laptop | none |

Already run in the build container: `python3 -m pytest -q tests` (29 tests, Web API stubbed with responses shaped
like the Learn examples) and the offline `report --from-json` on the fictional sample. **Nothing has run against
Dataverse yet: all four `screen` scenes need the lab tenant**, and the `path` code scene shows *expected* active
paths that must be confirmed there.

## Setup (before recording)

1. **Create the BPF (recorded as screen 1):** make.powerapps.com → Solutions → **MGLabDataverse** → New → Automation →
   Process → **Business process flow**. Display name **Project Approval**, table **Project Request**, Create.
   (Learn: since August 2022 BPFs are created from a solution, not from Power Automate's list.)
   - Stage 1 **Submit**: steps Request Code, Customer Account, **Budget (Required)**.
   - **Condition** after Submit: *Budget is greater than or equal to 50000* (the branch must use a step of the stage
     right before it — Budget is in Submit).
   - Yes → stage **Finance Review**: steps **Business Justification (Required)**, Due Date.
   - No → connect to stage **Approve** (step Priority); Finance Review also continues to Approve.
   - Stage **Close** after Approve (no steps or a "Notes" step).
   - Validate, Save, **Activate**. Check the instance table name in Tables (expected `mgl_projectapproval`, display
     name *Project Approval*). If it differs, nothing to change in code (bpfkit reads it), but update the narration.
2. `export DATAVERSE_URL=https://<lab-env>.crm4.dynamics.com`; terminal dark, font 18+, short prompt.
3. `cd src && python3 -m bpfkit stages` — note the stage ids and whether the stages come back unordered.
4. **Recording order:** record screen 4 (`backfill`) **first**, so it shows the real first run, then screens 2–3,
   and put them back in script order in the edit. Before that, open **PR-0004** in the app once and **verify**
   whether the form creates an instance for a record that has none (note the result in README; if it does, PR-0004
   simply won't appear in the backfill list). Make sure PR-0004 has Budget 75,000 and PR-0001 42,000 (episode 1 data).
5. **Security check (optional, for the gotcha scene B-roll):** sign in as episode 2's *Alex Demo* (`alex.demo`, role *Project
   Requester*) in a private window and open PR-0004 → expected: no process bar. Then Power Platform admin center →
   Security roles → Project Requester → find the **Project Approval** table → Create/Read/Write at Organization (the
   table is organization-scoped) → the bar appears. Record what really happens.

## Screens to capture (match the `screen` scenes in script.yaml)

### 1. `screens/bpf-designer.jpg` — "Project Approval, with one branch" (**needs tenant**)
The whole flow visible in the designer (use the mini-map/zoom): Submit → condition → Finance Review / Approve →
Close, with the Budget step shown as Required. Status **Activated** in the header. Mask tenant name.

### 2. `screens/bpfkit-status.jpg` — "Status and a move, against the lab" (**needs tenant**)
```bash
python3 -m bpfkit status --code PR-0004
python3 -m bpfkit next --code PR-0004
python3 -m bpfkit status --code PR-0004
```
Expected: `active path: [>] Submit  [ ] Finance Review  [ ] Approve  [ ] Close`, then
`PR-0004: moved Submit -> Finance Review` with the PATCH body, then `[x] Submit  [>] Finance Review ...`.
**Verify and note in README:**
- the fields `RetrieveProcessInstances` returns (bpfkit prints `name` and `processstageid`; if the line shows `?`,
  inspect the raw JSON and fix `cmd_status`);
- that `RetrieveActivePath` for **PR-0001** (42,000) skips Finance Review (`status --code PR-0001`) — this is the
  `path` scene's "expected" line; replace "expected" with the real result;
- whether the move succeeds while Business Justification (a **required** step of Finance Review) is empty — it
  shouldn't matter for entering Finance Review, but try `next` again from Finance Review with the justification empty
  and record whether the API enforces required steps.
- `back --code PR-0004`, then `status`: record the traversed path the platform keeps (README "Not verified yet").

### 3. `screens/app-bpf.jpg` — "The same move, on the form" (**needs tenant**)
PR-0004 in the app after a refresh: process bar with Submit completed, **Finance Review** active, flyout open showing
Business Justification (required) and Due Date. Mask tenant name/avatar.

### 4. `screens/bpfkit-report.jpg` — "The report on lab data" (**needs tenant**)
```bash
python3 -m bpfkit backfill
python3 -m bpfkit backfill --apply
python3 -m bpfkit report
```
Expected: `N active record(s) without a 'Project Approval' instance` (up to 18), `+ PR-00xx: instance at Submit`
lines, `created N, failed 0`, then the report (mostly Submit, 0 d). For a more telling report, move a few records
with `next` before recording (PR-0002 and PR-0004 to Finance Review, PR-0001 to Approve). "Days in stage" will be
small on fresh data; say so in the narration rather than faking dates.

## Masking checklist
- Environment URL and org name (terminal, address bar), tenant name, user UPN/avatar.
- Only the fictional episode 1 data and lab test users on screen. GUIDs are environment-specific: blur if preferred.

## Tear-down
1. Optional: delete the instances (`DELETE mgl_projectapprovals(<id>)` or the table's data view).
2. In the solution: **Deactivate** Project Approval, then delete it; check under Tables that *Project Approval* is gone
   and delete it there if it isn't.
3. Remove the Project Approval privileges added to *Project Requester* (if the security check was done).
4. Keep Business Justification and the episode 1 data if later episodes use them.
