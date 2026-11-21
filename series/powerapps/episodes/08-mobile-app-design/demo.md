# Demo shot list — DEVLADLOG Power Apps #8, Mobile app design

The screen and app formulas were tested locally (`dotnet test`: 112 passed) at several screen sizes, online and offline,
with simulated scans. Everything below **needs the lab tenant and a real phone** and has not been run: Studio accepting the
source, offline-first sync, the native barcode scanner, rotation on a device.

## Lab environment
No VM and no Azure resource.

| What | Notes | Cost |
|---|---|---|
| Lab **DEV** environment with episodes 1-7: solution **Equipment Desk** (tables, model-driven app, flow from ep. 6), the **Equipment Desk Kit** library (ep. 7) and **Equipment Desk (phone)** with episode 7's Open loans screen | the canvas app **must be in the solution** (Learn: otherwise "Can be used offline" doesn't show) | existing |
| Recording user `labadmin` (System Administrator in DEV, Power Apps Premium) | System Administrator/Customizer/Environment Maker can set up offline (Learn) | existing |
| Optional second user `alex.demo` on the phone | Learn: users with only **Basic User** can't open an offline app; create a role **Equipment Desk Offline** with Read on **Canvas App**, **Mobile offline profile** and **Sync Error** (plus Read/Write on Loan and Equipment) and assign it for the demo | free |
| **A real phone** (Android or iOS) with the **Power Apps** mobile app from the store, signed in to the lab tenant | barcode reader and offline only work in Power Apps mobile (Learn: browsers can't run offline; the barcode reader isn't supported in desktop browsers). Recorded with the phone's own screen recorder, **not an emulator** | existing device |
| Printed (or second-screen) barcodes: **Code 128** labels with the text `CT-0043`, `CT-0107`, `CT-0042`, and any retail product's **EAN** barcode | generate the Code 128 labels with any label printer or barcode generator off camera | free |
| Lab Windows host, Microsoft Edge | for `wide-screen`: browser **device emulation** (DevTools device toolbar) and a full desktop window | existing |

Screens: `rotate-screen`, `offline-screen`, `scan-screen` on the **real phone (Power Apps mobile)**; `wide-screen` in **Edge on the
lab laptop with device emulation**. Say which on screen (the `bar` text in `script.yaml` already does).

## Things to confirm in the lab (fix code/tests/README if they differ)
- Control type names Studio writes for the containers (`GroupContainer` + `Variant: AutoLayout`) and the barcode reader
  (`BarcodeReader`), and the container property names `LayoutDirection`, `LayoutGap`, `FillPortions`, `LayoutMinWidth`
  (Learn names `LayoutDirection` and `LayoutAlignItems`; the others weren't checked).
- `Live.Polite` as the label's Live value; `Icon.Globe...` names, `ConnectionSync.*`, `Host.OfflineEnabled`,
  `ShowHostInfo(HostInfo.OfflineSync)` exactly as in Learn's offline template.
- The screen's **default** Width/Height formulas in this app (Learn shows both `Max(App.Height, App.MinScreenHeight)` and
  `Max(App.Height, App.DesignHeight)`); we replace them anyway with Learn's orientation formulas.
- A debug label `App.Width & " x " & App.Height & " size " & LoansScreen.Size` (add, record off camera, delete) on the phone
  upright and sideways, and in Edge: note the real values in the README; the tests use example widths.
- `FindLoan` (a behavior UDF with `LookUp` on Loans and `Set`) is accepted in App.Formulas, and the lookup filter
  `Equipment.'Asset tag' = tag` works offline (Learn: one-level lookup filters are supported offline).

## Steps
1. Tables (make.powerapps.com > Tables): **Equipment** and **Loan** > Edit table properties > Advanced options >
   **Can be taken offline** > Save.
2. Studio, Equipment Desk (phone): **Settings > Display**: Scale to fit **off**, Lock aspect ratio **off**, Lock orientation **off**.
   **App**: set `SizeBreakpoints`, `MinScreenWidth`, `MinScreenHeight` and replace **App > Formulas** from `src/app/Src/App.pa.yaml`.
