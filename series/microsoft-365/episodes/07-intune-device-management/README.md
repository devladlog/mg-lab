# DEVLADLOG Microsoft 365 #7 — Intune & Device Management

**A Windows compliance policy as code, and an audit of the devices it should cover.** One file
([`src/intune.json`](src/intune.json)) says what a compliant Windows 11 device is and what happens when one isn't; the
module makes the tenant match it through Microsoft Graph, then audits every managed device for what the dashboard tends
to hide. The demo enrolls a **real Windows 11 VM** (`CON-W11-01`, Microsoft Entra joined as a lab user), so the screens
show the product doing the real thing.

1. **Policy** — `Set-IntuneCompliancePolicy`: builds a `windows10CompliancePolicy` body (BitLocker, Secure Boot, code
   integrity, storage encryption, password rules, minimum OS build) plus its actions for noncompliance, finds the policy
   by name, and **creates it or patches only what differs**. Settings go through `PATCH`; actions have their own
   endpoint (`scheduleActionsForRules`); assignment goes through `assign`. Every write honours `-WhatIf`.
2. **Validation before any call** — `Get-IntuneConfig` refuses settings that aren't `windows10CompliancePolicy`
   properties, wrong types, an OS version that isn't `major.minor.build.revision`, a grace period outside 0–8760 hours,
   zero or two `block` actions (Learn: one and only one), a `wipe` action, and a placeholder group id.
3. **Audit** — `Get-IntuneManagedDevice` (paged) + `Get-IntuneDeviceFinding` + `Get-IntuneComplianceSummary`:
   `NonCompliant`, `InGracePeriod`, `StaleCheckIn`, `NeverSynced`, `NotEncrypted`, `OsBelowMinimum`, `NoPrimaryUser`,
   `PersonalOwned`, `DuplicateSerial`; thresholds come from the config.
4. **Sync** — `Invoke-IntuneDeviceSync`: `POST managedDevices/{id}/syncDevice`.

Same fictional tenant as episodes 1–6 (`contoso`); lab users `alex.demo`, `sam.demo`, `jordan.demo`, `riley.demo`,
`taylor.demo`. The device list in the tests is fictional and **never** appears in the demo.

| Path | What it is |
|---|---|
| [`src/intune.json`](src/intune.json) | The policy: settings, one `block` action with a 24 h grace period, assignment (placeholder group id), audit thresholds |
| [`src/IntuneDevices/IntuneDevices.psm1`](src/IntuneDevices/IntuneDevices.psm1) | The module: config validation, request bodies, policy create/update/assign, device paging, findings, markdown, device sync |
| [`src/IntuneDevices/IntuneDevices.psd1`](src/IntuneDevices/IntuneDevices.psd1) | Module manifest |
| [`src/Invoke-IntuneDevices.ps1`](src/Invoke-IntuneDevices.ps1) | Runner: `-ApplyPolicy [-WhatIf]`, `-Audit` (live or `-DevicesFile`), `-SaveDevices`, `-SyncDeviceName`, `-OutFile`, `-Now` |
| [`tests/IntuneDevices.Tests.ps1`](tests/IntuneDevices.Tests.ps1) | 58 Pester tests (Graph mocked with a small fake tenant; one test checks our calls against the real Microsoft.Graph.Authentication module) |
| [`tests/fixtures/devices.json`](tests/fixtures/devices.json) | Fictional managed devices: noncompliant, unencrypted, old OS, stale, never synced, grace period, userless, BYOD, duplicate serial, one macOS |
| [`sample/intune-audit.md`](sample/intune-audit.md) | Audit of the fictional fixture, generated offline |
| [`script.yaml`](script.yaml) · [`demo.md`](demo.md) | Draft video script and the shot list (with the new VM `CON-W11-01`, also in `series/LAB-REQUESTS.md`) |

## Run the tests

```bash
cd series/microsoft-365/episodes/07-intune-device-management
pwsh -NoProfile -Command 'Invoke-Pester ./tests'
# Without the real Graph module:  Tests Passed: 57, Failed: 0, Skipped: 1
# With Microsoft.Graph.Authentication installed (it adds the "real module parameters" test):
#                                 Tests Passed: 58, Failed: 0, Skipped: 0
```

Both results were produced in this repo's container (PowerShell 7.6, Pester 6.2.0; Microsoft.Graph.Authentication
2.41.2 saved to a temp folder on `PSModulePath`). PSScriptAnalyzer (Warning and Error) reports 0 issues on `src/`.

## Run it

