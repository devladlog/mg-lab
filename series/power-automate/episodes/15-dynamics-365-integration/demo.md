# Demo shot list: DEVLADLOG Power Automate #15, Dynamics 365 integration

## Lab environment

| Item | What this episode needs |
|---|---|
| VMs / Azure | none (no Azure resources, cost 0) |
| Tenant | The Dynamics 365 Sales trial environment **"Sales trial"** (EMEA, created 21 Nov 2026, 30-day trial, so record before ~21 Dec 2026): Sales Hub app with sample data. Everything (solution, flows, test data) lives in that environment. Mask the org URL in every capture |
| Lab users | `labadmin` (the recording account): System Administrator in "Sales trial", owner of the flows and of both connections. **`alex.demo` (Alex Demo)**: salesperson, owner of the demo opportunities, on screen in Sales Hub (needs a sales security role: give *Salesperson* in the environment). **`jordan.demo` (Jordan Demo)**: "sales manager", receives the digest and the finance mail in Outlook on the web (second browser profile). All hold the Dynamics 365 Sales trial licence |
| Licences | The **Microsoft Dataverse** connector is listed on Learn as *Premium* for Power Automate. `labadmin` starts the **self-service Power Automate Premium trial** the first time make.powerautomate.com asks (say so on camera). The Office 365 Outlook connector is standard. Whether the Dynamics 365 Sales licence already covers these flows in "Sales trial" is not verified here: if the trial prompt does not appear, nothing else is needed |
| Extra objects (created and deleted in this episode) | Solution **Sales follow-up** (`SalesFollowUp`, publisher `contoso`, prefix `cts`), one account **Fabrikam**, five opportunities (table in Setup 4), their tasks |
| Recording machine | The Windows lab laptop: browser with `pipeline/mask.js` (Sales Hub as Alex Demo, make.powerautomate.com as Lab Admin, Outlook on the web as Jordan Demo in a second profile) and a PowerShell 7 terminal in this folder with `pac` and Python 3 |

Everything in `src/` and `tests/` already runs locally (see README). Items marked **needs tenant** can't be validated from
the build container.

## Setup (≈ 45 min) - **needs tenant**

1. **Roles and sample data.** Open the *Sales trial* environment in the Power Platform admin center, confirm `labadmin`
   is System Administrator and give `alex.demo` the *Salesperson* role. Open **Sales Hub** once as `alex.demo` to check
   he can create opportunities.
2. **Pack and import the solution.** On the laptop:
   `pac solution pack --zipfile out/SalesFollowUp.zip --folder src/solution --packagetype Unmanaged` (no sign-in needed).
   In make.powerautomate.com choose the environment **Sales trial** > Solutions > Import solution > `SalesFollowUp.zip`.
   Create the two connections as `labadmin` (Dataverse, Office 365 Outlook) when the import asks for the connection
   references.
3. **Replace the placeholder addresses** inside both flows (never committed): `finance@contoso.com` ->
   `jordan.demo`'s address in *Tell finance*, `sales-managers@contoso.com` -> the same address in *Send digest*. Turn both
   flows **on**.
4. **Test data**, created in Sales Hub as `alex.demo` (owner = Alex Demo unless noted). Close dates are in the past on
   purpose; use today's date for "today". Rows 1, 2 and 5 are what the digest should list (open, before today):

   | # | Topic | Account | Est. revenue | Est. close date | Note |
   |---|---|---|---|---|---|
   | 1 | Fabrikam laptop refresh | Fabrikam | 12,500 | 3 weeks ago | the deal we close as won (big) |
   | 2 | Adatum chairs | Fabrikam | 1,800 | yesterday | small deal |
   | 3 | Litware monitors | Fabrikam | 4,200 | in 3 weeks | not overdue |
   | 4 | Northwind docks | Fabrikam | 3,000 | 2 months ago | owner `sam.demo` is fine; close it as **lost** to show it is not listed |
   | 5 | Tailspin printers | Fabrikam | 900 | 2 weeks ago | owner `sam.demo` (shows a second owner name in the digest) |

