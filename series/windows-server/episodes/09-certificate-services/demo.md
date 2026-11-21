# Demo shot list — DEVLADLOG Windows Server #9: Certificate Services

## Lab environment

Recorded on the **shared local Hyper-V lab** (`series/LAB.md`): domain `lab.contoso.com` / `CONTOSO`, network
`10.50.0.0/24`. One **extra VM** (also listed in `series/LAB-REQUESTS.md`), no cloud, no licence, cost 0.

| Role in the episode | VM | OS / edition | vCPU / RAM / disk | IP | Notes |
|---|---|---|---|---|---|
| **Admin console, runs everything** | CON-SRV02 (shared) | WS 2025 Datacenter Eval, Desktop Experience | 2 / 2–3 GB (existing) | 10.50.0.22 | episode folder in `C:\lab\ep09`; RSAT AD CS tools for the Certificate Templates console |
| **The CA (new, throwaway)** | **CON-CA01** | WS 2025 Datacenter Eval, **Server Core** (same evaluation media as the lab) | 2 / 2 GB dynamic / 60 GB | 10.50.0.43, `MGLab-NAT`, DNS 10.50.0.10, **domain-joined** to `lab.contoso.com` | gets AD CS, IIS and the IIS scripting tools from `Deploy-CertLab.ps1`; WinRM enabled (default on a domain-joined Server Core) |
| Domain controller | CON-DC01 (shared) | WS 2025 Datacenter Eval, Server Core | existing | 10.50.0.10 | receives the enterprise CA's objects in the configuration partition; gets a Domain Controller certificate by autoenrollment |
| Members | CON-SRV01, CON-SQL01 (shared) | Server Core | existing | .21 / .30 | CON-SRV01 enrolls certificates; CON-SQL01 only holds a seeded legacy certificate |

- Screens are recorded on **CON-SRV02** (VMConnect, elevated Windows PowerShell 5.1) signed in as the **lab
  Administrator** (`CONTOSO\Administrator`, an Enterprise Admin: Learn requires that for an enterprise CA).
  Passwords are never typed on camera or written in a file.
- **Why a new VM and not CON-SRV01:** an enterprise CA writes into Active Directory and can only be torn down
  partly. A throwaway VM keeps the shared servers clean; the lab is rebuilt by `Start-MGLab.ps1` afterwards anyway.
- **Before recording: Hyper-V checkpoints** of CON-DC01, CON-SRV01, CON-SRV02, CON-SQL01 (and CON-CA01 once created):
  `Checkpoint-VM -Name CON-DC01 -SnapshotName pre-ep09` and so on. The lab has one domain controller. This is the
  tear-down (see below).

Everything in `src/` and `tests/` already ran in the build container: 46 Pester tests, and the check on three invented
fact files (`sample/`). **Needs the lab (not run yet):** both collectors on real servers, the CA build, the HTTP CDP,
`Get-Certificate` through remoting, the renewal. Rewrite the narration of the screen scenes to the real output on the
recording day.

## Prepare (before recording)

On the laptop (Hyper-V host), elevated PowerShell, repo root:

```powershell
$cred = Get-Credential 'CONTOSO\Administrator'                      # typed off camera
foreach ($v in 'CON-DC01','CON-SRV01','CON-SRV02','CON-SQL01') { Checkpoint-VM -Name $v -SnapshotName pre-ep09 }
$s = New-PSSession -VMName CON-SRV02 -Credential $cred
Copy-Item -ToSession $s -Path .\series\windows-server\episodes\09-certificate-services -Destination C:\lab\ep09 -Recurse -Force
Invoke-Command -Session $s { Install-WindowsFeature RSAT-ADCS -IncludeAllSubFeature | Out-Null; Get-WindowsFeature *ADCS* | ft Name, Installed }   # check the names on the day
Remove-PSSession $s
```

Create **CON-CA01** by hand like the other Server Core VMs (same base image, `MGLab-NAT`, 10.50.0.43/24, gateway
10.50.0.1, DNS 10.50.0.10), join it to `lab.contoso.com`, and check that `Invoke-Command -ComputerName CON-CA01 { hostname }`
works from CON-SRV02. Then `Checkpoint-VM -Name CON-CA01 -SnapshotName pre-ep09`.

On CON-SRV02: **Windows PowerShell (Admin)**, `cd C:\lab\ep09\src`, `function prompt { 'PS> ' }`, large font.

## Screens to capture (match the `screen` scenes in script.yaml)

Record in this order: the state the check sees depends on it.

### 1. `screens/ca-build.jpg` — "WhatIf first, then the real build"
```powershell
.\Deploy-CertLab.ps1 -Step Ca -WhatIf                  # plan table (Irreversible column) + What if lines
.\Deploy-CertLab.ps1 -Step Ca -AllowCaInstall          # Features, Install, CrlPeriods
Invoke-Command -ComputerName CON-CA01 { Get-Service CertSvc; certutil -CAInfo name }
```
Capture the plan with the Irreversible column and the final service/CA name. If `Install-AdcsCertificationAuthority`
fails through remoting (double hop, key access), run the Install step in a VMConnect session on CON-CA01 as the lab
Administrator and say so; the plan text is the same. Wait for the CA to publish its first CRL before the next screen.

