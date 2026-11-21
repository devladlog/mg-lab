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

1. `cd tests/python && python3 -m pytest -q` (37 passed), `cd tests/pester && pwsh -NoProfile -Command "Invoke-Pester -Path ./Provision.Tests.ps1"` (19 passed),
   `cd tests/ContosoInspections.Canvas.Tests && dotnet test -m:1` (126 passed). Delete `bin`, `obj` and caches afterwards.
   The schema must still equal episode 12's (the tests check it): if episode 12 changes its schema, copy the file over this one first.
2. `pwsh -File src/scripts/Provision-ContosoInspections.ps1 -EnvironmentUrl https://contoso.crm.dynamics.com -PlanOnly`: shows the plan.
   Show this in the terminal for the `provision` scene.

### B. Create the schema (needs tenant)

3. Sign in as the lab administrator: `az login` (recorder only). Get a token for the DEV environment URL:
   `$env:DATAVERSE_ACCESS_TOKEN = (az account get-access-token --resource <DEV url> --query accessToken -o tsv)`. Do not show the token or the URL.
4. Run `src/scripts/Provision-ContosoInspections.ps1 -EnvironmentUrl <DEV url> -SeedData -AlexEmail <Alex UPN> -SamEmail <Sam UPN>`.
   Expected: publisher, solution, 4 tables, 21 columns, 3 relationships (each adds its lookup), the site-code alternate key, the
   Inspection Field Inspector role, 3 sites, 2 inspectors, then publish. Run it a second time: nothing is created twice.
   If episode 12 was already set up in this environment (its solution imported or its tables built by hand), run this script
   anyway: it skips what exists, and the sample sites share episode 12's codes, so nothing is duplicated. Check that Inspection item
   has the Photo column; if episode 12's tables came first without it, the script adds it.
5. make.powerapps.com > Solutions > ContosoInspections > Tables. Open Inspection > Columns and Inspection item > Columns. Record for `tables-screen`.
6. Assign the Inspection Field Inspector role to Alex Demo and Sam Demo (Admin center > Environment > Users > Manage security roles).
   The role has not been created by this builder against a tenant, so check its 17 privileges on the role page.
   **Unverified:** the privilege names for the system tables (canvas app, mobile offline profile, sync error) and adding the role to the
   solution by component type 20. If the script reports an error here, create or fix the role in the UI, and note it in the video.

### C. Build the app in Studio (needs tenant)

