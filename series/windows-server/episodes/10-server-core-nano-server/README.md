# DEVLADLOG Windows Server #10 — Server Core & Nano Server: audit which servers are really Core, then check your Nano images

Episodes 1 to 9 built and looked after the lab. Four of its five machines are Server Core, one (CON-SRV02) has a desktop
on purpose. This episode checks that this is still true, what the desktop costs, and what Nano Server means today.
One module, **CoreLab**, driven by [`src/core-lab.json`](src/core-lab.json):

1. **Core check.** A read-only collector runs on each server over WinRM: the install type (from the `ServerLevels`
   registry key that Learn documents), the installed roles and features, the state of the Server Core App Compatibility
   feature on demand, the WinRM service and the firewall rule group *Windows Remote Management*, system drive use, memory
   use, running services. `Test-CoreHost` turns that into findings: server does not answer (High), wrong install type,
   remote management firewall rules off, the App Compatibility FOD missing where the config says it is required or
   installed where nothing needs it, a Core server whose system drive is over our limit, and an information row that says
   why a Desktop Experience server has its desktop and which installed features have no Server Core equivalent.
2. **Footprint.** `Get-CoreFootprint` averages disk, memory, running services and installed features by install type.
   It is a measurement of these servers, not a benchmark: they do not run the same roles.
3. **Setup plan.** `Get-CoreSetupPlan` / `Invoke-CoreSetupPlan`: enable the WinRM firewall rule group, add the App
   Compatibility FOD (from Windows Update, or from the Languages and Optional Features ISO you point the config at), then a
   restart. A restart is a step of its own and needs `-AllowRestart`. A server that does not answer, or has the wrong
   install type, becomes a **Manual** step (SConfig at the console; a clean reinstall) that is never run.
4. **Nano Server image check.** Nano Server is not something you install on a host (see below), so `Test-NanoDockerfile`
   reads Dockerfiles: Windows PowerShell in a stage built on a Nano Server image (High), a base image with no pinned tag
   (Low), a Server Core base image that may be worth trying on Nano (Info). It follows `FROM <earlier stage>` and a
   custom `# escape=` character.

| Path | What it is |
|---|---|
| [`src/CoreLab/CoreLab.psm1`](src/CoreLab/CoreLab.psm1) | Collector, rules, footprint, Nano check, report, setup plan and apply (Windows PowerShell 5.1 and PowerShell 7) |
| [`src/core-lab.json`](src/core-lab.json) | Our policy: expected install type per server, who needs the App Compatibility FOD, the size limit, the list of features that are not in Server Core |
| [`src/Invoke-CoreCheck.ps1`](src/Invoke-CoreCheck.ps1) | The check: live over WinRM, or from saved facts; optional `-Dockerfile`; `-PlanOnly`, `-FailOnHigh` |
| [`src/Deploy-CoreLab.ps1`](src/Deploy-CoreLab.ps1) | The setup plan and its apply; `-WhatIf`, `-AllowRestart` |
| [`tests/CoreLab.Tests.ps1`](tests/CoreLab.Tests.ps1) | 56 Pester tests |
| [`tests/fixtures/`](tests/fixtures) | `facts-before/after/bad.json` (**invented sample data**, not measured on any server) and three sample Dockerfiles (not built) |
| [`sample/`](sample) | The report for each fact file and the WhatIf output of the deploy script; a test keeps them equal to what the scripts print |
| [`script.yaml`](script.yaml), [`demo.md`](demo.md) | Narration and shot list |

## Run the tests (any OS, no servers)

```powershell
Install-Module Pester -MinimumVersion 5.5 -Scope CurrentUser     # once
Invoke-Pester ./tests -Output Detailed
# Tests Passed: 56, Failed: 0
./src/Invoke-CoreCheck.ps1 -FromFacts ./tests/fixtures/facts-before.json -PlanOnly
# 5 server(s), 6 finding(s), 1 high.
./src/Invoke-CoreCheck.ps1 -FromFacts ./tests/fixtures/facts-after.json
# 5 server(s), 2 finding(s), 0 high.
./src/Invoke-CoreCheck.ps1 -FromFacts ./tests/fixtures/facts-after.json -Dockerfile ./tests/fixtures/Dockerfile.nano-bad
# 5 server(s), 5 finding(s), 2 high.
```

The tests need nothing from Windows: the collector scriptblock is run for real, with stand-ins for the handful of Windows
commands it calls (`Get-ItemProperty` on the registry, `Get-WindowsFeature`, `Get-WindowsCapability`, `Get-CimInstance`,
`Get-Service`, `Get-NetFirewallRule`). That tests the logic and the shape of the facts, **not** what Windows answers.

