# Security baseline check

| Server | OS | Domain role | SMB sign (srv/cli) | SMB1 | LmCompat | WDigest | Cred Guard | Proc. audit | Defender RT | LAPS |
|---|---|---|---|---|---|---|---|---|---|---|
| HV-DC02 | Microsoft Windows Server 2016 Standard | 4 | False/False | True | 1 | 1 | no | No Auditing | on | no |
| OLD-FS01 | Microsoft Windows Server 2012 R2 Standard | 3 | False/False | True | 2 | 1 | no | No Auditing | off | no |
| APP-SRV03 | Microsoft Windows Server 2025 Datacenter Evaluation | 3 | False/True | False | 3 | not set | running | Success | off | no |

## Findings

| Severity | Target | Check | Message |
|---|---|---|---|
| High | HV-DC02 | LdapSigningNotRequired | LDAPServerIntegrity is 0: the domain controller accepts unsigned LDAP binds (Learn: set Require signing, check clients first). |
| High | HV-DC02 | LmCompatibilityWeak | LmCompatibilityLevel is 1: clients send LM or NTLM responses (levels 0 to 2, Learn). Policy wants 5. |
| High | HV-DC02 | Smb1Enabled | The SMB 1 server protocol is enabled. Disable it (Set-SmbServerConfiguration -EnableSMB1Protocol $false). |
| High | HV-DC02 | WDigestEnabled | WDigest UseLogonCredential is 1: LSASS keeps a copy of the plaintext password (Learn: recommended state is disabled). |
| Medium | HV-DC02 | CommandLineNotLogged | Include command line in process creation events is not enabled (Learn: off by default). Once on, anyone who can read the Security log sees every command line, passwords included if someone typed them. |
| Medium | HV-DC02 | DefenderSignaturesOld | Antivirus signatures are 30 days old (policy: 7). |
| Medium | HV-DC02 | ProcessCreationNotAudited | Audit Process Creation is 'No Auditing'. Without it there is no event 4688 (Learn). |
| Medium | HV-DC02 | SmbServerSigningNotRequired | Inbound SMB signing is not required (policy: required). Learn: signing protects against tampering and relay; requiring it also disables guest access, so check third-party clients first. |
| Low | HV-DC02 | DefenderTamperProtectionOff | Tamper protection is off (it cannot be changed with PowerShell, Learn). |
| Low | HV-DC02 | SmbClientSigningNotRequired | Outbound SMB signing is not required (policy: required). Windows Server 2025 requires outbound signing by default (Learn), so this server was changed or is older. |
| Info | HV-DC02 | CredentialGuardNotRunningOnDc | Credential Guard is not running. Learn: default enablement on Windows Server 2025 skips domain controllers. |
| High | OLD-FS01 | DefenderNotReadable | Get-MpComputerStatus returned nothing: Microsoft Defender Antivirus is missing, disabled or replaced. |
| High | OLD-FS01 | LmCompatibilityWeak | LmCompatibilityLevel is 2: clients send LM or NTLM responses (levels 0 to 2, Learn). Policy wants 5. |
| High | OLD-FS01 | Smb1Enabled | The SMB 1 server protocol is enabled. Disable it (Set-SmbServerConfiguration -EnableSMB1Protocol $false). |
| High | OLD-FS01 | WDigestEnabled | WDigest UseLogonCredential is 1: LSASS keeps a copy of the plaintext password (Learn: recommended state is disabled). |
| Medium | OLD-FS01 | CommandLineNotLogged | Include command line in process creation events is not enabled (Learn: off by default). Once on, anyone who can read the Security log sees every command line, passwords included if someone typed them. |
| Medium | OLD-FS01 | CredentialGuardNotRunning | Credential Guard is not running. Learn: it is on by default on Windows Server 2025 for domain-joined non-DC servers that meet the hardware requirements (VBS, Secure Boot; a Hyper-V VM must be generation 2) and are not explicitly disabled. |
| Medium | OLD-FS01 | LapsNotBackingUpToAd | No Windows LAPS Group Policy backing up to Active Directory (BackupDirectory is not set; Learn: 0 disabled, 1 Entra ID, 2 Active Directory, default disabled). Every server may share one local administrator password. |
| Medium | OLD-FS01 | ProcessCreationNotAudited | Audit Process Creation is 'No Auditing'. Without it there is no event 4688 (Learn). |
| Medium | OLD-FS01 | SmbServerSigningNotRequired | Inbound SMB signing is not required (policy: required). Learn: signing protects against tampering and relay; requiring it also disables guest access, so check third-party clients first. |
| Low | OLD-FS01 | SmbClientSigningNotRequired | Outbound SMB signing is not required (policy: required). Windows Server 2025 requires outbound signing by default (Learn), so this server was changed or is older. |
| Info | OLD-FS01 | CollectorError | Defender: The term 'Get-MpComputerStatus' is not recognized |
| High | APP-SRV03 | DefenderRealTimeOff | Real-time protection is off. |
| Medium | APP-SRV03 | CommandLineNotLogged | Include command line in process creation events is not enabled (Learn: off by default). Once on, anyone who can read the Security log sees every command line, passwords included if someone typed them. |
| Medium | APP-SRV03 | LapsNotBackingUpToAd | No Windows LAPS Group Policy backing up to Active Directory (BackupDirectory is 1; Learn: 0 disabled, 1 Entra ID, 2 Active Directory, default disabled). Every server may share one local administrator password. |
| Medium | APP-SRV03 | LmCompatibilityBelowPolicy | LmCompatibilityLevel is 3, policy wants 5. Level 5 makes domain controllers refuse LM and NTLM (NTLMv2 only, Learn): audit NTLM use first. |
| Medium | APP-SRV03 | SmbServerSigningNotRequired | Inbound SMB signing is not required (policy: required). Learn: signing protects against tampering and relay; requiring it also disables guest access, so check third-party clients first. |

