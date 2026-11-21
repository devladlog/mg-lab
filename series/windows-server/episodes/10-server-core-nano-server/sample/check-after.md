# Server Core check

## Servers

| Server | Install type | OS | System drive used GB | Memory used MB | Running services | Features | App Compat FOD | WinRM firewall rules |
|---|---|---|---|---|---|---|---|---|
| CON-DC01 | Core | Microsoft Windows Server 2025 Datacenter Evaluation | 13.2 | 1180 | 52 | 9 | NotListed | 4 |
| CON-SRV01 | Core | Microsoft Windows Server 2025 Datacenter Evaluation | 12.9 | 660 | 47 | 9 | Installed | 4 |
| CON-SRV02 | DesktopExperience | Microsoft Windows Server 2025 Datacenter Evaluation | 24.8 | 1210 | 71 | 17 | NotListed | 4 |
| CON-SQL01 | Core | Microsoft Windows Server 2025 Datacenter Evaluation | 15.1 | 1330 | 49 | 5 | NotPresent | 4 |
| CON-CLI01 | Core | Microsoft Windows Server 2025 Datacenter Evaluation | 10.8 | 520 | 41 | 5 | NotPresent | 4 |

## Footprint by install type

Averages over the servers that answered. A measurement of these servers, not a benchmark: they do not run the same roles.

| Install type | Servers | Avg disk used GB | Avg memory used MB | Avg running services | Avg features installed |
|---|---|---|---|---|---|
| Core | 4 | 13 | 922 | 47 | 7 |
| DesktopExperience | 1 | 24.8 | 1210 | 71 | 17 |

## Findings

| Severity | Target | Check | Message |
|---|---|---|---|
| Info | CON-SRV02 | CoreBlockers | 6 installed feature(s) are not in Server Core (Learn): Hyper-V-Tools, PowerShell-ISE, RSAT-ADCS, RSAT-ADCS-Mgmt, Web-Mgmt-Console, Windows-Defender-Gui. |
| Info | CON-SRV02 | DesktopJustified | Desktop Experience on purpose: runs the graphical consoles (RSAT, certtmpl.msc, Hyper-V Manager) for the whole lab. |

