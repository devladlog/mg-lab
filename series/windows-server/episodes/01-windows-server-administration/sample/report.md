# Server baseline report

Generated 2026-11-20 09:00 UTC for 3 server(s).

| Server | High | Medium | Low | Info |
|---|---:|---:|---:|---:|
| CON-APP01 | 0 | 0 | 0 | 1 |
| CON-DC01 | 1 | 0 | 0 | 2 |
| CON-FS01 | 5 | 3 | 2 | 0 |

| Severity | Server | Check | Detail |
|---|---|---|---|
| High | CON-DC01 | TimeSource | Time source is 'Local CMOS Clock'. Domain members must follow the domain hierarchy; the PDC emulator an external NTP source. |
| High | CON-FS01 | DiskSpace | D: has 6.3% free (31.5 of 500 GB). |
| High | CON-FS01 | Firewall | Windows Firewall 'Public' profile is off. |
| High | CON-FS01 | ForbiddenFeature | Feature 'FS-SMB1' is installed. Remove it: Uninstall-WindowsFeature FS-SMB1 |
| High | CON-FS01 | PendingReboot | Reboot pending: Windows Update. |
| High | CON-FS01 | Updates | Last update installed 128 days ago (2026-07-15). Baseline: 45 days. |
| Medium | CON-FS01 | LocalAdministrators | Unexpected member of local Administrators: CONTOSO\alex.demo |
| Medium | CON-FS01 | Service | Automatic service 'ContosoBackupAgent' (Contoso Backup Agent) is Stopped. |
| Medium | CON-FS01 | Uptime | Up for 110 days (baseline: 35). Patch reboots are being skipped. |
| Low | CON-FS01 | InstallationType | Installed as 'Server'. Baseline prefers Server Core (smaller footprint and attack surface). |
| Low | CON-FS01 | Rdp | Remote Desktop is enabled on a server that the baseline manages remotely only. |
| Info | CON-APP01 | PendingFileRename | PendingFileRenameOperations is set (applications use it as well). Clears on the next planned reboot. |
| Info | CON-DC01 | EvaluationEdition | Evaluation edition (180-day licence). Fine for a lab, not for production. |
| Info | CON-DC01 | LocalAdministrators | Domain controller: no local Administrators group. Review the domain Administrators group instead (episode 2). |

