# DEVLADLOG Microsoft 365 #13 — Microsoft 365 Apps Deployment

**One JSON file, two ways to deploy.** [`src/apps.json`](src/apps.json) says what a Microsoft 365 Apps deployment looks like
(channel, architecture, products, languages, excluded apps, display, MSI removal). The module turns it into an **Office
Deployment Tool `configuration.xml`** (and runs `setup.exe` for you) and into an **Intune "Microsoft 365 Apps for Windows 10
and later" app** through Microsoft Graph, then checks what really got installed and who activated it. The demo installs
Microsoft 365 Apps on the **real Windows 11 VM** (`CON-W11-01`, from episode 7), so the screens show the product doing the
real thing.

1. **Config** — `Get-ADConfig` refuses channels, editions, `ExcludeApp` ids, languages and flags that Learn does not list.
2. **configuration.xml** — `New-ADOdtXml` (install or download mode) and `Test-ADOdtXml`, which checks *any* file (also
   hand-written ones) against the documented values: `Add`/`Updates` channel, `OfficeClientEdition`, `Version`,
   `DownloadPath` needs `Version`, `SourcePath` must not contain the `Office` folder, `Display`, `Property`, `ExcludeApp`.
3. **Install** — `Install-ADOffice`: validates, writes the file, runs `setup.exe /configure` (or `/download`), honours
   `-WhatIf`, fails on a non-zero exit code.
4. **Intune** — `ConvertTo-ADOfficeSuiteAppBody` + `Set-ADOfficeSuiteApp`: builds the `officeSuiteApp` body, finds the
   app by name, **creates it or patches only what differs**, assigns it to a group. Graph **beta** (see gotchas).
5. **Client check** — `Get-ADOfficeClient` (registry, Windows) + `Get-ADReleaseChannel` (Office release discovery API,
   no sign-in) + `Get-ADClientFinding`: `StoreInstallType`, `NotInstalled`, `ProductMissing`, `ArchitectureMismatch`,
   `ChannelMismatch`, `BuildBehind`, `BuildAhead`, `UnknownChannel`.
6. **Activation audit** — `Get-ADActivationReport` + `Get-ADActivationFinding` from Graph
   `getOffice365ActivationsUserDetail`: `DesktopAtLimit`, `StaleActivation`, `MobileOnly`, `SharedComputer`.

Same fictional tenant as episodes 1–12 (`contoso`); lab users `alex.demo`, `sam.demo`, `jordan.demo`, `riley.demo`,
`taylor.demo`. The activation rows, client registry values and update-channel names in the tests are fictional
(the channel list in `tests/fixtures/channels.json` is a trimmed copy of the real, public release discovery answer) and
**never** appear in the demo.

| Path | What it is |
|---|---|
| [`src/apps.json`](src/apps.json) | The deployment: channel, edition, products, languages, excluded apps; Intune app name and assignment (placeholder group id); audit thresholds |
| [`src/AppsDeploy/AppsDeploy.psm1`](src/AppsDeploy/AppsDeploy.psm1) | The module: validation, XML, install wrapper, Intune body/create/update/assign, release data, client and activation findings, markdown |
| [`src/AppsDeploy/AppsDeploy.psd1`](src/AppsDeploy/AppsDeploy.psd1) | Module manifest |
| [`src/Invoke-AppsDeploy.ps1`](src/Invoke-AppsDeploy.ps1) | Runner: `-BuildXml`, `-ValidateXml`, `-Install`, `-Inventory`, `-PublishIntune`, `-ActivationAudit` |
| [`tests/AppsDeploy.Tests.ps1`](tests/AppsDeploy.Tests.ps1) | 57 Pester tests (Graph mocked with a small fake tenant; the install wrapper runs a real process, a stub shell script standing in for `setup.exe`, Linux only) |
| [`tests/fixtures/`](tests/fixtures) | `channels.json` (trimmed real release data), `clients.json` and `activations.csv` (fictional) |
| [`sample/configuration.xml`](sample/configuration.xml) · [`sample/activation-audit.md`](sample/activation-audit.md) | Generated offline from the sample config and the fictional report |
| [`script.yaml`](script.yaml) · [`demo.md`](demo.md) | Draft video script and the shot list |

