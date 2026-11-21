# Security baseline check

| Server | OS | Domain role | SMB sign (srv/cli) | SMB1 | LmCompat | WDigest | Cred Guard | Proc. audit | Defender RT | LAPS |
|---|---|---|---|---|---|---|---|---|---|---|
| CON-DC01 | Microsoft Windows Server 2025 Datacenter Evaluation | 4 | False/True | False | not set | not set | no | No Auditing | on | no |
| CON-SRV01 | Microsoft Windows Server 2025 Datacenter Evaluation | 3 | False/True | False | not set | not set | running | No Auditing | on | no |
| CON-SRV02 | Microsoft Windows Server 2025 Datacenter Evaluation | 3 | False/True | False | not set | not set | running | No Auditing | on | no |
| CON-SQL01 | Microsoft Windows Server 2025 Datacenter Evaluation | 3 | False/True | False | not set | not set | running | No Auditing | on | no |
| CON-CLI01 | Microsoft Windows Server 2025 Datacenter Evaluation | 3 | False/True | False | not set | not set | running | No Auditing | on | no |

## Findings

| Severity | Target | Check | Message |
|---|---|---|---|
| Medium | CON-DC01 | CommandLineNotLogged | Include command line in process creation events is not enabled (Learn: off by default). Once on, anyone who can read the Security log sees every command line, passwords included if someone typed them. |
| Medium | CON-DC01 | ProcessCreationNotAudited | Audit Process Creation is 'No Auditing'. Without it there is no event 4688 (Learn). |
| Medium | CON-DC01 | SmbServerSigningNotRequired | Inbound SMB signing is not required (policy: required). Learn: signing protects against tampering and relay; requiring it also disables guest access, so check third-party clients first. |
| Info | CON-DC01 | CredentialGuardNotRunningOnDc | Credential Guard is not running. Learn: default enablement on Windows Server 2025 skips domain controllers. |
| Info | CON-DC01 | LdapSigningNotInRegistry | No LDAPServerIntegrity value on this domain controller. Not a finding by itself: Learn says Windows Server 2025 requires LDAP signing by default for new deployments, and a missing policy on an upgraded DC takes that default. Check the Group Policy result instead. |
| Info | CON-DC01 | LmCompatibilityNotSet | LmCompatibilityLevel is not set in the registry, so the OS default applies; policy wants level 5. |
| Medium | CON-SRV01 | CommandLineNotLogged | Include command line in process creation events is not enabled (Learn: off by default). Once on, anyone who can read the Security log sees every command line, passwords included if someone typed them. |
| Medium | CON-SRV01 | LapsNotBackingUpToAd | No Windows LAPS Group Policy backing up to Active Directory (BackupDirectory is not set; Learn: 0 disabled, 1 Entra ID, 2 Active Directory, default disabled). Every server may share one local administrator password. |
| Medium | CON-SRV01 | ProcessCreationNotAudited | Audit Process Creation is 'No Auditing'. Without it there is no event 4688 (Learn). |
| Medium | CON-SRV01 | SmbServerSigningNotRequired | Inbound SMB signing is not required (policy: required). Learn: signing protects against tampering and relay; requiring it also disables guest access, so check third-party clients first. |
| Info | CON-SRV01 | LmCompatibilityNotSet | LmCompatibilityLevel is not set in the registry, so the OS default applies; policy wants level 5. |
| Medium | CON-SRV02 | CommandLineNotLogged | Include command line in process creation events is not enabled (Learn: off by default). Once on, anyone who can read the Security log sees every command line, passwords included if someone typed them. |
| Medium | CON-SRV02 | LapsNotBackingUpToAd | No Windows LAPS Group Policy backing up to Active Directory (BackupDirectory is not set; Learn: 0 disabled, 1 Entra ID, 2 Active Directory, default disabled). Every server may share one local administrator password. |
| Medium | CON-SRV02 | ProcessCreationNotAudited | Audit Process Creation is 'No Auditing'. Without it there is no event 4688 (Learn). |
| Medium | CON-SRV02 | SmbServerSigningNotRequired | Inbound SMB signing is not required (policy: required). Learn: signing protects against tampering and relay; requiring it also disables guest access, so check third-party clients first. |
| Info | CON-SRV02 | LmCompatibilityNotSet | LmCompatibilityLevel is not set in the registry, so the OS default applies; policy wants level 5. |
| Medium | CON-SQL01 | CommandLineNotLogged | Include command line in process creation events is not enabled (Learn: off by default). Once on, anyone who can read the Security log sees every command line, passwords included if someone typed them. |
| Medium | CON-SQL01 | LapsNotBackingUpToAd | No Windows LAPS Group Policy backing up to Active Directory (BackupDirectory is not set; Learn: 0 disabled, 1 Entra ID, 2 Active Directory, default disabled). Every server may share one local administrator password. |
| Medium | CON-SQL01 | ProcessCreationNotAudited | Audit Process Creation is 'No Auditing'. Without it there is no event 4688 (Learn). |
| Medium | CON-SQL01 | SmbServerSigningNotRequired | Inbound SMB signing is not required (policy: required). Learn: signing protects against tampering and relay; requiring it also disables guest access, so check third-party clients first. |
| Info | CON-SQL01 | LmCompatibilityNotSet | LmCompatibilityLevel is not set in the registry, so the OS default applies; policy wants level 5. |
| Medium | CON-CLI01 | CommandLineNotLogged | Include command line in process creation events is not enabled (Learn: off by default). Once on, anyone who can read the Security log sees every command line, passwords included if someone typed them. |
| Medium | CON-CLI01 | LapsNotBackingUpToAd | No Windows LAPS Group Policy backing up to Active Directory (BackupDirectory is not set; Learn: 0 disabled, 1 Entra ID, 2 Active Directory, default disabled). Every server may share one local administrator password. |
| Medium | CON-CLI01 | ProcessCreationNotAudited | Audit Process Creation is 'No Auditing'. Without it there is no event 4688 (Learn). |
| Medium | CON-CLI01 | SmbServerSigningNotRequired | Inbound SMB signing is not required (policy: required). Learn: signing protects against tampering and relay; requiring it also disables guest access, so check third-party clients first. |
| Info | CON-CLI01 | LmCompatibilityNotSet | LmCompatibilityLevel is not set in the registry, so the OS default applies; policy wants level 5. |

