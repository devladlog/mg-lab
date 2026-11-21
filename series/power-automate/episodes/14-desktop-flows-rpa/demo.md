# Demo shot list: DEVLADLOG Power Automate #14, Desktop flows and RPA

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs / Azure | Windows 11 VM **CON-W11-01** (Entra-joined, 90-day eval, Hyper-V network 10.50.0.0/24) as the registered machine. No Azure resources, cost 0 |
| Tenant | Environment **`DEV`**. SharePoint site `Purchasing`, list **Purchase Requests** (from episode 2) with added columns `Supplier` (text), `PONumber` (text), `RpaStatus` (text). Solution `Purchase RPA` (`PurchaseRpa`) |
| Lab users | `labadmin` (maker, owner of the connection and the machine registration), **`alex.demo` (Alex Demo)** requester on screen, `sam.demo` approves, `jordan.demo` is in the purchasing team mailbox |
| Licences | Self-service **Power Automate Premium trial** for `labadmin`: covers **attended** runs from the cloud. **Unattended needs a Process licence** (Learn disagrees on the trial: do not film unattended unless the tenant shows an unattended bot on the machine) |
| Recording machine | The laptop (browser with `pipeline/mask.js`, terminal) and a remote session to CON-W11-01 |

Everything in `src/` and `tests/` runs locally (README). Items marked **needs tenant** cannot be validated from the build container.

## Setup (about 60 min) — **needs tenant**

1. **Windows 11 machine.** Power Automate for desktop is included in Windows 11 (Windows 10 needs the download). Copy
   `src/scripts/*.ps1` to `C:\MGLab\scripts`, publish the app (`dotnet publish src/legacy-app/App -c Release`) to
   `C:\MGLab\ContosoPurchasing`, create `C:\MGLab\run`. Sign in as the lab user; keep the session open (attended).
2. **Register the machine** (Power Automate machine runtime, Machine settings, environment `DEV`).
3. **Desktop flow.** In Power Automate for desktop build **Enter purchase order** from `src/desktop-flow/enter-purchase-order.robin.txt`
   and the contract (inputs Supplier, Description, Amount, RequestId; outputs Status, OrderNumber, Errors). Copy the
   designer text back over the `.robin.txt` file (**the draft was never run**) and re-run `python -m padkit lint`.
   Verify in the designer: PowerShell action runs Windows PowerShell 5.1 (if the scripts fail, report); amount culture
   (README gotcha 2) with the machine set to a comma-decimal region.
4. **Connection.** Data, Connections, New connection, **Desktop flows**, attended sign-in method, pick CON-W11-01.
5. **Cloud flow.** `pac solution pack --zipfile out/PurchaseRpa.zip --folder src/solution --packagetype Unmanaged`,
   import to `DEV`, set the three connection references, set the real `uiFlowId` of the desktop flow, replace
   `contoso.sharepoint.com` with the lab site URL. Compare the action with the JSON ("not verified": `item/*` keys), turn on.
6. **Data.** As `alex.demo` add two requests (Fabrikam 12,500 and a "Supplier empty" one); `sam.demo` approves them.
7. **Gotcha takes.** (a) Put `' ; Get-Date #` in the supplier and show the file-based flow handles it. (b) Close the app
   mid-run to show the ledger check failing and the Catch email. (c) Edit the item by hand after a run: no new run.

## Screens to capture (match `screen` scenes in `script.yaml`)

| Scene id | File | What must be on screen |
|---|---|---|
| `legacy` | `screens/legacyapp.jpg` | Contoso Purchasing, New order, filled with Fabrikam / Laptops / 12500, and the "order saved" message box. **needs tenant**: no, only the VM |
| `designer` | `screens/pad.jpg` | Power Automate for desktop, flow *Enter purchase order*, variables pane with inputs and outputs and the action list. Mask the user name |
| `flowrun` | `screens/flowrun.jpg` | Run history of *Enter approved purchase orders* (all green, branch *Saved*) next to the SharePoint item showing PO number and RPA status. Mask the tenant URL |
| `tests` | `screens/tests.jpg` | Terminal: `python -m pytest` (23 passed), Pester (23 passed), `dotnet test` (9 passed) |

## Masking

- `pipeline/mask.js` in the browser; `series_label: "POWER AUTOMATE"`.
- Hide tenant and site URLs, the environment id, machine and connection ids, the desktop flow id, and user names in
  the Windows title bars. Never show or `echo` a token (`Invoke-DesktopFlow.ps1` reads `$env:DATAVERSE_TOKEN`).
- Only fictional data: Fabrikam, Alex Demo, zero GUIDs in committed files.

## Tear-down

- Turn off the cloud flow, delete solution `Purchase RPA` and the desktop flow connection.
- Unregister CON-W11-01 from the environment; delete `C:\MGLab` and `%LOCALAPPDATA%\ContosoLegacy`.
- Delete the added list columns and test items; `Remove-Item Env:DATAVERSE_TOKEN`.
- Stop the VM (the 90-day evaluation keeps running while it exists).