## Run the tests

```bash
cd series/microsoft-365/episodes/13-microsoft-365-apps-deployment
pwsh -NoProfile -Command 'Invoke-Pester ./tests'
# Tests Passed: 57, Failed: 0, Skipped: 0   (on Windows the 5 Install-ADOffice tests are skipped: they use a shell script as the stub)
```

Produced in this repo's container (PowerShell 7.6, Pester 6.2.0). PSScriptAnalyzer (Warning and Error) reports 0 issues on
`src/`. `Microsoft.Graph.Authentication` is not installed here: the tests use a stub with the documented parameter names
(`Invoke-MgGraphRequest`), so the real module's parameter binding was **not** checked in this episode.

## Run it

```powershell
cd src
# Offline (no tenant)
./Invoke-AppsDeploy.ps1 -BuildXml -OutFile ../sample/configuration.xml     # then -ValidateXml ../sample/configuration.xml
./Invoke-AppsDeploy.ps1 -ActivationAudit -ReportFile ../tests/fixtures/activations.csv -Now 2026-11-21T12:00:00Z

# Needs the Windows client (see demo.md): PowerShell 7.2+, local administrator, setup.exe from the Office Deployment Tool
./Invoke-AppsDeploy.ps1 -Inventory
./Invoke-AppsDeploy.ps1 -Install -OdtPath C:\ODT\setup.exe -WhatIf
./Invoke-AppsDeploy.ps1 -Install -OdtPath C:\ODT\setup.exe

# Needs tenant: copy apps.json to apps.lab.json and put the Entra group's object id in it
./Invoke-AppsDeploy.ps1 -ConfigFile ./apps.lab.json -PublishIntune -WhatIf   # Graph beta: DeviceManagementApps.ReadWrite.All
./Invoke-AppsDeploy.ps1 -ConfigFile ./apps.lab.json -PublishIntune
./Invoke-AppsDeploy.ps1 -ActivationAudit                                    # Graph v1.0: Reports.Read.All
```

## Licensing and permissions (Learn)

| Feature | Needs |
|---|---|
| Microsoft 365 Apps | A licence assigned to the user; one licence = up to **five** desktops, five tablets and five phones; the PC must reach the Office Licensing Service at least once every **30 days** |
| Shared computer activation | `SharedComputerLicensing` = 1; does not count against the activation limit |
| ODT install | Local administrator on the client; internet access to the Office CDN unless `SourcePath` has the files |
| Intune app (`officeSuiteApp`, `assign`) | An active Intune licence; `DeviceManagementApps.ReadWrite.All` (list: `.Read.All` is enough) |
| Activation report | `Reports.Read.All` and an Entra role that can read usage reports |
| Release discovery API | No permissions |

## What we learned / gotchas

- **The Intune API for this app is beta only.** Learn documents `officeSuiteApp` (list, create, update, delete) and
  `mobileApps/{id}/assign` for `graph-rest-beta`; the v1.0 pages say to check the version selector. The module therefore
  calls `/beta` and says so. Beta APIs can change.
- **Listing is not filtered.** Learn's list page documents `GET /deviceAppManagement/mobileApps` with no `$filter`, so
  `Get-ADOfficeSuiteApp` pages through all apps and keeps the `#microsoft.graph.officeSuiteApp` ones (test: finds the app on
  the second page).
- **Channel names differ between ODT and Graph.** ODT: `Current`, `CurrentPreview`, `MonthlyEnterprise`, `SemiAnnual`,
  `SemiAnnualPreview`, `BetaChannel`. Graph `officeUpdateChannel`: `current`, `firstReleaseCurrent`, `monthlyEnterprise`,
  `deferred`, `firstReleaseDeferred` (and `none`). The mapping comes from the `alternateNames` that the release discovery API
  publishes (`Deferred` for Semi-Annual, `FirstReleaseCurrent`, `FirstReleaseDeferred`); a test checks it against the real data.
  There is no Graph value for Beta Channel, so that is refused for Intune.
