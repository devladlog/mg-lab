# Demo shot list — SharePoint #2 JSON formatting

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs / Azure / Power Platform | none |
| Tenant | **SharePoint** in the lab tenant: episode 1's site `/sites/ListsDemo` and its seeded **Purchase Requests** list (formats applied here, reset in tear-down) |
| Lab users | `labadmin` (the recording account): site owner, runs the script, owns "own requests". **`alex.demo` (Alex Demo)**: the other requester (from episode 1's seed) |
| Entra | The existing "MG Lab PnP" app registration (delegated) |
| Licences / trials | lab E5 licences; cost 0 |
| Recording machine | The Windows lab laptop: PowerShell 7.4+ with PnP.PowerShell 3.x and Pester; browser with `pipeline/mask.js` for the SharePoint screens; Python 3.10+ on PATH (the apply script runs formatlint first) |

The code scenes are real output from this folder (formatlint, pytest). The four `screen` scenes need the lab tenant.
**Needs tenant:** `Set-ListFormatting.ps1` against a real list (apply / export / reset) and everything the browser
shows. Locally the script is covered by Pester tests that mock the real PnP cmdlets, and the formats by the local
renderer, which is a test harness, not SharePoint.

## Prerequisites
| What | Notes | Cost |
|---|---|---|
| Lab tenant + test site from episode 1 | `/sites/ListsDemo` (or whatever episode 1 used) | €0 |
| **Purchase Requests** list provisioned and seeded by episode 1 | `Invoke-ListDesign.ps1 ... -SeedItems 40` | €0 |
| Entra app for PnP, delegated | existing "MG Lab PnP" app | €0 |
| PowerShell 7.4+, PnP.PowerShell 3.x, Python 3.10+ | `python3` must be on PATH: the apply script runs formatlint first | €0 |
| Edit / manage views permission on the list | site owner is fine | €0 |

## Set-up (before recording)
1. Run the tests: `python3 -m pytest tests -q` (62 passed) and `Invoke-Pester ./tests` (6 passed).
2. In the list, edit a few seeded items so the view shows every case the narration mentions. Use dates relative to
   the recording day:
   - one **open** request due **two or more days ago** (overdue, red, row highlighted)
   - one **open** request due **today** (must be amber — this confirms the date-only gotcha on camera)
   - one **open** request due in **3–5 days** (amber)
   - one **Closed** request with an **old** due date (plain)
   - one request with **no due date** (plain)
   - at least one requested by `labadmin` (the recording account) and one by Alex Demo
3. Reset any formatting: `./src/Set-ListFormatting.ps1 -SiteUrl $site -ClientId $app -Reset`.

## Screens to capture (match the `screen` scenes in script.yaml)

1. **`screens/before.jpg` — scene `before`**: Purchase Requests → view *Open requests*, unformatted.
2. **`screens/after.jpg` — scene `after`**: run
   ```powershell
   ./src/Set-ListFormatting.ps1 -SiteUrl $site -ClientId $app
   ```
   (expect "No findings." then four `Column` rows and one `View` row), refresh the same view and capture it. Check:
   status pills, overdue date red + bold + warning icon, due-today and due-soon amber, data bars, own requests in
   bold, overdue open rows highlighted. **If the due-today row is red, record it as is** and fix the README gotcha
   and narration — don't stage it.
3. **`screens/format-pane.jpg` — scene `pane`**: Due date header → Column settings → **Format this column** →
   Advanced mode; the JSON with `86400000` visible. Cancel, don't save.
4. **`screens/not-in-view.jpg` — scene `inview`**: create a **personal** view "Due dates only" with Title and Due
   date only; capture the closed, old-due-date request and how its date renders without Status in the view. Record
   what actually happens and adjust the `inview` narration if needed. Delete the personal view afterwards.

Optional insert for scene `apply`: run with `-Export ./backup` and show the exported files (no tenant data in them
beyond the formats themselves).

Add `crop`/`highlight` to each screen scene after capture (see episode 07's script for the format).

## Masking
- Tenant host in the address bar and in the `$site` line of the terminal; PnP client id; device-login code.
- Account avatars/photos and real names; requesters must be fictional display names (e.g. "Alex Demo").
- Amounts and titles are fictional (seed data from episode 1).

## Tear-down
```powershell
./src/Set-ListFormatting.ps1 -SiteUrl $site -ClientId $app -Reset     # if the list stays for later episodes
# or remove the lists entirely, see episode 1's demo.md
```
Delete the personal view "Due dates only" if it still exists.
