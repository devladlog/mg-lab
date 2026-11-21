# Remote Desktop Services check

Connection broker: `con-rds01.lab.contoso.com`

## Servers and role services

| Server | Role services |
|---|---|
| con-rds01.lab.contoso.com | RDS-CONNECTION-BROKER, RDS-WEB-ACCESS, RDS-RD-SERVER |

## Session hosts

| Host | OS | Installation | Grace days left |
|---|---|---|---|
| CON-RDS01 | Microsoft Windows Server 2025 Datacenter Evaluation | Server | 118 |

## Findings

| Severity | Target | Check | Message |
|---|---|---|---|
| Medium | con-rds01.lab.contoso.com | NoLicensingServer | No RD Licensing server in the deployment. Learn: there is a 120 day grace period without one; after it clients need an RDS CAL from a license server. |
| Medium | MG Lab Desktops | CollectionOpenToEveryone | User group 'CONTOSO\Domain Users' lets every domain account log on to the session host. Use a dedicated group. |
| Medium | MG Lab Desktops | NoDisconnectLimit | Disconnected sessions are kept forever (0). Policy: end them after 60 minutes. Closed laptops leave running sessions behind. |
| Medium | MG Lab Desktops | NoIdleLimit | No idle session limit (0). Policy: 30 minutes. Idle sessions keep memory and licences busy. (0 is read as no limit; confirm in the lab.) |
| Medium | RDPublishing | CertSelfSigned | The RDPublishing certificate is self-signed (Learn: level Untrusted). Clients show a warning, and people learn to click through it. Replace it with an enterprise or public certificate (Set-RDCertificate). |
| Medium | RDRedirector | CertSelfSigned | The RDRedirector certificate is self-signed (Learn: level Untrusted). Clients show a warning, and people learn to click through it. Replace it with an enterprise or public certificate (Set-RDCertificate). |
| Medium | RDWebAccess | CertSelfSigned | The RDWebAccess certificate is self-signed (Learn: level Untrusted). Clients show a warning, and people learn to click through it. Replace it with an enterprise or public certificate (Set-RDCertificate). |
| Low | MG Lab Desktops | EncryptionBelowPolicy | Encryption level is ClientCompatible, policy wants High (Learn: Low, ClientCompatible (default), High, FipsCompliant). |
| Low | MG Lab Desktops | SecurityLayerBelowPolicy | Security layer is Negotiate, policy wants SSL (Learn: RDP, Negotiate, SSL; the default is Negotiate). |
| Info | CON-RDS01 | OnGracePeriod | Running on the licensing grace period: 118 day(s) left (Learn: 120 days, no license server needed until it ends). |
| Info | con-rds01.lab.contoso.com | NoLicensingConfigured | Neither a license server nor a mode is set: expect the "licensing mode is not configured" balloon in sessions (Learn). |
| Info | con-rds01.lab.contoso.com | SingleBroker | One RD Connection Broker: it keeps the session table, so it is a single point of failure for reconnects. Learn lists high availability for the broker as a supported design. |
| Info | con-rds01.lab.contoso.com | SingleSessionHost | One RD Session Host: no load balancing and every update window is an outage. |

## Sessions

| Host | Total | Active | Disconnected | Users |
|---|---|---|---|---|
| con-rds01.lab.contoso.com | 2 | 1 | 1 | alex.demo, sam.demo |

