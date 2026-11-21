# Demo shot list: DEVLADLOG Power Automate #13, Business process flows

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs / Azure | none (no Azure resources, cost 0) |
| Tenant | Power Platform environment **`DEV`** (Dataverse). Solution `Purchase BPF` (unique name `PurchaseBpf`, publisher prefix `cts`). A model-driven app **Purchasing** with the table form |
| Lab users | `labadmin` (the recording account): maker, system administrator in `DEV`, owner of the flows. **`alex.demo` (Alex Demo)**: requester, on screen in the form. **`jordan.demo` (Jordan Demo)**: finance approver (answers the approval in Outlook on the web). `sam.demo` is Alex's manager from episode 2 (only needed if the manager decision is shown being set by him; otherwise `labadmin` sets it) |
| Licences | Maker needs a **per user Power Apps or Power Automate licence, or a Dynamics 365 plan that includes business process flow rights** (Learn, *Create a business process flow*). Lab users hold the Dynamics 365 Sales trial licence: check on `labadmin` that the designer opens before filming. The Dataverse and Approvals connectors are used as standard connectors; if the designer shows a premium badge on any action, start the self-service Power Automate Premium trial for `labadmin` (say so on camera) |
| Extra objects (created and deleted in this episode) | Dataverse table **Purchase request** (`cts_purchaserequest`), the BPF **Purchase request process**, security role **Purchasing user**, Microsoft 365 group `finance-approvers` (from episode 2; recreate with member `jordan.demo` if deleted) |
| Recording machine | The Windows lab laptop: browser with `pipeline/mask.js` (make.powerapps.com designer, the Purchasing app, make.powerautomate.com, Outlook on the web in a second profile for Jordan Demo) and a PowerShell 7 terminal in this folder, plus `pac` and Python 3 for the tests |

Everything in `src/` and `tests/` already runs locally (see README). Items marked **needs tenant** can't be validated from
the build container.

## Setup (≈ 60 min) — **needs tenant**

1. **Solution and table.** In `DEV`: solution `Purchase BPF`, publisher `contoso` with prefix `cts`. New table
   **Purchase request** (`cts_purchaserequest`), tick **Business process flows (fields will be created)** (irreversible;
   removed in tear-down by deleting the table). Columns, exact logical names: `cts_amount` (Currency or Decimal, EUR),
   `cts_justification` (Multiple lines), `cts_neededby` (Date only), `cts_managerdecision` / `cts_financedecision`
   (Choice: *Approved*, *Rejected*; **option values** `444460000` and `444460001`, the default for prefix 44446),
   `cts_ponumber` (Text), `cts_received` (Choice: *Yes*, *No, partial*, *No, missing*), `cts_activestage` (Text).
   Add the table to a model-driven app **Purchasing** with its main form.
2. **Security.** Role **Purchasing user** (create/read/write on Purchase request) for `alex.demo`; on the BPF table the
   default is *System Administrator / System Customizer only* (Learn): give the role access to **Purchase request
   process** (Business Process Flows tab) after step 4.
3. **BPF.** *New → Automation → Process → Business process flow*, display name **Purchase request process**, name
   `purchaserequestprocess`, table Purchase request. Build the stages and steps exactly as in
   `src/process/purchase-request-process.json`; **do not add Amount to *Manager review* yet** (step 4 needs the failure).
   Use stage categories Qualify / Develop / Propose / Close as in the file.
4. **Gotcha 1, on camera.** Add the **Condition** tile after *Manager review* with rule *Amount ≥ 5000 AND Manager
   decision = Approved*. Record what the designer does when *Amount* is not a step of the preceding stage (the
   rule-builder should only offer the steps of *Manager review*). **This confirms the Learn rule; if the designer behaves
   differently, change the `branch-rule` scene and README gotcha 1 before publishing.** Then add *Amount* (not required)
   to *Manager review* and finish the branch: Yes → *Finance review*, No → *Order*, merging at *Order*. Add the global
   workflow trigger *Process completed* only if a workflow exists (optional; the design lists "Notify requester").
   **Validate**, **Save**, **Activate**.
