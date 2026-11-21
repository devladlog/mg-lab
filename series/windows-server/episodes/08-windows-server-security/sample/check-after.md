# Security baseline check

| Server | OS | Domain role | SMB sign (srv/cli) | SMB1 | LmCompat | WDigest | Cred Guard | Proc. audit | Defender RT | LAPS |
|---|---|---|---|---|---|---|---|---|---|---|
| CON-DC01 | Microsoft Windows Server 2025 Datacenter Evaluation | 4 | True/True | False | 5 | 0 | no | Success | on | no |
| CON-SRV01 | Microsoft Windows Server 2025 Datacenter Evaluation | 3 | True/True | False | 5 | 0 | running | Success | on | AD |
| CON-SRV02 | Microsoft Windows Server 2025 Datacenter Evaluation | 3 | True/True | False | 5 | 0 | running | Success | on | AD |
| CON-SQL01 | Microsoft Windows Server 2025 Datacenter Evaluation | 3 | True/True | False | 5 | 0 | running | Success | on | AD |
| CON-CLI01 | Microsoft Windows Server 2025 Datacenter Evaluation | 3 | True/True | False | 5 | 0 | running | Success | on | AD |

## Findings

| Severity | Target | Check | Message |
|---|---|---|---|
| Info | CON-DC01 | CredentialGuardNotRunningOnDc | Credential Guard is not running. Learn: default enablement on Windows Server 2025 skips domain controllers. |

