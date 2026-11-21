# Certificate check

## Certificates in the machine store

| Server | Subject | Template | Not after (UTC) | Days left | Key | Signature | CDP http |
|---|---|---|---|---|---|---|---|
| CON-DC01 | CN=CON-DC01.lab.contoso.com | DomainController | 2027-11-20 | 364 | RSA 2048 | sha256RSA | yes |
| CON-SRV01 | CN=CON-SRV01.lab.contoso.com | Machine | 2027-11-21 | 365 | RSA 2048 | sha256RSA | yes |
| CON-SRV02 | CN=CON-SRV02.lab.contoso.com | Machine | 2027-11-21 | 365 | RSA 2048 | sha256RSA | yes |
| CON-CA01 | CN=Contoso Lab Issuing CA, DC=lab, DC=contoso, DC=com | - | 2031-11-20 | 1825 | RSA 2048 | sha256RSA | no |

## The CA

- Server: **CON-CA01**, CertSvc: **Running**
- CA certificate: Contoso Lab Issuing CA, RSA 2048, sha256RSA, not after 2031-11-20
- Base CRL: Contoso Lab Issuing CA.crl, next update 2026-11-28 10:00 UTC
- CDP: `C:\Windows\system32\CertSrv\CertEnroll\<CAName><CRLNameSuffix><DeltaCRLAllowed>.crl` publish=True in-certificates=False
- CDP: `ldap:///CN=<CATruncatedName><CRLNameSuffix>,CN=<ServerShortName>,CN=CDP,CN=Public Key Services,CN=Services,<ConfigurationContainer><CDPObjectClass>` publish=True in-certificates=True
- CDP: `http://con-ca01.lab.contoso.com/pki/<CAName><CRLNameSuffix><DeltaCRLAllowed>.crl` publish=False in-certificates=True
- Published templates: Machine, DomainController, LabWebServer, LabSmartcard

## Findings

| Severity | Target | Check | Message |
|---|---|---|---|
| Low | CON-CA01 | TemplateSuppliesIdentityGuarded | Template 'LabSmartcard': the requester supplies the subject or subject alternative name and the certificate has an EKU that can sign someone in, but requests need approval. Keep it that way: review who may enroll. |