- **Intune and ODT accept different things.** Intune: four product ids (`o365ProPlusRetail`, `o365BusinessRetail`,
  `visioProRetail`, `projectProRetail`), culture codes only (no `MatchOS`), and `excludedApps` booleans (no
  `OutlookForWindows`). ODT: any supported product id, the `Match*` language keywords, 12 `ExcludeApp` ids, with
  `Groove` meaning OneDrive and `Lync` meaning Skype for Business.
- **`officeConfigurationXml` takes precedence.** Learn: "Takes precedence over all other properties". The module deliberately
  sends the individual properties, so the portal shows them; use the XML property only if you need ODT-only options.
- **Which version key to trust.** Microsoft's guidance: use `HKLM\SOFTWARE\Microsoft\Office\ClickToRun\Inventory\Office\16.0`
  (`OfficePackageVersion`, `OfficeProductReleaseIds`), not `Configuration\VersionToReport`, which is internal telemetry and can
  differ from what is installed. The channel comes from `Configuration\CDNBaseUrl` / `UpdateChannel`; the GUID at the end of
  the URL is matched against the release discovery data. `UpdateChannel` is dynamic and updates only when the *Office
  Automatic Updates 2.0* task runs or a user signs in, so after a channel change it can lag a day or more (Learn, Intune settings catalog).
- **Policy precedence for the channel.** Cloud Update, Group Policy/Intune policy and the ODT `UpdateUrl` all write the
  channel; Learn lists the order (Cloud Update first, ODT fifth). With the Intune app made in the Configuration designer and
  assigned as required, Intune re-enforces the app's channel at every policy refresh, so a settings catalog channel policy that
  disagrees can make devices switch back and forth. Keep them equal.
- **Channel unification (July 2026).** Learn: beginning with Version 2606, Semi-Annual Enterprise Channel devices get the
  Monthly Enterprise updates and show as Monthly Enterprise in the apps, while some tools keep the old name; builds above
  20131.20000 have 2606. The client check mentions this on a `SemiAnnual` vs `MonthlyEnterprise` mismatch. Cloud Update takes
  precedence over other tools and onboards eligible devices automatically after 2606.
- **`Version` and `Channel` go together.** Learn: with `Version`, include `Channel` (required for `MatchInstalled`);
  `DownloadPath` requires a `Version`; `SourcePath` must not include the `Office` folder. The validator checks all three.
- **ExcludeApp merging.** Learn: on a device that already has Microsoft 365 Apps, the `ExcludeApp` list replaces the old one only
  if the file lists all installed languages; otherwise they are combined. Not covered by a test (needs a device).
- **Store installation type.** Learn: feature updates stopped in October 2025, security updates end in December 2026; installs through
  the ODT, Intune or Configuration Manager detect and remove it; the check is `Get-AppxPackage -Name Microsoft.Office.Desktop`.
- **Windows 10.** Learn: Windows 10 support ended 14 Oct 2025; Microsoft 365 Apps security updates continue until 10 Oct 2028, feature
  updates until Version 2608. Not part of the code; mentioned only as planning context.
- **Activation report shape.** The columns come from Learn (`Report Refresh Date`, `User Principal Name`, `Display Name`, `Product Type`,
  `Last Activated Date`, `Windows`, `Mac`, `Windows 10 Mobile`, `iOS`, `Android`, `Activated On Shared Computer`). Learn does not
  show sample rows, so that Windows/Mac/mobile cells are counts and the shared column is `Yes`/`No` is **our assumption** (the parser
  accepts `Yes`/`True`/`1`); the report's refresh delay is not documented. Also: a user over 10 devices has the least recently used one
  deactivated automatically (Windows only, Learn).
