# Remote Desktop Services check

Connection broker: `con-rds01.lab.contoso.com`

## Servers and role services

| Server | Role services |
|---|---|
| con-rds01.lab.contoso.com | RDS-CONNECTION-BROKER, RDS-WEB-ACCESS, RDS-RD-SERVER, RDS-LICENSING |

## Session hosts

| Host | OS | Installation | Grace days left |
|---|---|---|---|
| CON-RDS01 | Microsoft Windows Server 2025 Datacenter Evaluation | Server | 118 |

## Findings

| Severity | Target | Check | Message |
|---|---|---|---|
| Medium | RDPublishing | CertSelfSigned | The RDPublishing certificate is self-signed (Learn: level Untrusted). Clients show a warning, and people learn to click through it. Replace it with an enterprise or public certificate (Set-RDCertificate). |
| Medium | RDRedirector | CertSelfSigned | The RDRedirector certificate is self-signed (Learn: level Untrusted). Clients show a warning, and people learn to click through it. Replace it with an enterprise or public certificate (Set-RDCertificate). |
| Medium | RDWebAccess | CertSelfSigned | The RDWebAccess certificate is self-signed (Learn: level Untrusted). Clients show a warning, and people learn to click through it. Replace it with an enterprise or public certificate (Set-RDCertificate). |
| Info | con-rds01.lab.contoso.com | SingleBroker | One RD Connection Broker: it keeps the session table, so it is a single point of failure for reconnects. Learn lists high availability for the broker as a supported design. |
| Info | con-rds01.lab.contoso.com | SingleSessionHost | One RD Session Host: no load balancing and every update window is an outage. |

## Sessions

| Host | Total | Active | Disconnected | Users |
|---|---|---|---|---|
| con-rds01.lab.contoso.com | 2 | 1 | 1 | alex.demo, sam.demo |

