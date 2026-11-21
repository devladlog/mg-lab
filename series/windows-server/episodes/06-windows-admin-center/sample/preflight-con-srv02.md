# Windows Admin Center preflight: CON-SRV02

Collected 11/20/2026 09:00:00 | URL https://con-srv02.lab.contoso.com | Mode Administration

| Gateway | OS | Build | Type | Domain | CPU | RAM GB | Free GB |
|---|---|---|---|---|---|---|---|
| CON-SRV02 | Microsoft Windows Server 2025 Datacenter Evaluation | 26100 | Server | lab.contoso.com | 2 | 4 | 38.2 |

| Node | Reachable | Build | SSO (RBCD) | RBAC |
|---|---|---|---|---|
| con-dc01.lab.contoso.com | yes | 26100 | no | no |
| con-srv01.lab.contoso.com | yes | 26100 | yes | yes |
| con-srv02.lab.contoso.com | yes | 26100 | no | no |
| con-sql01.lab.contoso.com | no | 0 | yes | no |
| con-cli01.lab.contoso.com | yes | 26100 | yes | no |

## Findings

| Severity | Target | Check | Message |
|---|---|---|---|
| Info | CON-SQL01 | NodeUnreachable | No WinRM/CIM answer from the gateway: WinRM cannot complete the operation. |
| Info | CON-SRV02 | SelfSignedCertificate | No certificate configured: the installer generates a self-signed one that expires after 60 days (testing only). |