```powershell
cd src
# Offline (no tenant): audit the fictional device list
./Invoke-IntuneDevices.ps1 -Audit -DevicesFile ../tests/fixtures/devices.json -Now 2026-11-21T12:00:00Z -OutFile ../sample/intune-audit.md
#   -> 9 Windows devices, 10 findings: 2 High / 5 Medium / 3 Low (the macOS record is ignored)

# Needs tenant (see demo.md): copy intune.json to intune.lab.json and put the Entra group's object id in it
./Invoke-IntuneDevices.ps1 -PolicyFile ./intune.lab.json -ApplyPolicy -WhatIf   # Graph: DeviceManagementConfiguration.ReadWrite.All
./Invoke-IntuneDevices.ps1 -PolicyFile ./intune.lab.json -ApplyPolicy
./Invoke-IntuneDevices.ps1 -PolicyFile ./intune.lab.json -Audit                 # Graph: DeviceManagementManagedDevices.Read.All
./Invoke-IntuneDevices.ps1 -PolicyFile ./intune.lab.json -SyncDeviceName CON-W11-01   # …PrivilegedOperations.All
```

## Licensing and permissions (Learn)

| Feature | Needs |
|---|---|
| Intune and the Graph API for Intune | An active Intune licence in the tenant; Intune is included in Microsoft 365 E3, E5 and E7 |
| Enforcing compliance (Conditional Access) | Intune plus Microsoft Entra ID P1 or P2 (included in E5) |
| Windows automatic enrollment | Microsoft Entra ID Premium; **MDM user scope** Some or All |
| Create/update policy, `assign`, `scheduleActionsForRules` | `DeviceManagementConfiguration.ReadWrite.All` |
| List `managedDevices` | `DeviceManagementManagedDevices.Read.All` |
| `syncDevice` | `DeviceManagementManagedDevices.PrivilegedOperations.All` |
| Windows 11 VM | Hyper-V generation 2, ≥ 4 GB, ≥ 64 GB, ≥ 2 vCPU, Secure Boot capable, virtual TPM |

## What we learned / gotchas

- **`PATCH` can't change the actions.** The documented update of `windows10CompliancePolicy` takes only the policy's
  own properties; actions for noncompliance are `scheduledActionsForRule` / `deviceComplianceActionItem`, changed with
  the `scheduleActionsForRules` action. `Set-IntuneCompliancePolicy` compares settings, actions and assignments
  separately and calls only the endpoint that owns each difference (tests: *patches only the settings that differ*,
  *uses scheduleActionsForRules for a changed grace period*).
- **Exactly one `block` action.** Learn: "Compliance policy must have one and only one block scheduled action"; the
  portal's default *Mark device noncompliant* action can't be removed, only rescheduled. Learn doesn't spell out that
  Graph's `block` is that action — our reading, to be confirmed on the first run (demo.md, screen 2).
- **`ruleName` is always `PasswordRequired`** ("scheduled actions are created per policy instead of per rule").
- **Grace period units.** Graph takes `gracePeriodHours` (0–8760); the portal shows days (0 to 365) and accepts
  quarter-day steps. The config uses hours, like Graph.
- **Device-health settings are measured, not read.** *Require BitLocker* is evaluated by Device Health Attestation and
  "only measured at boot": encryption can finish and the device stays noncompliant until a restart. *Secure Boot* shows
  Not compliant on devices without a supported TPM. On Windows 11 the health settings use Azure attestation endpoints:
  a firewall blocking them makes devices with BitLocker/Secure Boot/Code integrity rules noncompliant. *Encryption of
  data storage* (`storageRequireEncryption`) is the simpler OS-drive check; we use both and the audit also reads
  `isEncrypted`.
- **No policy = compliant.** The tenant setting *Mark devices with no compliance policy assigned as* defaults to
  Compliant; Microsoft recommends Not compliant when you use Conditional Access, and the *Devices without compliance
  policy* report lists the gap. It isn't a per-policy setting, so this episode only shows it (optional capture).
- **`$filter` isn't documented for every property.** Learn lists `$filter` for `complianceState`, `lastSyncDateTime`,
  `enrolledDateTime` and a few more, not `operatingSystem`: `Get-IntuneManagedDevice` pages everything with `$select`
  and filters client-side.
- **Cleanup rules hide, they don't remove.** 30–270 days without check-in; no wipe or retire; a hidden device that
  checks in before its certificate expires reappears; Entra device objects are separate. The audit's stale limit
  (default 30) is a reporting threshold, not a cleanup rule.
- **Enrollment restrictions and join:** if restrictions block personal Windows devices, the join-and-enroll flow from
  OOBE doesn't complete; the Entra device limit (default 50) applies to joined and registered devices.
- **`Format-Table` prints nothing without a console** (CI, redirected output: width 0). The runner pipes through
  `Out-String -Width` so its tables show everywhere.
- Not verified here (needs tenant, see [demo.md](demo.md)): that Graph accepts `scheduledActionsForRule` in the create
  body and a `block` action without `notificationTemplateId`; the exact property names and casing of `deviceCompliancePolicies`
  responses beyond Learn's samples; what the VM really reports for BitLocker, Secure Boot and code integrity; how long
  the attestation-based settings take to turn compliant; whether `assign` replaces the full list (the module always sends
  the full desired list, and compares first).