- **Process exit code.** `setup.exe` prints "Products configured successfully" on success (Learn); the wrapper trusts the exit code and tells
  you to read the logs in `%temp%` on failure.
- **Not verified here (needs tenant/VM, see [demo.md](demo.md))**: that Graph accepts the `excludedApps` object with all 15 booleans and an
  `assign` body with only `intent` and `target`; that a second `-PublishIntune` reports `Unchanged` (depends on Graph echoing our values);
  what the real PC registry shows for each key; the activation report's real cell values; PowerShell 7 availability on the VM image.

Not covered (to keep the episode to 6 minutes): Configuration Manager, Cloud Update and the Microsoft 365 Apps admin center, the
Office Customization Tool, languages and proofing tools, shared computer activation and VDI, application preferences (`AppSettings`),
macOS, Visio/Project side by side, update rings and deadlines, offline sources and `/download` at scale (the code supports
`-Mode Download`, not demonstrated).

## References

- [Overview of the Office Deployment Tool](https://learn.microsoft.com/microsoft-365-apps/deploy/overview-office-deployment-tool) · [Configuration options for the ODT](https://learn.microsoft.com/microsoft-365-apps/deploy/office-deployment-tool-configuration-options)
- [Overview of update channels](https://learn.microsoft.com/microsoft-365-apps/updates/overview-update-channels) · [Change the update channel (policy precedence)](https://learn.microsoft.com/microsoft-365-apps/updates/change-update-channels) · [Channel unification: Semi-Annual to Monthly Enterprise](https://learn.microsoft.com/microsoft-365-apps/updates/unified-update-channels)
- [Determining the installed version (Click-to-Run Inventory key)](https://learn.microsoft.com/microsoft-365-apps/updates/microsoft-guidance-on-office-build-install) · [Intune settings catalog: check the Office registry keys](https://learn.microsoft.com/intune/device-configuration/settings-catalog/update-office#check-the-office-registry-keys) · [Release discovery API](https://learn.microsoft.com/office/client-developer/shared/manageability-applications-with-the-office-365-click-to-run-installer#automating-content-staging)
- [officeSuiteApp resource (beta)](https://learn.microsoft.com/graph/api/resources/intune-apps-officesuiteapp?view=graph-rest-beta) · [create](https://learn.microsoft.com/graph/api/intune-apps-officesuiteapp-create?view=graph-rest-beta) · [update](https://learn.microsoft.com/graph/api/intune-apps-officesuiteapp-update?view=graph-rest-beta) · [list](https://learn.microsoft.com/graph/api/intune-apps-officesuiteapp-list?view=graph-rest-beta) · [officeUpdateChannel](https://learn.microsoft.com/graph/api/resources/intune-apps-officeupdatechannel?view=graph-rest-beta) · [mobileApp assign](https://learn.microsoft.com/graph/api/intune-apps-mobileapp-assign?view=graph-rest-beta)
- [getOffice365ActivationsUserDetail](https://learn.microsoft.com/graph/api/reportroot-getoffice365activationsuserdetail?view=graph-rest-1.0)
- [Licensing and activation in Microsoft 365 Apps](https://learn.microsoft.com/microsoft-365-apps/licensing-activation/overview-licensing-activation-microsoft-365-apps) · [Shared computer activation](https://learn.microsoft.com/microsoft-365-apps/licensing-activation/overview-shared-computer-activation)
- [Microsoft Store installation type end of support](https://learn.microsoft.com/microsoft-365-apps/end-of-support/microsoft-store-install-type-support) · [Windows 10 end of support and Microsoft 365 Apps](https://learn.microsoft.com/microsoft-365-apps/end-of-support/windows-10-support) · [32-bit Arm end of support](https://learn.microsoft.com/microsoft-365-apps/end-of-support/end-of-support-32bit-arm)
- Blog: [Microsoft 365 Apps Deployment — Complete Guide](https://www.devladlog.com/articles/office-365/2025-03-05-apps-deployment-complete-guide-2025/)
