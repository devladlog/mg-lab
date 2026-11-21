# Certificate check

## Certificates in the machine store

| Server | Subject | Template | Not after (UTC) | Days left | Key | Signature | CDP http |
|---|---|---|---|---|---|---|---|
| CON-DC01 | CN=CON-DC01.lab.contoso.com | DomainController | 2027-11-20 | 364 | RSA 2048 | sha256RSA | no |
| CON-SRV01 | CN=CON-SRV01.lab.contoso.com | Machine | 2026-11-30 | 8 | RSA 2048 | sha256RSA | no |
| CON-SRV02 | CN=Lab Test Portal | - | 2026-12-05 | 13 | RSA 2048 | sha256RSA | no |
| CON-SQL01 | CN=CON-SQL01 legacy | - | 2026-10-12 | -41 | RSA 1024 | sha1RSA | no |
| CON-CA01 | CN=Contoso Lab Issuing CA, DC=lab, DC=contoso, DC=com | - | 2031-11-20 | 1825 | RSA 2048 | sha256RSA | no |

## The CA

- Server: **CON-CA01**, CertSvc: **Running**
- CA certificate: Contoso Lab Issuing CA, RSA 2048, sha256RSA, not after 2031-11-20
- Base CRL: Contoso Lab Issuing CA.crl, next update 2026-11-28 10:00 UTC
- CDP: `C:\Windows\system32\CertSrv\CertEnroll\<CAName><CRLNameSuffix><DeltaCRLAllowed>.crl` publish=True in-certificates=False
- CDP: `ldap:///CN=<CATruncatedName><CRLNameSuffix>,CN=<ServerShortName>,CN=CDP,CN=Public Key Services,CN=Services,<ConfigurationContainer><CDPObjectClass>` publish=True in-certificates=True
- Published templates: Machine, DomainController, LabWebServer, LabSmartcard

## Findings

| Severity | Target | Check | Message |
|---|---|---|---|
| High | CON-CA01 | TemplateSuppliesIdentity | Template 'LabWebServer': the requester supplies the subject or subject alternative name (Learn: SubjectNameEnrolleeSupplies), the certificate has an EKU that can sign someone in, nobody approves, and CONTOSO\Domain Computers can enroll. Anyone in that group can ask for a certificate that names someone else. |
| High | CON-SQL01 | CertExpired | CN=CON-SQL01 legacy [51515151] expired 41 day(s) ago. |
| High | CON-SQL01 | CertWeakKey | CN=CON-SQL01 legacy [51515151] has an RSA key of 1024 bits (policy: at least 2048). |
| High | CON-SQL01 | CertWeakSignature | CN=CON-SQL01 legacy [51515151] is signed with sha1RSA: an SHA-1 or MD5 signature is not acceptable for a new certificate. |
| High | CON-SRV01 | CertExpiring | CN=CON-SRV01.lab.contoso.com [51515151] expires in 8 day(s) (critical below 14). |
| High | CON-SRV02 | CertExpiring | CN=Lab Test Portal [52525252] expires in 13 day(s) (critical below 14). |
| Medium | CON-CA01 | CdpNoHttp | No HTTP URL is added to the CRL distribution point extension of issued certificates. Learn: publish an HTTP CRL location so clients outside the organization and non-Windows clients can validate certificates. |
| Medium | CON-DC01 | CertNoHttpCdp | CN=CON-DC01.lab.contoso.com [D0D0D0D0] (template DomainController) has no HTTP CRL distribution point. Learn: publish an HTTP location so clients outside the domain and non-Windows clients can check revocation. |
| Medium | CON-SRV01 | CertNoHttpCdp | CN=CON-SRV01.lab.contoso.com [51515151] (template Machine) has no HTTP CRL distribution point. Learn: publish an HTTP location so clients outside the domain and non-Windows clients can check revocation. |
| Low | CON-CA01 | TemplateSuppliesIdentityGuarded | Template 'LabSmartcard': the requester supplies the subject or subject alternative name and the certificate has an EKU that can sign someone in, but requests need approval. Keep it that way: review who may enroll. |
| Low | CON-SRV02 | CertSelfSigned | CN=Lab Test Portal [52525252] is self-signed: nobody else can chain it to a trusted root. |

