# Windows Admin Center preflight: CON-SRV02

Collected 11/20/2026 09:00:00 | URL https://con-srv02.lab.contoso.com | Mode Administration

| Gateway | OS | Build | Type | Domain | CPU | RAM GB | Free GB |
|---|---|---|---|---|---|---|---|
| CON-SRV02 | Microsoft Windows Server 2025 Datacenter Evaluation | 26100 | Server Core | lab.contoso.com | 2 | 3 | 8.5 |

| Node | Reachable | Build | SSO (RBCD) | RBAC |
|---|---|---|---|---|
| con-dc01.lab.contoso.com | yes | 26100 | no | no |
| con-srv01.lab.contoso.com | no | 0 | yes | yes |
| con-srv02.lab.contoso.com | yes | 26100 | no | no |
| con-sql01.lab.contoso.com | yes | 9600 | yes | no |
| con-cli01.lab.contoso.com | yes | 26100 | yes | no |

## Findings

| Severity | Target | Check | Message |
|---|---|---|---|
| High | CON-SRV01 | NodeUnreachable | No WinRM/CIM answer from the gateway: The WinRM client cannot process the request. |
| High | CON-SRV02 | CertificateEku | Certificate lacks Server Authentication (1.3.6.1.5.5.7.3.1). |
| High | CON-SRV02 | CertificateExpired | Certificate expired on 2026-10-01. |
| High | CON-SRV02 | GatewayOnDomainController | Don't install Windows Admin Center on a domain controller: that configuration isn't supported. |
| High | CON-SRV02 | PortInUse | Port 443 is already used by w3wp. Pick another HttpsPort. |
| Medium | CON-SQL01 | NodeOldOs | Build 9600: Windows Server 2012/2012 R2 need WMF 5.1 and get limited functionality. |
| Medium | CON-SRV02 | CertificateName | Certificate names (old-portal.lab.contoso.com) don't include con-srv02.lab.contoso.com: browsers will warn. |

