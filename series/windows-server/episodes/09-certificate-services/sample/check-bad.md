# Certificate check

## Certificates in the machine store

| Server | Subject | Template | Not after (UTC) | Days left | Key | Signature | CDP http |
|---|---|---|---|---|---|---|---|
| CON-OLDWEB | CN=oldweb.lab.contoso.com | WebServer | 2026-12-01 | 9 | RSA 2048 | sha256RSA | no |

## The CA

- Server: **CON-OLDCA**, CertSvc: **Stopped**
- CA certificate: Contoso Old Internal CA, RSA 1024, sha1RSA, not after 2027-02-01
- Base CRL: Contoso Old Internal CA.crl, next update 2026-11-20 10:00 UTC
- CDP: `\\fileshare\pki\old.crl` publish=True in-certificates=True
- Published templates: AnyoneWeb

## Findings

| Severity | Target | Check | Message |
|---|---|---|---|
| High | CON-OLDCA | CaServiceNotRunning | The CertSvc service is 'Stopped': nothing can be issued and no CRL is published. |
| High | CON-OLDCA | CaWeakKey | The CA key is RSA 1024 bits (policy: at least 2048). |
| High | CON-OLDCA | CaWeakSignature | The CA certificate is signed with sha1RSA. |
| High | CON-OLDCA | CrlExpired | The base CRL (Contoso Old Internal CA.crl) passed its next-update time 23 hour(s) ago: clients that need a fresh CRL will fail validation. |
| High | CON-OLDCA | TemplateSuppliesIdentity | Template 'AnyoneWeb': the requester supplies the subject or subject alternative name (Learn: SubjectNameEnrolleeSupplies), the certificate has no EKU (usable for any purpose), nobody approves, and CONTOSO\Domain Users, NT AUTHORITY\Authenticated Users can enroll. Anyone in that group can ask for a certificate that names someone else. |
| High | CON-OLDWEB | CertExpiring | CN=oldweb.lab.contoso.com [71717171] expires in 9 day(s) (critical below 14). |
| Medium | CON-OLDCA | CaCertificateExpiring | The CA certificate expires in 71 day(s) (warning below 180). Every certificate it issued stops validating on that day, so renew the CA first. |
| Medium | CON-OLDCA | CdpLocalPathInCertificates | A local or UNC path (\\fileshare\pki\old.crl) is added to issued certificates as a distribution point. Learn: don't assume a local folder or UNC path is suitable as a client-facing CDP. |
| Medium | CON-OLDCA | CdpNoHttp | No HTTP URL is added to the CRL distribution point extension of issued certificates. Learn: publish an HTTP CRL location so clients outside the organization and non-Windows clients can validate certificates. |
| Medium | CON-OLDWEB | CertNoHttpCdp | CN=oldweb.lab.contoso.com [71717171] (template WebServer) has no HTTP CRL distribution point. Learn: publish an HTTP location so clients outside the domain and non-Windows clients can check revocation. |
| Low | CON-OLDWEB | CertNoPrivateKey | CN=oldweb.lab.contoso.com [71717171] is a server authentication certificate without a private key on this machine. |
| Info | CON-OLDCA | CollectorError | Templates: access denied |

