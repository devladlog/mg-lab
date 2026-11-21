# DEVLADLOG Power Automate #14: Desktop flows and RPA for apps without an API

Continues the purchasing scenario of episodes 2 to 4 and 13. An approved purchase request (SharePoint list **Purchase
Requests**) must become an order in **Contoso Purchasing**, a legacy Windows Forms application with no API. A cloud flow
starts a **desktop flow** that types the order into the window, and the result comes back to the request. Everything
around the click-through (the app, the scripts, the cloud flow, the checks) is built and tested without a tenant.

| Path | What it is |
|---|---|
| [`src/legacy-app/`](src/legacy-app) | The "legacy" app: `Core` (validation, CSV ledger, PO numbering), `App` (WinForms, net8.0-windows, built on Linux with `EnableWindowsTargeting`), `Tests` (xUnit, 9 tests) |
| [`src/scripts/`](src/scripts) | `Test-PurchaseOrder.ps1` (pre-flight validation, culture-safe amount), `Confirm-PurchaseOrder.ps1` (reads the ledger back), `Invoke-DesktopFlow.ps1` (Dataverse `RunDesktopFlow`, poll `flowsession`, outputs, cancel; `-WhatIf`) |
| [`src/desktop-flow/`](src/desktop-flow) | The contract (inputs and outputs) and a **draft** of the desktop flow actions (see "What was not verified") |
| [`src/solution/`](src/solution) | Unpacked solution `PurchaseRpa`: cloud flow *Enter approved purchase orders* (Try / Catch scopes, `RunUIFlow_V2`), 3 connection references |
| [`src/tools/build_flows.py`](src/tools) | Writes the flow JSON |
| [`src/padkit/`](src/padkit) | `contract.py` (rules PAD101-109: cloud call vs the desktop flow's contract) and `lint.py` (PAD001-004: unassigned output, hard-coded secret, message dialog in an unattended run, free text pasted into script text). CLI: `python -m padkit lint / contract` |
| [`src/flowkit/`](src/flowkit) | Lint, expression engine and simulator from earlier episodes; this episode adds `result()` and scope results |
| [`src/samples/`](src/samples) | An approved request, mocked desktop run results |
| [`tests/`](tests) | 23 pytest tests (one runs the Pester suite, one runs `pac solution pack`), 23 Pester tests, 9 xUnit tests |

## Run it

```bash
cd series/power-automate/episodes/14-desktop-flows-rpa
python -m pytest                                              # 23 passed (includes the Pester suite and pac solution pack)
pwsh -NoProfile -Command "Invoke-Pester ./tests/Scripts.Tests.ps1"   # 23 passed (Pester 6.2, PowerShell 7.6)
dotnet test src/legacy-app/Tests -m:1                         # 9 passed (.NET 8)

cd src
python -m padkit lint desktop-flow/enter-purchase-order.robin.txt --contract desktop-flow/enter-purchase-order.contract.json   # OK
python -m padkit contract solution/Workflows/Enterapprovedpurchaseorders-*.json --contract desktop-flow/enter-purchase-order.contract.json   # OK
python -m flowkit lint solution/Workflows/*.json
pac solution pack --zipfile ../out/PurchaseRpa.zip --folder solution --packagetype Unmanaged
```

Delete `src/legacy-app/*/bin` and `obj` afterwards. No sign-in, no network; `pac auth` is never used.
The PowerShell scripts run for real (the injection tests execute hostile text on purpose); only `Invoke-RestMethod` is
mocked. The click-through needs a Windows desktop and is **not** run here.

## What we learned / gotchas

1. **`%variables%` are pasted into the script text.** In *Run PowerShell script*, Power Automate variables are
   evaluated *before* the script runs (Learn, *Scripting actions*), so a supplier named `x'; Remove-Item ...` becomes code.
   Fix used here: write each field to its own file and let the script read the files. Pester tests prove the files are safe
   and a **negative control** proves the inline pattern really executes the text; `padkit` rule PAD004 flags it.
2. **Never send the amount as a number.** The desktop flow types into a window that parses with the machine culture. On
   this build machine (ICU on Linux) pt-PT rejects `1800.50` and en-US reads `1800,50` as 180050. The cloud flow sends
   `formatNumber(..., '0.00', 'en-US')` as text and the pre-flight script converts it for the app. *Confirm on the
   Windows machine: not verified, see below.*
3. **A click on Save proves nothing.** The robot reads the legacy ledger back (`Confirm-PurchaseOrder.ps1`, only rows
   saved after the run started) and fails loudly if the order is not there.
4. **Loop guard.** The SharePoint trigger fires on every modification, including our own `PatchItem`. The trigger
   condition requires `RpaStatus` to be empty; tests prove items with a status do not start the flow.
5. **A failed desktop run needs a Catch scope.** Test with the Catch removed: the failed run marks nothing and tells
   nobody (the flow still ends "Succeeded" because the join action runs after a skipped branch).
6. **Attended vs unattended licensing.** Learn: attended runs from the cloud need a premium per-user plan with attended
   RPA; unattended needs a Process licence (one bot per concurrent run). The user of the connection needs a Premium
   licence too. Learn pages disagree on whether the Premium trial includes unattended, so the demo only claims attended.
7. **Unattended rules.** Windows 10/11 cannot run unattended if any user session exists, even locked; the run uses an RDP
   session with the screen locked and a default resolution that may differ from authoring (keyboard-driven input helps);
   message dialogs have no one to read them (PAD003).
8. **Limits.** 2 MB of input per run; 70 desktop runs per minute per connection (Learn, *Trigger desktop flows from cloud
   flows*); a timeout on the cloud action (`PT30M` here) stops a stuck window hanging the flow.

### What was not verified here

- **The desktop flow itself.** `enter-purchase-order.robin.txt` is hand-written action text, never pasted into the
  designer. Action names and syntax (`Scripting.RunPowershellScript...`, `File.WriteText`, `SendKeys` with `{Tab}` /
  `{Enter}`, `Flow.Exit`, `Variables.ConvertJsonToCustomObject`) must be checked in Power Automate for desktop; the
  recording session replaces the file with the text the designer copies and re-runs `padkit lint`.
- **Cloud flow parameter keys** (`item/<Name>`, `outputs(...)['body/<Name>']`) and the `RunUIFlow_V2` details were
  taken from Learn and the connector reference, not from an exported flow.
- **PowerShell version in the action.** Learn says the action starts `powershell.exe` (Windows PowerShell 5.1); the
  scripts were run on PowerShell 7.6 only.
- **Culture behaviour on Windows** (gotcha 2) was observed on Linux/ICU only.
- **`flowsession` statuses** are listed in Learn (1 Paused ... 14 Terminated); which are terminal is inferred from the names.
- Learn contradicts itself on the unattended trial (gotcha 6).

## References

- Trigger desktop flows from cloud flows (limits, 70 runs/min, 2 MB): https://learn.microsoft.com/power-automate/desktop-flows/trigger-desktop-flows
- Manage machines: https://learn.microsoft.com/power-automate/desktop-flows/manage-machines
- Manage desktop flow connections: https://learn.microsoft.com/power-automate/desktop-flows/desktop-flow-connections
- Run unattended desktop flows: https://learn.microsoft.com/power-automate/desktop-flows/run-unattended-desktop-flows
- Scripting actions (Run PowerShell script, `%` variables): https://learn.microsoft.com/power-automate/desktop-flows/actions-reference/scripting
- Work with desktop flows using code (`RunDesktopFlow`, `flowsession`): https://learn.microsoft.com/power-automate/developer/desktop-flow-public-apis
- Types of Power Automate licenses: https://learn.microsoft.com/power-platform/admin/power-automate-licensing/types
- Power Automate licensing FAQ: https://learn.microsoft.com/power-platform/admin/power-automate-licensing/faqs
- Requests limits and allocations: https://learn.microsoft.com/power-platform/admin/api-request-limits-allocations
- Run PowerShell script troubleshooting (`powershell.exe`): https://learn.microsoft.com/troubleshoot/power-platform/power-automate/desktop-flows/failed-to-run-powershell-script-error
- Blog, Complete Guide: https://www.devladlog.com/articles/power-automate/2025-02-03-desktop-flows-rpa-complete-guide-2025/