5. **Read back the real names** (becomes the values in `src/samples/stage-ids.json` for the recording, never committed):
   ```powershell
   # token for the Web API: the recorder signs in; the token is never shown or saved
   $env:DATAVERSE_TOKEN = az account get-access-token --resource https://<org>.crm4.dynamics.com --query accessToken -o tsv
   Invoke-RestMethod "https://<org>.crm4.dynamics.com/api/data/v9.2/EntityDefinitions?`$select=LogicalName,EntitySetName&`$filter=IsBPFEntity eq true" -Headers @{Authorization="Bearer $env:DATAVERSE_TOKEN"}
   ```
   Check that the BPF table's entity set matches `cts_purchaserequestprocesses` (else pass the real one to `-BpfTable`)
   and that `$metadata` shows `bpf_purchaserequestid` as the navigation property (README "not verified").
6. **Flows.** `pac solution pack --zipfile out/PurchaseBpf.zip --folder src/solution --packagetype Unmanaged`, import into
   `DEV`, create the two connection references (Dataverse, Approvals) with `labadmin`, replace
   `finance-approvers@contoso.com` with the group address in the lab tenant, turn both flows on. Then in the BPF designer
   drag **Flow Step (Preview)** onto *Finance review*, pick **Finance review step**, **Apply**, **Update** (re-activate).
   **Compare with the JSON**: if the trigger `operationId`, the `subscriptionRequest/*` keys, `message`/`scope` values or
   the Process Log column values differ, export (`pac solution export` + `unpack`) over `src/solution/`, adjust
   `tests/test_flows.py` and the README ("not verified").
7. **Sample data.** As `alex.demo` create two requests: *Ergonomic chairs* 1,800 and *Laptops for two new developers*
   12,500, each with a justification.

## Screens to capture (match `screen` scenes in `script.yaml`)

| Scene id | File | What must be on screen |
|---|---|---|
| `designer` | `screens/designer.jpg` | The BPF designer with Submit, Manager review, the Condition tile (both rules visible), Finance review (flow step icon) on the Yes branch, Order, Close. Mask the org URL |
| `gate` | `screens/gate.jpg` | Alex Demo's request form on *Submit* with Justification empty, **Next Stage** pressed and the required-field message; then (second take, same shot) the field filled and the bar on *Manager review* |
| `flowrun` | `screens/flowrun.jpg` | Run history of *Finance review step* for the 12,500 EUR request: all green, *Finance decision* on the Approve branch, *Complete flow step* green; side by side with the form where the step shows Completed. Jordan Demo's Outlook approval can be a cut-in |
| `script` | `screens/script.jpg` | Terminal: `./src/scripts/Set-BpfStage.ps1 -OrgUrl https://<org>.crm4.dynamics.com -BpfTable cts_purchaserequestprocesses -Operation Next -InstanceId <id> -WhatIf` (PATCH printed), the same without `-WhatIf`, then `-Operation ListInstances`; next to it the form's process bar moved. Instance ids come from `ListInstances` |

Take for the gate scene (cross-check with the narration): press **Next Stage** with *Justification* empty; also try a
required Two Options column on a throwaway step to confirm that *No* does not pass (README gotcha 2).

Code scenes (`definition`, `branch-rule`, `engine`, `flowstep`, `webapi`, `tests`) come from this folder; re-run the
commands before recording and update the excerpts if step 6 changed the JSON.

## Run the code on the recording machine

```powershell
python -m pytest                     # 36 passed
cd src; python -m bpfkit validate process/purchase-request-process.json
```

## Masking

- `pipeline/mask.js` in the browser; `series_label: "POWER AUTOMATE"`.
- Hide the org URL (`*.crm4.dynamics.com`), the environment id, every GUID in the terminal, approval ids and the access
  token (never `echo` it; the script reads `$env:DATAVERSE_TOKEN`). Only Alex Demo, Jordan Demo and Lab Admin on screen.
- Before committing an exported solution, replace the org URL with `https://contoso.crm4.dynamics.com` and any real
  group address with `finance-approvers@contoso.com`.

## Tear-down

- Turn off both flows; delete solution `Purchase BPF` **including** its components (BPF, table `cts_purchaserequest`,
  connection references). Deleting the table removes the BPF table and instances.
- Delete the role **Purchasing user**; keep `finance-approvers` if episode 15 or another episode reuses it.
- Remove the token from the terminal (`Remove-Item Env:DATAVERSE_TOKEN`) and close the PowerShell session.