5. **Checks that can change the script** (do them before filming; each is listed in README "What was not verified"):
   a. **Does Close as Won fire the trigger?** Close a spare opportunity (not #1) as won and look at the run history of
      *Won opportunity follow-up*. If it does **not** run, open the flow, replace the trigger by
      *When a row is added, modified or deleted* on **Opportunity Close** (Added, filter `opportunitystatecode eq 1`;
      Learn: closing creates an Opportunity Close activity) and re-record the `trigger` and `fires` scenes.
   b. **Export and compare.** `pac solution export` + `pac solution unpack` of the imported solution over a temp folder and
      diff the two flow JSON files against `src/solution/`: the trigger keys (`subscriptionRequest/*`), `message` and
      `scope` numbers, and the two `@odata.bind` property names. Fix `tools/build_flows.py`, the tests and the
      `trigger` and `task` code scenes if they differ.
   c. **Run the digest filter in the terminal** (Setup 6) before the flow: confirm `estimatedclosedate lt <date>` is
      accepted on this Date Only column and that `-FormattedValues -PageSize 2` is accepted together.
   d. **Run the digest once by hand** (flow *Test* > Manually) and check the Owner column shows a name (the
      `...@OData.Community.Display.V1.FormattedValue` annotation is present in the List rows output).
6. **Terminal prep** (the recorder signs in out of band; the token is never shown or echoed):
   ```powershell
   $env:DATAVERSE_TOKEN = az account get-access-token --resource https://<org>.crm4.dynamics.com --query accessToken -o tsv
   function d365kit { python -m d365kit @args }   # the slides show the short name (run from src/)
   ```

## Screens to capture (match `screen` scenes in `script.yaml`)

| Scene id | File | What must be on screen |
|---|---|---|
| `won` | `screens/won.jpg` | Sales Hub, opportunity *Fabrikam laptop refresh*: **Close as Won** dialog (actual revenue 12,500). Then make.powerautomate.com run history of *Won opportunity follow-up*: trigger, *Get opportunity*, *List existing kickoff tasks*, *Create kickoff task*, *Tell finance* all green. Split screen or two takes |
| `task` | `screens/task.jpg` | The opportunity timeline: exactly one open task **Kick-off call**, regarding the opportunity, owner Alex Demo, due in three days. Second take: **Reactivate** the opportunity and close it as won again; the run history shows a second run with *Create kickoff task* skipped, and the timeline still has one task |
| `query` | `screens/query.jpg` | Terminal: `./src/scripts/Invoke-DataverseQuery.ps1 -OrgUrl https://<org>.crm4.dynamics.com -Table opportunities -Filter "statecode eq 0 and estimatedclosedate lt <yyyy-MM-dd>" -Select name,estimatedvalue,estimatedclosedate -Expand 'parentaccountid($select=name)' -OrderBy 'estimatedclosedate asc,opportunityid asc' -PageSize 2 -FormattedValues -PrintOnly`, then the same without `-PrintOnly` ("3 row(s) in 2 page(s)") |
| `digest` | `screens/digest.jpg` | Jordan Demo's Outlook on the web: mail *Overdue opportunities: 3* with the HTML table (Fabrikam laptop refresh, Adatum chairs, Tailspin printers; owners Alex Demo and Sam Demo); beside it the run history of *Overdue opportunities digest* (manual test run) |

Code scenes (`trigger`, `fires`, `task`, `paging`, `gotcha`, `tests`) come from this folder; re-run the commands before
recording and update the excerpts if step 5b changed the JSON. The `fires` and `gotcha` scenes use
`python -m d365kit fires/lint` on `src/solution/Workflows/Wonopportunityfollowup-*.json` (for `gotcha`, a copy whose
*Select columns* is `statecode,parentaccountid,opportunityid`, as in README).

For the `gotcha` scene it is worth proving the Learn claim once in the tenant: temporarily add `parentaccountid` to
*Select columns*, change the account of an opportunity, and show that no run starts (undo afterwards).

## Run the code on the recording machine

```powershell
python -m pytest                     # 50 passed
pwsh -NoProfile -Command "Invoke-Pester ./tests/Invoke-DataverseQuery.Tests.ps1"   # 12 passed
cd src; python -m d365kit lint solution/Workflows/Wonopportunityfollowup-*[0-9].json
```

## Masking

- `pipeline/mask.js` in the browser; `series_label: "POWER AUTOMATE"`.
- Hide the org URL (`*.crm4.dynamics.com`), the environment id, every GUID in the terminal and run history, and the access
  token (never `echo` it; the script reads `$env:DATAVERSE_TOKEN`). Only Alex Demo, Sam Demo, Jordan Demo and Lab Admin
  on screen; Dynamics sample data names with "(sample)" are fine.
- Before committing an exported solution, put back `finance@contoso.com`, `sales-managers@contoso.com` and the org URL
  `https://contoso.crm4.dynamics.com`.

## Tear-down

- Turn off both flows; delete the solution **Sales follow-up** including its flows and connection references.
- Delete the five test opportunities, the account **Fabrikam** and the tasks **Kick-off call** (Sales Hub, or Advanced
  Find). Remove `alex.demo`'s *Salesperson* role if it was added only for this episode.
- `Remove-Item Env:DATAVERSE_TOKEN` and close the PowerShell session. The trial environment itself is left alone.