### Seed the problems the check will find (off camera; each is real)
1. **A template that lets the requester choose the subject.** On CON-SRV02 open `certtmpl.msc`, duplicate **Web Server**
   as `LabWebServer`: *Subject Name* tab → **Supply in the request**; *Extensions* → Application Policies → add
   **Client Authentication**; *Security* → **Domain Computers** Enroll. Duplicating a template cannot be done with the
   AD CS cmdlets (Learn: `Add-CATemplate` only publishes). Publish it: `Invoke-Command -ComputerName CON-CA01 { Add-CATemplate -Name LabWebServer -Force }`.
2. **A template with a 10-day certificate.** Duplicate **Computer** as `LabShortLived` (validity 10 days, renewal 2 days,
   Domain Computers Enroll, autoenroll off), publish it the same way, then on CON-SRV01:
   `Get-Certificate -Template LabShortLived -CertStoreLocation Cert:\LocalMachine\My`.
3. **A self-signed certificate about to expire** (CON-SRV02, elevated):
   `New-SelfSignedCertificate -Subject 'CN=Lab Test Portal' -DnsName portal.lab.contoso.com -CertStoreLocation Cert:\LocalMachine\My -NotAfter (Get-Date).AddDays(9)`
4. **A weak, expired legacy certificate** (CON-SQL01): `New-SelfSignedCertificate -Subject 'CN=CON-SQL01 legacy' -KeyLength 1024 -HashAlgorithm SHA1 -NotBefore (Get-Date).AddDays(-400) -NotAfter (Get-Date).AddDays(-1) -CertStoreLocation Cert:\LocalMachine\My`.
   If Windows refuses 1024 bits, SHA-1 or a past date, **say so on camera**; the check reports whatever really exists.
5. Let the domain controller autoenroll: `Invoke-Command -ComputerName CON-DC01 { certutil -pulse }`, wait for the Domain
   Controller Authentication certificate (Learn: an enterprise CA makes DCs enroll automatically).

### 2. `screens/check-before.jpg` — "The lab, as it is today"
```powershell
.\Invoke-CertCheck.ps1 -FactsFile .\facts-before.json -OutFile .\check-before.md -PlanOnly
```
Capture the findings table, the renewal plan and the last line. Expect: `TemplateSuppliesIdentity` (High) for
`LabWebServer`, `CertExpiring` for the portal and the short-lived certificate, `CdpNoHttp` and `CertNoHttpCdp` (the HTTP
step has not run yet), and whatever the legacy certificate shows. The sample on invented data says 11 findings, 6 high;
the real numbers decide the narration. Keep `CollectorError` rows (language of `certutil -dump`, template reads):
they are part of the truth.

### 3. `screens/cdp-http.jpg` — "Issue a certificate, check the chain"
```powershell
.\Deploy-CertLab.ps1 -Step Http -WhatIf ; .\Deploy-CertLab.ps1 -Step Http
Invoke-Command -ComputerName CON-SRV01 { $c = Get-Certificate -Template Machine -CertStoreLocation Cert:\LocalMachine\My; Export-Certificate -Cert $c.Certificate -FilePath C:\Windows\Temp\srv01.cer | Out-Null }
Copy-Item \\CON-SRV01\C$\Windows\Temp\srv01.cer .
certutil -verify -urlfetch .\srv01.cer
```
Show the plan, then the `certutil` output with the HTTP CRL URL retrieved. If the `.crl` request returns an error, that
is the MIME mapping Learn warns about: add `application/pkix-crl` for `.crl` on the `pki` virtual directory, record the
fix, and rerun. Do not put the exported file in the repo.

### 4. `screens/renew.jpg` — "Renew what is about to expire"
```powershell
.\Deploy-CertLab.ps1 -Step Renew -WhatIf               # Enroll and Manual steps, What if line for the Enroll step
.\Deploy-CertLab.ps1 -Step Renew                       # Get-Certificate on CON-SRV01
.\Invoke-CertCheck.ps1 -OutFile .\check-after.md
```
Capture the plan, the result row and the re-check. Fix the `LabWebServer` template (back to *Build from this Active
Directory information*, remove Client Authentication) in `certtmpl.msc` before the re-check, so the High finding goes
away on camera; the self-signed and legacy certificates stay as Manual.

Code scenes (collector, rule, CA plan, HTTP CDP, gotcha, tests) come from `script.yaml`; the Pester output comes from
the command in README.

## Masking

- Lab names are fictional (`CON-*`, `lab.contoso.com`); keep them. CA thumbprints in the lab are fine.
- No private keys and no `.pfx` anywhere; `Get-Certificate` and `Export-Certificate` (public part only) are enough.
- Crop the VMConnect title bars ("<VM> on <host name>") and the laptop taskbar.

## Tear-down

Preferred (the lab is disposable and has one DC): on the laptop, restore the checkpoints taken in *Prepare*:
```powershell
foreach ($v in 'CON-DC01','CON-SRV01','CON-SRV02','CON-SQL01') { Restore-VMSnapshot -VMName $v -Name pre-ep09 -Confirm:$false }
```
Then delete CON-CA01 (VM, VHDX, checkpoint) and `Remove-Item C:\lab\ep09` is moot after the restore.

If the checkpoints cannot be used, undo what the episode did, knowing the CA leaves objects in Active Directory:
```powershell
Invoke-Command -ComputerName CON-CA01 { Uninstall-AdcsCertificationAuthority -Force; Uninstall-WindowsFeature ADCS-Cert-Authority, Web-Server }
# delete LabWebServer and LabShortLived in certtmpl.msc; remove the seeded certificates by subject from Cert:\LocalMachine\My on CON-SRV02 and CON-SQL01
```
and rebuild the lab with `Start-MGLab.ps1` before the next episode that needs a clean domain.
