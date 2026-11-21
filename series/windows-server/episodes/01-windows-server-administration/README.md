# DEVLADLOG Windows Server #1 — Windows Server administration: one baseline, every server

**ServerBaseline** is a small PowerShell module that answers "is every server where I think it is?":

- a **collector** runs on each server over PowerShell remoting (`Invoke-Command`, in parallel) and returns a snapshot:
  OS build and patch level (UBR), Server Core or Desktop Experience, uptime, the pending-reboot signals, disks,
  automatic services that aren't running, installed features, hotfixes, time source, firewall profiles, RDP,
  members of the local Administrators group (read by SID `S-1-5-32-544`)
- a **baseline** in JSON holds the rules (minimum build, patch age, disk space, forbidden/required features, allowed
  local admins, ...)
- **pure checks** turn snapshot + baseline into findings (High / Medium / Low / Info) and a markdown report, worst first
- snapshots are saved as JSON, so the same checks re-run offline — that's how the tests run on Linux

| Path | What it is |
|---|---|
| [`src/ServerBaseline/ServerBaseline.psm1`](src/ServerBaseline/ServerBaseline.psm1) | The module: collector script block, `Get-SbSnapshot`, `Test-SbBaseline`, `ConvertTo-SbMarkdown` |
| [`src/Invoke-ServerBaseline.ps1`](src/Invoke-ServerBaseline.ps1) | Entry script: live (`-ComputerName`) or offline (`-FromSnapshot`), `-OutFile`, `-FailOnHigh` (exit code 1) |
| [`src/baseline.json`](src/baseline.json) | The Contoso lab baseline for Windows Server 2025 (build 26100) |
| [`tests/ServerBaseline.Tests.ps1`](tests/ServerBaseline.Tests.ps1) | 32 Pester tests (rules, report, end-to-end exit code, collector is Windows PowerShell 5.1-safe) |
| [`tests/fixtures/*.json`](tests/fixtures) | Three fictional snapshots: CON-DC01 (Server Core DC), CON-FS01 (the problem child), CON-APP01 (healthy) |
| [`sample/report.md`](sample/report.md) | The report generated from the fixtures |

## Run the tests (any OS, no servers)

```bash
cd series/windows-server/episodes/01-windows-server-administration
pwsh -NoProfile -Command 'Invoke-Pester ./tests'          # Tests Passed: 32, Failed: 0   (PowerShell 7.6, Pester 6.2)

cd src
pwsh -NoProfile -Command './Invoke-ServerBaseline.ps1 -FromSnapshot ../tests/fixtures/*.json -Now 2026-11-20T09:00:00Z -OutFile ../sample/report.md'
# 3 server(s), 14 finding(s), 6 high.
```

## Run it against real servers (lab)

From an admin machine with PowerShell 7.2+ joined to the domain (or with `-Credential`):

```powershell
cd src
./Invoke-ServerBaseline.ps1 -ComputerName CON-DC01, CON-FS01, CON-APP01 -SnapshotDir ./snapshots -OutFile ./report.md
./Invoke-ServerBaseline.ps1 -FromSnapshot ./snapshots/*.json -OutFile ./report.md     # re-check later, no servers needed
```

Nothing is installed on the targets: PowerShell remoting is enabled by default on Windows Server. Schedule it with
`-FailOnHigh` so a High finding fails the job.

## Design choices

- **Collect facts remotely, judge them locally.** Only the collector script block travels to the server; the rules
  stay on the admin side, in a file. Changing a threshold never touches the servers.
- **`-Now` is a parameter.** Uptime and patch age are computed against it, so tests and old snapshots are repeatable.
- **Unreachable servers stay in the report** as a High `Unreachable` finding instead of silently disappearing.
- **`PendingFileRenameOperations` alone is Info, not High.** Applications queue file renames too; Component Based
  Servicing, Windows Update and a pending computer rename are the reboot signals that block maintenance.
