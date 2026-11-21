# Demo guide: episode 11, build a canvas app from start to end

## Lab environment

- Tenant: the lab tenant, environment `DEV` (Dataverse, standard environment). Nothing in this episode has been run against it yet: the
  builder had no sign-in. Everything marked **needs tenant** below must be done and recorded by the recorder.
- People: the lab administrator (builds, shares), **Alex Demo** (inspector, phone), **Sam Demo** (second inspector, to show row isolation).
  Fictional addresses used in the sample data: `alex.demo@contoso.com`, `sam.demo@contoso.com`. Replace them with the lab users' real UPNs
  only on the command line, never in files in this folder.
- Premium: the app uses Dataverse, so the users need a Power Apps premium entitlement. Use the self-service **Power Apps trial**
  (Learn: "Explore Power Apps for free for 30 days"). No AI credits, no pay-as-you-go plan.
- Devices: the lab Windows host for Studio and the admin center, one real phone with the **Power Apps** mobile app (Android or iOS) and its
  built-in screen recorder. No emulator, no browser device mode: the offline and camera scenes must be a real phone.
- Tools on the recorder's machine: PowerShell 7, Azure CLI (only to fetch a token), Power Platform CLI. The recorder signs in; the
  scripts in this folder never do.
- Azure resources: none. (If anything is created, it goes in `rg-mglab-powerapps-11`.)

## Run order (recorder checklist)

Rows marked **local** need no tenant and are already covered by the tests. Rows marked **needs tenant** are not proven by anything in this
folder.

### A. Prove the local parts first (local)

1. `cd tests/python && python3 -m pytest -q` (28 passed), `cd tests/pester && pwsh -NoProfile -Command "Import-Module /root/.local/share/powershell/Modules/Pester; Invoke-Pester -Path ./Provision.Tests.ps1"` (15 passed),
   `cd tests/ContosoInspections.Canvas.Tests && dotnet test -m:1` (104 passed). Delete `bin`, `obj` and caches afterwards.
2. `pwsh -File src/scripts/Provision-ContosoInspections.ps1 -EnvironmentUrl https://contoso.crm.dynamics.com -PlanOnly`: shows the plan.
   Show this in the terminal for the `provision` scene.

### B. Create the schema (needs tenant)

3. Sign in as the lab administrator: `az login` (recorder only). Get a token for the DEV environment URL:
   `$env:DATAVERSE_ACCESS_TOKEN = (az account get-access-token --resource <DEV url> --query accessToken -o tsv)`. Do not show the token or the URL.
4. Run `src/scripts/Provision-ContosoInspections.ps1 -EnvironmentUrl <DEV url> -SeedData -AlexEmail <Alex UPN> -SamEmail <Sam UPN>`.
   Expected: publisher, solution, 4 tables, 18 columns, 3 relationships, the Contoso Inspector role, 3 sites, 2 inspectors, then publish.
   Run it a second time: nothing is created twice.
5. make.powerapps.com > Solutions > ContosoInspections > Tables. Open Inspection > Columns and Finding > Columns. Record for `tables-screen`.
6. Assign the Contoso Inspector role to Alex Demo and Sam Demo (Admin center > Environment > Users > Manage security roles).
   The Contoso Inspector role has not been created by this builder, so check the 18 privileges on the role page.
   **Unverified:** the privilege names for the system tables (canvas app, mobile offline profile, sync error) and adding the role to the
   solution by component type 20. If the script reports an error here, create or fix the role in the UI, and note it in the video.

### C. Build the app in Studio (needs tenant)