3. Rebuild **LoansScreen** from `src/app/Src/LoansScreen.pa.yaml`: screen Width/Height formulas; `hdrLoans` (width leaves room for
   `icoSync`), `icoSync`, `lblOffline`; horizontal container `conBody` with vertical containers `conList` and `conDetail`; move the
   two buttons from the gallery rows to `conDetail`; insert **Barcode reader** `bcrScan` and text input `txtFindTag` in `conFind`.
   App checker: no errors. Save, publish.
4. **Settings > General > Can be used offline** on, profile **New profile with current app data**: Loan (rows: Organization rows /
   user's rows, or All rows for the small lab table) and Equipment (related rows via the Loan lookup). Save and **publish the
   profile**, then publish the app (Learn: after editing a profile, republish the apps that use it).
5. Test data: CT-0043 overdue for `alex.demo@contoso.com`, CT-0107 due soon, CT-0108 later, CT-0042 returned (episode 3 rows).
6. Phone: open Power Apps mobile, open the app, wait for the **initial offline sync** message to finish. Start the screen recorder.
7. `rotate-screen`: upright list → tap CT-0043 → loan full screen, header "CT-0043" → back arrow → list → open CT-0107 → rotate.
8. `offline-screen`: airplane mode on → banner + globe not connected → open CT-0043 → Send reminder disabled "(needs a
   connection)" → Mark returned → confirm → success banner, globe "changes pending" → tap globe (device status page) → airplane
   mode off → globe connected. On the laptop: model-driven app shows CT-0043 **Available**.
9. Reset CT-0043 (Returned on cleared, status On loan) on the laptop, wait for sync (Learn: every 5 minutes online, or reopen).
10. `scan-screen`: Scan tag → Code 128 `CT-0043` → loan opens; EAN product code → warning; `CT-0042` → "has no open loan";
    type `ct-0107` → opens.
11. `wide-screen`: Edge on the laptop, Play the app; DevTools device toolbar with a tablet-sized viewport upright and sideways,
    then the full window: two panes, "Select a loan to see it here.", no globe icon.
12. `pac canvas download --name "Equipment Desk (phone)" -d <dir>`; copy `Src/App.pa.yaml` and `Src/LoansScreen.pa.yaml` over
    `src/app/Src`, re-run `dotnet test`, fix the tests where Studio wrote something different and note it in the README.
13. Optional terminal capture for `tests`: `dotnet test EquipmentDesk.Mobile.Tests -m:1` (112 passed).

## Screens to capture (match `screen` scenes in script.yaml)
| Scene | File | Recorded on | What must be on screen |
|---|---|---|---|
| `rotate-screen` | `screens/phone-rotate.jpg` | phone, Power Apps mobile | list upright; CT-0043 full screen with header "CT-0043"; back to list; CT-0107 + rotation = two panes, no scroll |
| `offline-screen` | `screens/phone-offline.jpg` | phone, Power Apps mobile (+ laptop for the model-driven check) | yellow offline banner; globe states; disabled "Send reminder (needs a connection)"; Mark returned offline; changes pending → connected; CT-0043 Available |
| `scan-screen` | `screens/phone-scan.jpg` | phone, Power Apps mobile | native scanner on the Code 128 label; loan opens; EAN warning; "CT-0042 has no open loan"; typed tag works |
| `wide-screen` | `screens/browser-wide.jpg` | Edge on the lab laptop, device emulation | tablet-size upright/sideways and desktop: two panes, "Select a loan...", no globe icon |

## Masking
- Phone: account name/avatar in Power Apps mobile, notification bar contents (turn on Do Not Disturb), tenant name on the app list.
- Laptop: environment name and URL, tenant, user names, the maker portal account menu.
- Borrowers on screen are fictional `*.demo@contoso.com`; mask the real lab mail domain anywhere it appears.
- `pipeline/mask.js` in the browser; `series_label: "POWER APPS"` is set in `script.yaml`.

## Tear-down
1. Reset the test loans; airplane mode off; stop the phone recorder and delete raw recordings after export.
2. Keep offline on if episode 9 (ALM) moves the app; Learn: export the offline profile with the solution (**Advanced > Add required
   objects**). Otherwise turn **Can be used offline** off and delete the profile.
3. Remove the **Equipment Desk Offline** role assignment from `alex.demo` (and delete the role) if created; sign the phone out of
   the lab tenant if it isn't a lab device.
