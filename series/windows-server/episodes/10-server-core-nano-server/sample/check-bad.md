# Server Core check

## Servers

| Server | Install type | OS | System drive used GB | Memory used MB | Running services | Features | App Compat FOD | WinRM firewall rules |
|---|---|---|---|---|---|---|---|---|
| CON-DC01 | DesktopExperience | Microsoft Windows Server 2025 Datacenter Evaluation | 26 | 1500 | 78 | 11 | NotListed | 4 |
| CON-SRV01 | Core | Microsoft Windows Server 2025 Datacenter Evaluation | 11.6 | 640 | 44 | 9 | NotPresent | 4 |
| CON-SRV02 | Core | Microsoft Windows Server 2025 Datacenter Evaluation | 24.8 | 1210 | 71 | 17 | NotListed | 4 |
| CON-SQL01 | Core | Microsoft Windows Server 2025 Datacenter Evaluation | 21.7 | 1330 | 49 | 5 | Installed | 4 |
| CON-CLI01 | Unknown | Microsoft Windows Server 2025 Datacenter Evaluation | 10.8 | 520 | 41 | 5 | Unknown | -1 |
| CON-OLD99 | Core | Microsoft Windows Server 2025 Datacenter Evaluation | 9 | 400 | 40 | 5 | NotPresent | 4 |

## Footprint by install type

Averages over the servers that answered. A measurement of these servers, not a benchmark: they do not run the same roles.

| Install type | Servers | Avg disk used GB | Avg memory used MB | Avg running services | Avg features installed |
|---|---|---|---|---|---|
| Core | 4 | 16.8 | 895 | 51 | 9 |
| DesktopExperience | 1 | 26 | 1500 | 78 | 11 |

## Findings

| Severity | Target | Check | Message |
|---|---|---|---|
| Medium | CON-DC01 | InstallTypeMismatch | Expected Core, found DesktopExperience. There is no in-place conversion (Learn): the fix is a clean install. |
| Medium | CON-SRV01 | AppCompatMissing | The App Compatibility FOD is required here (a vendor tool that needs mmc.exe on the box) and its state is 'NotPresent'. |
| Medium | CON-SRV02 | InstallTypeMismatch | Expected DesktopExperience, found Core. There is no in-place conversion (Learn): the fix is a clean install. |
| Low | CON-CLI01 | CollectorError | ServerLevels: Cannot find path |
| Low | CON-CLI01 | InstallTypeUnknown | The ServerLevels registry key could not be read, so Core or Desktop is unknown. |
| Low | CON-OLD99 | UnknownHost | Not in core-lab.json, so no expectation to compare with. |
| Low | CON-SQL01 | AppCompatNotNeeded | The App Compatibility FOD adds tools from Desktop Experience (Learn) but nothing here needs them. |
| Low | CON-SQL01 | CollectorError | Get-WindowsFeature: The term is not recognized |
| Low | CON-SQL01 | FootprintHigh | System drive used: 21.7 GB, our limit for a Core server is 16 GB. |
| Low | CON-SRV02 | FootprintHigh | System drive used: 24.8 GB, our limit for a Core server is 16 GB. |
| Info | CON-DC01 | CoreBlockers | 1 installed feature(s) are not in Server Core (Learn): RSAT-ADCS. |