7. Solutions > ContosoInspections > New > App > Canvas app > Phone. Name it `Contoso Inspections`. Record for `newapp-screen`.
8. Add data: Dataverse > Inspections, Findings, Sites, Inspectors.
9. Settings > Display: Scale to fit **off**, Lock aspect ratio **off**, Lock orientation **off**. Settings > Updates: Data row limit 500.
10. Paste the source from `src/app/Src`. Two ways: (a) coauthoring + the canvas authoring MCP server (Learn: "Create and edit canvas apps
    with AI code generation tools"), or (b) create the screens and controls by hand and paste each Power Fx property. **Unverified:** that
    Studio accepts every control type name in these files (`Camera`, `Classic/Dropdown`, `Classic/Icon`, `GroupContainer` with
    `Variant: AutoLayout`) and the `Formulas` property with the UDFs. Fix any file Studio rejects and say so on screen.
    `pac canvas pack` cannot build an msapp from these files offline in a way proven here.
11. After the Site dropdown exists, open its property pane and set **Value** to **Site name** (the classic Dropdown uses the first column
    otherwise). Record the formula bar for any properties you change.
12. Name every control as in the files (`galInspections`, `camFinding`, ...). The tests refer to those names.

### D. Delegation, list, new inspection (needs tenant)

13. Select `galInspections` > Items. No blue underline. Temporarily replace `StartsWith` with `Search`: blue underline and delegation
    warning. Undo (Ctrl+Z). Record for `delegation-screen`. **Unverified in the build:** Studio's verdict on the lookup-GUID `Filter`
    inside `FindingCount`, on the Boolean `Resolved = false` in `OverdueFindingCount`, and on `CountRows` (a Learn example says
    `CountRows` was not delegated in one scenario). If Studio underlines any of them, show it, then fix: filter on a delegable
    column or accept the limit and say so.
14. Play the list screen in the phone preview. Record for `list-screen`: summary line, search "CWN", chip Draft.
15. New inspection > Canal Works North > Start. Record for `newinsp-screen`. The reference should be `CWN-01-<yyyymmdd>-AD-001`.
    The initials come from the inspector row's Full name: if the lab inspector row is named differently, the reference changes; say so.

### E. Phone: finding, responsive, offline (needs tenant, real phone)

16. Save and publish the app. On the phone open Power Apps > Contoso Inspections as **Alex Demo**.
17. `finding-screen`: Add finding, Major, empty details, show the message; add details; message changes; tap the camera; Save.
    **Unverified:** the Camera `Photo` property in `OnSelect`, the Dataverse image column accepting `{ Full: uri, Value: uri }`, and
    the 640 by 480 resolution cap (Learn). If the image column rejects the record, check the Patch error in Monitor.
18. `responsive-screen`: rotate the phone on the inspection screen: one column, then two.
19. Accessibility: Studio > App checker > Accessibility, fix or note anything flagged (`a11y-screen`). On the phone turn on TalkBack
    (Android) or VoiceOver (iOS) and swipe through the list. Do not show other apps' notifications.
20. Offline: Studio > Settings > General > Can be used offline > **New profile with current app data**; keep Inspection, Finding,
    Site, Inspector; add filters if the lab data is large; save and publish the profile, then save and publish the app (Learn: publish the
    app again after editing the profile). If "Can be used offline" is missing, the app is not in a solution.
    On the phone: open the app, wait for the first sync, airplane mode on, add a finding, show the globe with changes pending and the
    banner, airplane mode off. Record for `offline-screen`. **Unverified:** that the role's three system-table read privileges are enough.

### F. Monitor, solution, share (needs tenant)

21. Studio > Advanced tools > Open monitor; play the app; save a finding; show the Dataverse request and the duration. Then the
    published app: Apps > Contoso Inspections > Details > Live monitor > Play published app (mobile: "Copy monitor link" is a preview
    feature). Turn "Debug published app" off afterwards. Record for `monitor-screen`.
22. Solutions > ContosoInspections > Add existing > App > Canvas app (if it is not there). Select the app > Advanced > Add required
    objects (adds the offline profile). Export solution > Unmanaged. Unpack: `pac solution unpack --zipfile <zip> --folder unpacked`.
    Record for `solution-screen`. Keep the zip out of this folder.
23. Apps > Contoso Inspections > Share. Add Alex Demo and Sam Demo (individual Entra users; a Microsoft 365 group does not take a role).
    Data permissions > assign Contoso Inspector. Only a system administrator can assign the role. Record for `share-screen`.
24. Phone, as Alex Demo: new inspection > Add finding with photo > result Fail, summary, Submit. The chip goes to Submitted. Then Sam
    Demo: Alex's inspection is not in Sam's list. Record for `phone-screen`.

### G. Gotchas to say on camera (`gotcha` scene)

- Blue underline is the real delegation test; the lint in the tests only reads formulas.
- Camera is capped at 640 by 480; use Add picture for full size.
- UDFs reading variables: check in Studio. Dropdown Value: set by hand.

## Mapping: screen scene to what must be on screen

| Scene id | Image file | Product | What must be visible | Needs tenant |
|---|---|---|---|---|
| `tables-screen` | `screens/tables.jpg` | make.powerapps.com | Solution tables with cin_ prefix; Status choice; Photo image column | yes |
| `newapp-screen` | `screens/new-app.jpg` | Studio | New phone app in the solution; data added; Display settings; App > Formulas | yes |
| `delegation-screen` | `screens/delegation.jpg` | Studio | Items with no underline; Search version with blue underline | yes |
| `list-screen` | `screens/list.jpg` | Studio play | Summary, search, chips, rows | yes |
| `newinsp-screen` | `screens/new-inspection.jpg` | Studio play | Site pick, Start, new reference, Draft | yes |
| `finding-screen` | `screens/finding.jpg` | Phone | Messages in sequence, camera capture, Save | yes, phone |
| `responsive-screen` | `screens/responsive.jpg` | Phone | Portrait one column; landscape two panes | yes, phone |
| `a11y-screen` | `screens/accessibility.jpg` | Studio, phone | App checker accessibility tab; screen reader on the list | yes |
| `offline-screen` | `screens/offline.jpg` | Studio, phone | Offline profile; airplane mode banner and globe | yes, phone |
| `monitor-screen` | `screens/monitor.jpg` | Monitor | Events, Dataverse request, duration | yes |
| `solution-screen` | `screens/solution.jpg` | make.powerapps.com | Solution contents; Add required objects; Export | yes |
| `share-screen` | `screens/share.jpg` | make.powerapps.com | Share panel, role assignment | yes |
| `phone-screen` | `screens/phone.jpg` | Phone | Alex's list only; new inspection; Submitted; Sam does not see it | yes, phone |

The `code` and `bullets` scenes need no recording. Their code is copied from `src` and `tests`; the `provision`, `validate-test`,
`solution` and `responsive` scenes show terminal output you can reproduce with section A.

## Masking

- Mask the tenant name, environment URL and organization id in every screen, the address bar, and the admin center.
- Mask the real account names and UPNs of the lab users; show **Alex Demo** and **Sam Demo** display names only.
- Never show the access token, the `az login` code, or the Monitor session id.
- On the phone, hide notifications and other apps; do not show the device name or number.

## Tear-down

1. Delete the test inspections and findings (as the admin, or run a bulk delete), then the sample sites and inspectors if they will not
   be reused by episode 12.
2. Remove Alex Demo's and Sam Demo's share and the Contoso Inspector role assignment if the app is not kept.
3. Delete the offline profile (admin center > Mobile configuration) and the app, then the solution `ContosoInspections` only if no
   other build special needs it. All build specials share it.
4. `az logout`, `Remove-Item Env:DATAVERSE_ACCESS_TOKEN`, delete any exported zip.
5. Remove `bin`, `obj`, `.pytest_cache` and `__pycache__` from this folder.