## Run it in the lab (CON-SRV02, elevated Windows PowerShell as the lab Administrator)

```powershell
cd C:\lab\ep10\src
.\Invoke-CoreCheck.ps1 -FactsFile .\facts-before.json -OutFile .\check-before.md -PlanOnly   # reads only
.\Deploy-CoreLab.ps1 -WhatIf                     # the plan and what would run
.\Deploy-CoreLab.ps1                             # runs the Run steps; the restart is skipped
.\Deploy-CoreLab.ps1 -AllowRestart               # adds the restart
.\Invoke-CoreCheck.ps1 -OutFile .\check-after.md
```

Details and the shot list are in [demo.md](demo.md).

## What we can say about Nano Server (and what we cannot)

From Microsoft Learn (links below):

- Nano Server is **not available as an installable host operating system**. It is a container base image
  (`mcr.microsoft.com/windows/nanoserver`). That is why this episode has no "Nano host" to audit and why
  `Read-CoreLabConfig` refuses a target whose `ExpectedInstall` or `Role` says Nano.
- Compared with Server Core, the Nano Server image has a smaller API surface and a smaller on-disk footprint. **PowerShell,
  WMI and the Windows servicing stack are absent from it.** It is built for .NET Core applications; the Server Core image
  supports traditional .NET Framework applications.
- The 2025 release has Server Core, Nano Server and Datacenter container base images (Long-Term Servicing Channel).
- Container images are not serviced from inside: Microsoft rebuilds the base images monthly, so you rebuild yours.

We did not measure any Nano Server size or startup time here, and the episode quotes none.

## Design choices

- **Same pattern as episodes 8 and 9.** A read-only collector over WinRM, pure rules, a report, a plan before any change,
  apply with `-WhatIf`, and a switch for the step that disrupts the server.
- **Install type from `ServerLevels`**, the registry key Learn documents for this. The levels are additive:
  `ServerCore` alone is Server Core, `Server-GuiMgmt` adds the Minimal Server Interface, `ServerGuiShell` adds the full
  desktop. No guess from the edition name.
- **"No answer" is a fact, not an exception.** `Get-CoreFacts` turns a failed WinRM connection into a row. A Core server
  you cannot reach has no desktop to fall back on, so that is the one High finding in the host rules.
- **Our policy is in JSON, Learn's facts are in the code.** The size limit and who needs the FOD are ours. The list of
  features that are not in Server Core is copied from Learn into `core-lab.json` so it can be updated without touching
  the module; it is a subset (the roles, role services and features Learn lists as removed).
- **Generated scripts are built from validated config.** The FOD name and the source path go into a script string, so the
  config reader accepts only plain characters for them, and a test parses every generated script.
- **Nothing is converted.** A server of the wrong install type gets a manual rebuild step, because there is no in-place
  conversion.
- **A restart is its own step.** The App Compatibility FOD needs one (Learn shows `RestartNeeded : True`); the plan keeps
  it separate and skips it unless you pass `-AllowRestart`. If a step on a server fails, that server's later steps are
  skipped and the other servers go on.

## What we learned / gotchas

- **No way back to Core.** Learn: you cannot convert between Server Core and Server with Desktop Experience after
  installation; you need a clean installation. The check reports a mismatch and plans a rebuild, never a conversion.
- **SConfig does not run in a remote session.** Learn: SConfig can be used when you are signed in locally or connected with
  Remote Desktop, not in a remote PowerShell session. So every setting we need over WinRM has to have a cmdlet; the one
  that cannot (a server that does not answer) is a manual console step: SConfig option 4, then 1.
- **`Enable-PSRemoting` is per PowerShell version.** Learn: run from PowerShell 6 or later it configures only the endpoints of
  that version; to enable the Windows PowerShell endpoints, run it from Windows PowerShell. Remoting is on by default on
  Windows Server, so our plan only enables the firewall rule group.
- **The FOD is Server Core only, and it is not free of side effects.** Learn: do not add it to a Desktop Experience server;
  it adds tools normally found in Desktop Experience (for example `mmc.exe`); an in-place upgrade removes it, so it has to
  be installed again.
- **`Get-WindowsCapability -Name` takes one exact name**, so the collector lists the capabilities and filters on the prefix
  `ServerCore.AppCompatibility`.
