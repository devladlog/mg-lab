# Demo shot list: DEVLADLOG Power Automate #10, performance optimization

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs | none (the Hyper-V lab 10.50.0.0/24 is not used) |
| Power Platform | **`DEV`** (exists, Dataverse), same environment as episode 9. The solution `IT Housekeeping` (unique name `ITHousekeeping`, publisher *contoso*, prefix `cts`) is imported unmanaged |
| SharePoint | Site `IT Helpdesk` with list **IT Requests** (episode 1). Add: choice value **`Archived`** to `Status`, and a **date and time column `DoneOn`**. We use `DoneOn` because `Modified` cannot be backdated, so it is the only way to make old Done items on demand. Then *List settings -> Indexed columns*: index **`Status`** and **`DoneOn`** (screen 4) |
| Lab users | `labadmin` (recording account, owns both connections, runs the seed script), `taylor.demo` (Taylor Demo): the service desk mailbox that receives the summary email |
| Licences | Standard connectors only (SharePoint, Office 365 Outlook), covered by the lab E5 licences. Cost 0. **The lab uses trial licences, and Learn puts "all license trials" in the Low performance profile (10,000 actions per 24 hours)**, so the demo is sized to stay under it (see "Budget for the day") |
| Recording machine | Windows lab laptop: browser with `pipeline/mask.js`, terminal with Python 3.10+, PowerShell 7 and the **PnP.PowerShell** module (`Install-Module PnP.PowerShell -Scope CurrentUser`, off camera), `pac` |

Everything in `src/` and `tests/` runs locally (README). **Needs tenant** is marked on each step below.

## Budget for the day (Low profile, 10,000 actions per 24 hours, sliding window)

Counts from `python -m perfkit compare`, at 40 percent of the items ready to archive:

| Run | Actions |
|---|---|
| slow draft, 1,000 items | 2,806 |
| tuned flow, 1,000 items, concurrency 1, then 20, then 50 (re-seed between) | 3 x 406 = 1,218 |
| **Total on day 1** | **about 4,100** (the seed script and the browser add none) |

The 2,000 item slow run (5,606) goes on **another day** or after a 24 hour gap. **Never run the slow draft at 4,000 items for real**: 11,206 actions is over the Low limit, which is the point of the episode, and Learn says a flow above the limit slows down and can be suspended. The 4,000 row is shown from the dry run only. Do not run any other flow of `labadmin` that day.

## Prerequisites check (before recording)

1. `python -m pytest` in this folder: all tests pass (see README for the count). `pwsh` with Pester 5 or later.
2. `python -m perfkit compare drafts/slow-archive-done-requests.json solution/Workflows/*.json` prints the table of scene "compare".
3. Mask: environment URL, tenant name, account, site URL.

## Setup (about 40 min) **needs tenant**

1. **Columns and indexes** as in the table above. Check that the list has no real data: every seeded title starts with `[TEST] seed `, so episode 1's flow ignores them.
2. **Import the tuned solution.** Interactive sign-in as `labadmin`, off camera:
   ```bash
   pac auth create --name dev --environment <DEV url>
   cd series/power-automate/episodes/10-performance-optimization/src
   pac solution pack --zipfile ../out/ITHousekeeping.zip --folder solution --packagetype Unmanaged
   pac solution import --path ../out/ITHousekeeping.zip
   ```
   Fill the environment variables (site URL, list `IT Requests`, `cts_ArchiveAfterDays` 30, mailbox) and sign in the two connection references. **If the import rejects the flow**, the flow JSON was hand-written and never imported by the real service (README, not verified): build the flow by hand following `src/solution/Workflows/*.json` (action names must match what the screens show), then export and replace `src/solution` with the real unpack, and re-run `python -m pytest`.
3. **The slow draft** is not in the solution. Build it by hand in a **second** flow named `Archive done IT requests (draft)`, following `src/drafts/slow-archive-done-requests.json` (Get items with no filter, Apply to each with Get item, a Condition, Update item and an Increment variable). Turn **both flows off** until the test.
4. **Connect and seed 1,000 items** (the script uses the current PnP connection):
   ```powershell
   Connect-PnPOnline -Url <IT Helpdesk site URL> -Interactive -ClientId <your PnP app id>
   ./scripts/Seed-ITRequests.ps1 -Count 1000          # 400 Done 31+ days ago, 100 Done recently, 500 open
   ```
   `-WhatIf` first shows what it would do. Check the list shows 1,000 items and the filter `Status = Done` in the list view returns 500.

## Screens (3 to 5 in the script) **needs tenant**

| # | Image | What to show | When |
|---|---|---|---|
| 1 | `screens/slowrun.jpg` | Draft flow, **Run history**: turn the flow on or *Run* manually once on the 1,000 item list. Show Start and **Duration**; open the run, expand Apply to each (Get item again and the If repeated per item). Read the duration off the screen and **write it in the README table** | scene `slowrun` |
| 2 | `screens/fastrun.jpg` | Re-seed (below), run the tuned flow with Apply to each concurrency **1**, re-seed, **20**, re-seed, **50** (*Settings* on the loop). Show the three Durations in Run history | scene `fastrun` |
| 3 | `screens/analytics.jpg` | Flow details -> **Analytics -> Actions** for both flows. Compare with the dry run: 2,806 and 406. Analytics can lag; if it is empty, wait and retake. **If the numbers differ from the dry run, keep the real ones and fix the README and the script narration** | scene `analytics` |
| 4 | `screens/listindex.jpg` | List settings -> Indexed columns (Status, DoneOn), item count visible | scene `index` |

Re-seeding between runs (the tuned flow archives 400 items and leaves them Archived):
```powershell
./scripts/Seed-ITRequests.ps1 -Cleanup            # removes only titles starting "[TEST] seed " (recycle bin)
./scripts/Seed-ITRequests.ps1 -Count 1000
```
Real timing depends on SharePoint throttling (600 calls per minute per connection, Learn), so durations will be longer than the dry run's lower bound. Do not edit them.

## Terminal takes (local, no tenant)

1. `python -m perfkit lint drafts/slow-archive-done-requests.json` then `... solution/Workflows/*.json` (4 findings, then 0).
2. `python -m perfkit compare drafts/slow-archive-done-requests.json solution/Workflows/*.json` (the short).
3. `python -m pytest -k "pagination or unindexed"` for the gotcha. Say on camera that the list is a **model of the documented limitation**, not the service.

## Optional: the gotcha on the real service **needs tenant**

Seed 6,000 items (`-Count 6000 -DoneOldFraction 0`), set 500 of the last ones to Done with an old `DoneOn`, turn pagination **off** on Get done requests and run: the Learn page says it should return no items. We have not tried it. Only add it to the video if it reproduces; otherwise leave the scene as the documented limitation. Seeding 6,000 items is about 60 batches of 100.

## Tear-down

1. `./scripts/Seed-ITRequests.ps1 -Cleanup`, then empty the site's Recycle Bin (both stages).
2. Delete the draft flow and the `IT Housekeeping` solution from DEV (*Delete -> Delete this component* for the managed pieces if asked). Remove the `Archived` value, `DoneOn` and the two indexes if episode 1's list must go back to how it was.
3. `pac auth clear` and remove `ITHousekeeping.zip` from `out/`. Check `labadmin`'s Analytics shows no leftover runs; both flows stay off.
