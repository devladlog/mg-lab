# Remote Desktop Services check

Connection broker: `con-rds01.lab.contoso.com`

## Servers and role services

| Server | Role services |
|---|---|
| con-rds01.lab.contoso.com | RDS-CONNECTION-BROKER, RDS-WEB-ACCESS, RDS-RD-SERVER |

## Session hosts

| Host | OS | Installation | Grace days left |
|---|---|---|---|
| CON-RDS01 | Microsoft Windows Server 2025 Datacenter Evaluation | Server Core | 0 |

## Findings

| Severity | Target | Check | Message |
|---|---|---|---|
| High | CON-RDS01 | GracePeriodOver | The licensing grace period is over (GetGracePeriodDays returned 0) and no license server is configured. Learn: clients now need an RDS CAL from a license server to sign in. |
| High | CON-RDS01 | SessionHostOnServerCore | This server is Server Core. Learn: the RD Session Host, RD Web Access and RD Gateway role services are not in Server Core (Connection Broker, Licensing and Virtualization Host are). Use Server with Desktop Experience. |
| High | MG Lab Desktops | EncryptionBelowPolicy | Encryption level is Low, policy wants High (Learn: Low, ClientCompatible (default), High, FipsCompliant). |
| High | MG Lab Desktops | NlaOff | Network Level Authentication is off: the logon screen is offered to anyone who can reach port 3389 before they authenticate. |
| High | MG Lab Desktops | SecurityLayerBelowPolicy | Security layer is RDP, policy wants SSL (Learn: RDP, Negotiate, SSL; the default is Negotiate). |
| High | RDPublishing | CertExpired | The RDPublishing certificate expired on 2026-10-01. |
| High | RDRedirector | CertNotConfigured | The RDRedirector role service has no valid certificate (Get-RDCertificate level: Not Configured). |
| Medium | con-rds01.lab.contoso.com | NoLicensingServer | No RD Licensing server in the deployment. Learn: there is a 120 day grace period without one; after it clients need an RDS CAL from a license server. |
| Medium | MG Lab Desktops | CollectionOpenToEveryone | User group 'Everyone' lets every domain account log on to the session host. Use a dedicated group. |
| Medium | MG Lab Desktops | NoDisconnectLimit | Disconnected sessions are kept forever (0). Policy: end them after 60 minutes. Closed laptops leave running sessions behind. |
| Medium | MG Lab Desktops | NoIdleLimit | No idle session limit (0). Policy: 30 minutes. Idle sessions keep memory and licences busy. (0 is read as no limit; confirm in the lab.) |
| Medium | RDPublishing | CertSelfSigned | The RDPublishing certificate is self-signed (Learn: level Untrusted). Clients show a warning, and people learn to click through it. Replace it with an enterprise or public certificate (Set-RDCertificate). |
| Medium | RDWebAccess | CertExpiring | The RDWebAccess certificate expires in 14 day(s) (policy: at least 30). |
| Medium | RDWebAccess | CertSelfSigned | The RDWebAccess certificate is self-signed (Learn: level Untrusted). Clients show a warning, and people learn to click through it. Replace it with an enterprise or public certificate (Set-RDCertificate). |
| Info | con-rds01.lab.contoso.com | CollectorError | Get-RDLicenseConfiguration: invented error for the test |
| Info | con-rds01.lab.contoso.com | NoLicensingConfigured | Neither a license server nor a mode is set: expect the "licensing mode is not configured" balloon in sessions (Learn). |
| Info | con-rds01.lab.contoso.com | SingleBroker | One RD Connection Broker: it keeps the session table, so it is a single point of failure for reconnects. Learn lists high availability for the broker as a supported design. |
| Info | con-rds01.lab.contoso.com | SingleSessionHost | One RD Session Host: no load balancing and every update window is an outage. |

## Sessions

| Host | Total | Active | Disconnected | Users |
|---|---|---|---|---|
| con-rds01.lab.contoso.com | 2 | 1 | 1 | alex.demo, sam.demo |

