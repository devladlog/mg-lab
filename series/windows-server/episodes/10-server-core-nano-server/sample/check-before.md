# Server Core check

## Servers

| Server | Install type | OS | System drive used GB | Memory used MB | Running services | Features | App Compat FOD | WinRM firewall rules |
|---|---|---|---|---|---|---|---|---|
| CON-DC01 | Core | Microsoft Windows Server 2025 Datacenter Evaluation | 13.2 | 1180 | 52 | 9 | NotListed | 4 |
| CON-SRV01 | Core | Microsoft Windows Server 2025 Datacenter Evaluation | 11.6 | 640 | 44 | 9 | NotPresent | 4 |
| CON-SRV02 | DesktopExperience | Microsoft Windows Server 2025 Datacenter Evaluation | 24.8 | 1210 | 71 | 17 | NotListed | 4 |
| CON-SQL01 | Core | Microsoft Windows Server 2025 Datacenter Evaluation | 17.4 | 1330 | 49 | 5 | NotPresent | 0 |
| CON-CLI01 | no answer | - | - | - | - | - | - | - |

## Footprint by install type

Averages over the servers that answered. A measurement of these servers, not a benchmark: they do not run the same roles.

| Install type | Servers | Avg disk used GB | Avg memory used MB | Avg running services | Avg features installed |
|---|---|---|---|---|---|
| Core | 3 | 14.1 | 1050 | 48 | 7.7 |
| DesktopExperience | 1 | 24.8 | 1210 | 71 | 17 |

## Findings

| Severity | Target | Check | Message |
|---|---|---|---|
| High | CON-CLI01 | Unreachable | No answer over WinRM. A Core server has no desktop to fall back on: Connecting to remote server CON-CLI01 failed with the following error message : WinRM cannot complete the operation. |
| Medium | CON-SQL01 | WinRmFirewall | No enabled firewall rule in the group Windows Remote Management. |
| Medium | CON-SRV01 | AppCompatMissing | The App Compatibility FOD is required here (a vendor tool that needs mmc.exe on the box) and its state is 'NotPresent'. |
| Low | CON-SQL01 | FootprintHigh | System drive used: 17.4 GB, our limit for a Core server is 16 GB. |
| Info | CON-SRV02 | CoreBlockers | 6 installed feature(s) are not in Server Core (Learn): Hyper-V-Tools, PowerShell-ISE, RSAT-ADCS, RSAT-ADCS-Mgmt, Web-Mgmt-Console, Windows-Defender-Gui. |
| Info | CON-SRV02 | DesktopJustified | Desktop Experience on purpose: runs the graphical consoles (RSAT, certtmpl.msc, Hyper-V Manager) for the whole lab. |