- **A Desktop Experience server stays one.** `CoreBlockers` lists which of its installed features are not in Server Core
  (for CON-SRV02: the RSAT AD CS tools, the Hyper-V GUI tools, the IIS Management Console, PowerShell ISE). That list is
  what you would have to move before a rebuild as Core.
- **The firewall finding is rare on a live lab.** The collector itself arrives over WinRM, so a server that answers has some
  rule open. `WinRmFirewall` only fires when the rule group `Windows Remote Management` is off and the server still
  answers through another rule (for example the compatibility rule). Expect it in the invented sample data, probably not
  in the lab; the finding that matters for a server with no open rule is `Unreachable`.
- **`pwsh -File` does not split `-Dockerfile a,b`.** Call the script from a PowerShell session (`& .\Invoke-CoreCheck.ps1
  -Dockerfile a,b`) to check several files.

> **Not run yet (needs the lab, see [demo.md](demo.md)):** the collector on real servers (the `ServerLevels` values on
> Windows Server 2025 Server Core and Desktop Experience, `Get-WindowsFeature` and `Get-WindowsCapability` through
> `Invoke-Command`, the firewall display group name `Windows Remote Management`), the real footprint numbers (the sample
> files are invented), adding the App Compatibility FOD from Windows Update or from the ISO on CON-SRV01 and the restart,
> and `Restart-Computer -ComputerName` from CON-SRV02. **Not possible here:** building the sample Dockerfiles (no Docker in
> this environment, and no Windows container host in the lab plan), so the Nano Server rules are tested on text only.
> Only parsed and unit-tested here.

## References

- [Server Core vs Server with Desktop Experience install options](https://learn.microsoft.com/en-us/windows-server/get-started/install-options-server-core-desktop-experience) (recommendation, no conversion after installation, differences, remote management)
- [What is the Server Core installation option in Windows Server?](https://learn.microsoft.com/en-us/windows-server/administration/server-core/what-is-server-core) (no desktop by design, what runs locally)
- [Roles, Role Services, and Features not in Windows Server - Server Core](https://learn.microsoft.com/en-us/windows-server/administration/server-core/server-core-removed-roles) (the list in `core-lab.json`)
- [Manage a Server Core server](https://learn.microsoft.com/en-us/windows-server/administration/server-core/server-core-manage) (WAC, RSAT, PowerShell, Server Manager, MMC, the `Windows Remote Management` rule group)
- [Configure a Server Core installation with SConfig](https://learn.microsoft.com/en-us/windows-server/administration/server-core/server-core-sconfig) (starts automatically from Windows Server 2022, option 4, not in a remote PowerShell session)
- [Install the Application Compatibility Feature on Demand on Server Core](https://learn.microsoft.com/en-us/windows-server/get-started/server-core-app-compatibility-feature-on-demand) (capability name, Windows Update or ISO source, restart, Server Core only, lost on upgrade)
- [Server apps must be able to run without the Server Graphical Shell](https://learn.microsoft.com/en-us/windows/compatibility/server-apps-must-be-able-to-run-without-the-server-graphical-shell) (the `ServerLevels` registry values)
- [Overview of Windows container base images](https://learn.microsoft.com/en-us/virtualization/windowscontainers/manage-containers/container-base-images) (Server Core vs Nano Server, what is absent from Nano Server, `ltsc2025` tags)
- [Base image servicing lifecycles](https://learn.microsoft.com/en-us/virtualization/windowscontainers/deploy-containers/base-image-lifecycle) and [Update Windows Server containers](https://learn.microsoft.com/en-us/virtualization/windowscontainers/deploy-containers/update-containers) (2025 Nano Server image, monthly rebuilds)
- [Features removed or no longer developed in Windows Server](https://learn.microsoft.com/en-us/windows-server/get-started/removed-deprecated-features-windows-server) (Nano Server is no longer an installation option)
- [Get-WindowsFeature](https://learn.microsoft.com/en-us/powershell/module/servermanager/get-windowsfeature), [Get-WindowsCapability](https://learn.microsoft.com/en-us/powershell/module/dism/get-windowscapability), [Add-WindowsCapability](https://learn.microsoft.com/en-us/powershell/module/dism/add-windowscapability), [Remove-WindowsCapability](https://learn.microsoft.com/en-us/powershell/module/dism/remove-windowscapability) (demo tear-down), [Restart-Computer](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.management/restart-computer), [Enable-PSRemoting](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/enable-psremoting)
- Blog: [Server Core & Nano Server: Complete Guide](https://www.devladlog.com/articles/windows-server/2025-09-13-server-core-nano-server-complete-guide-2025/)