- **The stopped-services ignore list starts empty.** Trigger-start services aren't visible through `Win32_Service`,
  so some Automatic services are legitimately stopped. Fill the list from *your* first run, not from a blog.
- **Hotpatch:** servers on Hotpatch only need a restart for the quarterly baseline update; raise `MaxUptimeDays`
  for them.

## What we learned / gotchas

- **The remote side runs Windows PowerShell 5.1.** With WinRM enabled, PowerShell 7 connects to the existing
  `Microsoft.PowerShell` endpoint, which is Windows PowerShell 5.1. A collector that uses `??`, `?.`, the ternary
  operator or `&&` works locally and fails on every server. A Pester test parses the collector's AST and fails on any
  of them; another test checks the collector doesn't call module functions (only the script block is sent).
- **`Get-HotFix` doesn't see every update.** It reads `Win32_QuickFixEngineering`, which only returns updates
  supplied by Component Based Servicing; MSI and Windows Update site updates aren't returned. The update check is
  fine for cumulative updates, and when nothing is dated the finding says to check the Windows Update history.
- **Domain controllers have no local users and groups to manage**, so the collector skips local Administrators when
  `Win32_ComputerSystem.DomainRole` is 4 or 5 (backup/primary DC) and the report points to the domain groups (episode 2).
- **`Format-Table` printed nothing in CI.** With no console attached the host width can be 0, and table output is
  empty. The script pipes through `Out-String -Width 220`.
- **Unix globbing in tests:** calling `pwsh -File script.ps1 -FromSnapshot fixtures/*.json` from PowerShell on Linux
  passed the expanded file list as positional arguments. The test calls `pwsh -Command` with the pattern quoted.

> Not verified yet in the lab (see [demo.md](demo.md)): the exact Automatic services that are stopped on a fresh
> Windows Server 2025, and whether Get-HotFix differs from the update history on the recording day.

## References

- [Windows Server 2025 lifecycle](https://learn.microsoft.com/lifecycle/products/windows-server-2025) (mainstream end 11/14/2029, extended end 11/15/2034)
- [Windows Server release information](https://learn.microsoft.com/windows/release-health/windows-server-release-info) (build 26100, hotpatch calendar)
- [Windows Server 2025 release health](https://learn.microsoft.com/windows/release-health/status-windows-server-2025) (180-day evaluation)
- [What is Server Core?](https://learn.microsoft.com/windows-server/administration/server-core/what-is-server-core)
- [Enable-PSRemoting](https://learn.microsoft.com/powershell/module/microsoft.powershell.core/enable-psremoting) ("PowerShell remoting is enabled by default on Windows Server platforms")
- [Migrating from Windows PowerShell 5.1 to PowerShell 7 — remoting](https://learn.microsoft.com/powershell/scripting/whats-new/migrating-from-windows-powershell-51-to-powershell-7) (PowerShell 7 uses the `Microsoft.PowerShell` 5.1 endpoint)
- [Get-HotFix](https://learn.microsoft.com/powershell/module/microsoft.powershell.management/get-hotfix) (Notes: CBS updates only)
- [Win32_ComputerSystem — DomainRole](https://learn.microsoft.com/windows/win32/cimwin32prov/win32-computersystem)
- [Local accounts](https://learn.microsoft.com/windows/security/identity-protection/access-control/local-accounts) (no Local Users and Groups on a DC)
- [Well-known SIDs](https://learn.microsoft.com/windows/win32/secauthz/well-known-sids) (`S-1-5-32-544` Administrators)
- [Pending reboot reasons (Azure Policy built-in)](https://learn.microsoft.com/azure/governance/policy/samples/swift-csp-cscf-2022) and [DSC RebootPending resource](https://learn.microsoft.com/powershell/dsc/reference/resources/microsoft/windows/rebootpending/)
- [Hotpatch for Windows Server](https://learn.microsoft.com/windows-server/get-started/hotpatch)
- Blog: [Windows Server Administration — Complete Guide](https://www.devladlog.com/articles/windows-server/2025-09-02-windows-server-administration-complete-guide-2025/)