Not covered (to keep the episode to 6 minutes): Autopilot, configuration profiles and the settings catalog, app
deployment, Windows Update rings and Autopatch, Conditional Access, device cleanup rules as code, notification message
templates, other platforms.

## References

- [Windows 10/11 compliance policy (`windows10CompliancePolicy`)](https://learn.microsoft.com/graph/api/resources/intune-deviceconfig-windows10compliancepolicy?view=graph-rest-1.0) · [create](https://learn.microsoft.com/graph/api/intune-deviceconfig-windows10compliancepolicy-create?view=graph-rest-1.0) · [update](https://learn.microsoft.com/graph/api/intune-deviceconfig-windows10compliancepolicy-update?view=graph-rest-1.0) · [list deviceCompliancePolicies](https://learn.microsoft.com/graph/api/intune-deviceconfig-devicecompliancepolicy-list?view=graph-rest-1.0)
- [assign](https://learn.microsoft.com/graph/api/intune-deviceconfig-devicecompliancepolicy-assign?view=graph-rest-1.0) · [scheduleActionsForRules](https://learn.microsoft.com/graph/api/intune-deviceconfig-devicecompliancepolicy-scheduleactionsforrules?view=graph-rest-1.0) · [deviceComplianceScheduledActionForRule](https://learn.microsoft.com/graph/api/resources/intune-deviceconfig-devicecompliancescheduledactionforrule?view=graph-rest-1.0) · [deviceComplianceActionItem](https://learn.microsoft.com/graph/api/resources/intune-deviceconfig-devicecomplianceactionitem?view=graph-rest-1.0) · [groupAssignmentTarget](https://learn.microsoft.com/graph/api/resources/intune-shared-groupassignmenttarget?view=graph-rest-1.0)
- [managedDevice resource](https://learn.microsoft.com/graph/api/resources/intune-devices-manageddevice?view=graph-rest-1.0) · [list managedDevices](https://learn.microsoft.com/graph/api/intune-devices-manageddevice-list?view=graph-rest-1.0) · [syncDevice](https://learn.microsoft.com/graph/api/intune-devices-manageddevice-syncdevice?view=graph-rest-1.0)
- [Compliance overview and tenant-wide compliance policy settings](https://learn.microsoft.com/intune/device-security/compliance/overview#compliance-policy-settings) · [Actions for noncompliance](https://learn.microsoft.com/intune/device-security/compliance/configure-noncompliance-actions) · [Windows compliance settings](https://learn.microsoft.com/intune/device-security/compliance/ref-windows-settings) · [Monitor compliance](https://learn.microsoft.com/intune/device-security/compliance/monitor-policy)
- [Device cleanup rules](https://learn.microsoft.com/intune/governance/configure-cleanup-rules) · [Intune licensing](https://learn.microsoft.com/intune/fundamentals/licensing) · [Intune planning guide: costs and licensing](https://learn.microsoft.com/intune/fundamentals/planning-guide#step-3---determine-costs-and-licensing)
- [Windows automatic enrollment (MDM user scope)](https://learn.microsoft.com/intune/device-enrollment/windows/guide#windows-automatic-enrollment) · [Entra join during OOBE](https://learn.microsoft.com/entra/identity/devices/device-join-out-of-box) · [Intune and Entra device limits](https://learn.microsoft.com/intune/device-enrollment/limits-intune-entra) · [Local administrators on Entra joined devices](https://learn.microsoft.com/entra/identity/devices/assign-local-admin)
- [Windows 11 requirements, VM support](https://learn.microsoft.com/windows/whats-new/windows-11-requirements#virtual-machine-support) · [Hyper-V generation 2 security features](https://learn.microsoft.com/windows-server/virtualization/hyper-v/generation-2-virtual-machine-security-features) · [Intune network endpoints (Azure attestation for Windows 11 health checks)](https://learn.microsoft.com/intune/fundamentals/endpoints#migrating-device-health-attestation-compliance-policies-to-microsoft-azure-attestation) · [BitLocker operations guide](https://learn.microsoft.com/windows/security/operating-system-security/data-protection/bitlocker/operations-guide#enable-bitlocker) · [Enable-BitLocker](https://learn.microsoft.com/powershell/module/bitlocker/enable-bitlocker)
- Blog: [Intune & Device Management — Complete Guide](https://www.devladlog.com/articles/office-365/2026-04-01-intune-device-management-complete-guide-2026/)
  (note: the current article has no Intune-specific content: its code uses placeholder cmdlets `Set-Configuration` and
  `Get-DeploymentStatus`, an `api.microsoft.com` endpoint that isn't Microsoft Graph, and `Directory.ReadWrite.All`
  scopes, and lists DLP as an Intune control; this folder's code is meant to replace it)