7. Solutions > ContosoInspections > New > App > Canvas app > Phone. Name it `Contoso Inspections`. Record for `newapp-screen`.
8. Add data: Dataverse > Inspections, Inspection items, Sites, Inspectors.
9. Settings > Display: Scale to fit **off**, Lock aspect ratio **off**, Lock orientation **off**. Settings > Updates: Data row limit 500.
10. Paste the source from `src/app/Src`. Two ways: (a) coauthoring + the canvas authoring MCP server (Learn: "Create and edit canvas apps
    with AI code generation tools"), or (b) create the screens and controls by hand and paste each Power Fx property. **Unverified:** that
    Studio accepts every control type name in these files (`Camera`, `Classic/Dropdown`, `Classic/Icon`, `GroupContainer` with
    `Variant: AutoLayout`) and the `Formulas` property with the UDFs. Fix any file Studio rejects and say so on screen.
    `pac canvas pack` cannot build an msapp from these files offline in a way proven here.
11. After the Site dropdown exists, open its property pane and set **Value** to **Site name** (the classic Dropdown uses the first column
    otherwise). Record the formula bar for any properties you change.
12. Name every control as in the files (`galInspections`, `camItem`, ...). The tests refer to those names.
    **Check the Status column first.** The custom Status (`cin_status`) and the system Status (`statecode`) share a display name. In
    the formula bar of `galInspections` > Items, type `cin_status` and `'Status (Inspections)'.`: IntelliSense must offer Draft,
    In progress, Submitted, Approved, Rejected. If Studio names the choice differently, replace that one pattern in
    `App.pa.yaml` and `InspectionsScreen.pa.yaml` and say so in the video (this is the `gotcha` scene).

### D. Delegation, list, new inspection (needs tenant)

13. Select `galInspections` > Items. No blue underline. Temporarily replace `StartsWith` with `Search`: blue underline and delegation
    warning. Undo (Ctrl+Z). Record for `delegation-screen`. **Unverified in the build:** Studio's verdict on the lookup-GUID `Filter`
    inside `ItemCount`, `FailedCount` and the items gallery, on the Boolean `Passed = false` with `IsBlank` in `UnresolvedItemCount`, and on `CountRows` (a Learn example says
    `CountRows` was not delegated in one scenario). If Studio underlines any of them, show it, then fix: filter on a delegable
    column or accept the limit and say so.
14. Play the list screen in the phone preview. Record for `list-screen`: summary line, search "INS-0000", chip In progress. The list
    is empty on a fresh environment: create two or three inspections as Alex Demo first (rows from episode 12's sample CSVs belong to
    whoever imported them, so Alex does not see those under Basic scope).
15. New inspection > Harbor Warehouse > Start. Record for `newinsp-screen`. The status is Draft; the inspection number (`INS-000xx`)
    is assigned by Dataverse. **Unverified:** whether the detail screen already shows it right after Start (the title says "New
    inspection" until the number is on the row; go back to the list if so).
15a. Open the new inspection: Submit is disabled while it is a Draft. Add one item (step 17): the status becomes In progress, the
    suggested score line appears, Submit is enabled.

### E. Phone: item, responsive, offline (needs tenant, real phone)

16. Save and publish the app. On the phone open Power Apps > Contoso Inspections as **Alex Demo**.
17. `item-screen`: Add item, name "Fire door", Major, Passed switched off, empty notes, show the message; add notes; message changes; tap the
    camera; Save. Also try Critical with Passed on: "A critical item cannot be marked as passed." (the same rule episode 12 enforces on
    the server).
    **Unverified:** the Camera `Photo` property in `OnSelect`, the Dataverse image column accepting `{ Full: uri, Value: uri }`, and
    the 640 by 480 resolution cap (Learn). If the image column rejects the record, check the Patch error in Monitor.
    Also unverified: the Draft to In progress `Patch` on the inspection right after the first item.
18. `responsive-screen`: rotate the phone on the inspection screen: one column, then two.
19. Accessibility: Studio > App checker > Accessibility, fix or note anything flagged (`a11y-screen`). On the phone turn on TalkBack
    (Android) or VoiceOver (iOS) and swipe through the list. Do not show other apps' notifications.
20. Offline: Studio > Settings > General > Can be used offline > **New profile with current app data**; keep Inspection, Inspection item,
    Site, Inspector; add filters if the lab data is large; save and publish the profile, then save and publish the app (Learn: publish the
    app again after editing the profile). If "Can be used offline" is missing, the app is not in a solution.
    On the phone: open the app, wait for the first sync, airplane mode on, add an item, show the globe with changes pending and the
    banner, airplane mode off. Record for `offline-screen`. **Unverified:** that the role's three system-table read privileges are enough, and what an inspection created offline shows
    as its number before it syncs (the screens say "New inspection").

### F. Monitor, solution, share (needs tenant)

21. Studio > Advanced tools > Open monitor; play the app; save an item; show the Dataverse request and the duration. Then the
    published app: Apps > Contoso Inspections > Details > Live monitor > Play published app (mobile: "Copy monitor link" is a preview
    feature). Turn "Debug published app" off afterwards. Record for `monitor-screen`.
22. Solutions > ContosoInspections > Add existing > App > Canvas app (if it is not there). Select the app > Advanced > Add required
    objects (adds the offline profile). Export solution > Unmanaged. Unpack: `pac solution unpack --zipfile <zip> --folder unpacked`.
    Record for `solution-screen`. Keep the zip out of this folder.
23. Apps > Contoso Inspections > Share. Add Alex Demo and Sam Demo (individual Entra users; a Microsoft 365 group does not take a role).
    Data permissions > assign Inspection Field Inspector. Only a system administrator can assign the role. Record for `share-screen`.
24. Phone, as Alex Demo: new inspection > Add item with a photo > score, summary, follow-up on > Submit. The row moves to Submitted and the
    screen says "Waiting for the back office to review it." Then Sam Demo: Alex's inspection is not in Sam's list. Record for `phone-screen`.
25. Bridge to episode 12 (needs its model-driven app): as the reviewer, open Alex's inspection in the Inspection Back Office app and
    set the status to Approved. On Alex's phone pull to refresh: the row reads "✓ Approved", the screen is read-only and the banner says
    "Approved by the back office." Repeat with Rejected to show "✕ Rejected". Skip this step if episode 12 is not built yet and say in
    the video that the next episode does it.

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
| `newinsp-screen` | `screens/new-inspection.jpg` | Studio play | Site pick, Start, Draft (number assigned by Dataverse) | yes |
| `item-screen` | `screens/item.jpg` | Phone | Messages in sequence, camera capture, Save; Draft becomes In progress | yes, phone |
| `responsive-screen` | `screens/responsive.jpg` | Phone | Portrait one column; landscape two panes | yes, phone |
| `a11y-screen` | `screens/accessibility.jpg` | Studio, phone | App checker accessibility tab; screen reader on the list | yes |
| `offline-screen` | `screens/offline.jpg` | Studio, phone | Offline profile; airplane mode banner and globe | yes, phone |
| `monitor-screen` | `screens/monitor.jpg` | Monitor | Events, Dataverse request, duration | yes |
| `solution-screen` | `screens/solution.jpg` | make.powerapps.com | Solution contents; Add required objects; Export | yes |
| `share-screen` | `screens/share.jpg` | make.powerapps.com | Share panel, role assignment | yes |
| `phone-screen` | `screens/phone.jpg` | Phone | Alex's list only; Submitted with the waiting banner; Sam does not see it; optional Approved banner | yes, phone |

The `code` and `bullets` scenes need no recording. Their code is copied from `src` and `tests`; the `provision`, `validate-test`,
`solution` and `responsive` scenes show terminal output you can reproduce with section A.

## Masking

- Mask the tenant name, environment URL and organization id in every screen, the address bar, and the admin center.
- Mask the real account names and UPNs of the lab users; show **Alex Demo** and **Sam Demo** display names only.
- Never show the access token, the `az login` code, or the Monitor session id.
- On the phone, hide notifications and other apps; do not show the device name or number.

## Tear-down

1. Delete the test inspections and items (as the admin, or run a bulk delete), then the sample sites and inspectors if they will not
   be reused by episode 12.
2. Remove Alex Demo's and Sam Demo's share and the Inspection Field Inspector role assignment if the app is not kept.
3. Delete the offline profile (admin center > Mobile configuration) and the app, then the solution `ContosoInspections` only if no
   other build special needs it. All build specials share it.
4. `az logout`, `Remove-Item Env:DATAVERSE_ACCESS_TOKEN`, delete any exported zip.
5. Remove `bin`, `obj`, `.pytest_cache` and `__pycache__` from this folder.
