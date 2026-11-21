# Group Policy hygiene report: lab.contoso.com

Snapshot: 2026-11-20 09:00 UTC - 9 GPO(s), 7 container(s) with links or blocked inheritance.

**High 2 / Medium 2 / Low 3 / Info 2**

| GPO | Status | Links | Computer | User |
|---|---|---|---|---|
| CON-Finance-ScreenLock | ComputerSettingsDisabled | 1 | - | settings (v2) |
| CON-HR-Printers | UserSettingsDisabled | 1 | settings (v1) | - |
| CON-Legacy-Drives | UserSettingsDisabled | 1 | - | settings (v5) |
| CON-Old-Kiosk | AllSettingsEnabled | 1 | settings (v4) | - |
| CON-Sec-Enforced | UserSettingsDisabled | 1 | settings (v2) | - |
| CON-Servers-Baseline | UserSettingsDisabled | 1 | settings (v2) | - |
| CON-Test-Empty | AllSettingsEnabled | 0 | - | - |
| Default Domain Controllers Policy | AllSettingsEnabled | 1 | settings (v1) | - |
| Default Domain Policy | AllSettingsEnabled | 1 | settings (v3) | - |

| Severity | Check | Target | Detail |
|---|---|---|---|
| High | DisabledHalfHasSettings | CON-Legacy-Drives | User settings exist but GpoStatus is UserSettingsDisabled: they are silently ignored. |
| High | UserGpoNoComputerRead | CON-Finance-ScreenLock | User settings, but neither Authenticated Users nor Domain Computers can read it. Since MS16-072 the computer reads user policy: grant Read (not Apply) to Authenticated Users or Domain Computers. |
| Medium | NobodyCanApply | CON-HR-Printers | Linked, but no trustee has Apply group policy. |
| Medium | VersionMismatch | CON-Legacy-Drives | User version AD 5 vs SYSVOL 4: the two halves of the GPO replicate separately and disagree. |
| Low | AllLinksDisabled | CON-Old-Kiosk | Linked 1 time(s), every link disabled. |
| Low | EmptyGpo | CON-Test-Empty | No settings in either half. |
| Low | UnlinkedGpo | CON-Test-Empty | Not linked anywhere: it applies to nobody. Delete it or link it (back it up first). |
| Info | BlockedInheritance | OU=Operations,OU=Users,OU=Contoso,DC=lab,DC=contoso,DC=com | Inheritance is blocked here: only enforced links from above apply. |
| Info | EnforcedLink | CON-Sec-Enforced | Enforced at DC=lab,DC=contoso,DC=com. Use sparingly: it overrides lower links and ignores blocked inheritance. |

