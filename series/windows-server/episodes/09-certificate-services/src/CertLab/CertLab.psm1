Set-StrictMode -Version Latest

# ---------------------------------------------------------------------------------------------------------------
# CertLab: read-only health check for an AD CS lab (certificates on every server, the CA itself, the templates it
# publishes), a renewal plan, and a plan to build the CA. Windows PowerShell 5.1 and PowerShell 7.
# Constants that come from Microsoft Learn live here; OUR policy lives in cert-lab.json.
# ---------------------------------------------------------------------------------------------------------------

$script:Severity = @{ High = 0; Medium = 1; Low = 2; Info = 3 }

# msPKI-Certificate-Name-Flag (Learn: X509CertificateTemplateSubjectNameFlag)
$script:SubjectNameEnrolleeSupplies = 0x1        # the request carries the subject
$script:SanEnrolleeSupplies = 0x10000            # the request carries the subject alternative name
# msPKI-Enrollment-Flag (Learn: X509CertificateTemplateEnrollmentFlag)
$script:EnrollmentPendAllRequests = 0x2          # every request waits for a CA manager
# Certificate-Enrollment extended right (Learn: AD schema, Rights-GUID)
$script:EnrollRightGuid = '0e10c968-78fb-11d2-90d4-00c04f79dc55'
# Signature algorithms we call weak (standard OIDs, RFC 3279 / RFC 5758, not from Learn)
$script:WeakSignatureOids = @{ '1.2.840.113549.1.1.4' = 'md5RSA'; '1.2.840.113549.1.1.5' = 'sha1RSA'; '1.2.840.10045.4.1' = 'sha1ECDSA' }
$script:ServerAuthEku = '1.3.6.1.5.5.7.3.1'

function New-CertFinding {
    param([string] $Target, [string] $Severity, [string] $Check, [string] $Message, [string] $Fix = '')
    [pscustomobject]@{ Severity = $Severity; Target = $Target; Check = $Check; Message = $Message; Fix = $Fix }
}

function Get-CertProp {
    param($Object, [string] $Name, $Default = $null)
    if ($null -eq $Object) { return $Default }
    if ($Object -is [System.Collections.IDictionary]) { if ($Object.Contains($Name)) { return $Object[$Name] }; return $Default }
    $p = $Object.PSObject.Properties[$Name]
    if ($p) { return $p.Value }
    $Default
}

function ConvertTo-CertUtc {
    <# ConvertFrom-Json turns ISO strings into DateTime in PowerShell 7 but not in 5.1: accept both. #>
    param($Value)
    if ($null -eq $Value -or "$Value" -eq '') { return $null }
    if ($Value -is [datetime]) { return $Value.ToUniversalTime() }
    [datetime]::Parse([string]$Value, [cultureinfo]::InvariantCulture, [System.Globalization.DateTimeStyles]::RoundtripKind).ToUniversalTime()
}

function Read-CertLabConfig {
    [CmdletBinding()]
    param([Parameter(Mandatory)] [string] $Path)
    $c = Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json
    if ((Get-CertProp $c 'SchemaVersion') -ne 1) { throw "Unsupported SchemaVersion in '$Path' (expected 1)." }
    foreach ($k in 'Policy', 'Ca', 'Targets') { if (-not (Get-CertProp $c $k)) { throw "'$Path' is missing '$k'." } }
    if ([int]$c.Policy.CertCriticalDays -ge [int]$c.Policy.CertWarnDays) { throw 'CertCriticalDays must be smaller than CertWarnDays.' }
    if ([int]$c.Policy.MinRsaKeyBits -lt 2048) { throw 'MinRsaKeyBits below 2048 is not a policy, it is a finding.' }
    $units = @('Hours', 'Days', 'Weeks', 'Months', 'Years')   # Learn: CAPolicy.inf, Install-AdcsCertificationAuthority
    foreach ($k in 'ValidityPeriod', 'CrlPeriod', 'CrlDeltaPeriod') {
        if ($units -notcontains [string]$c.Ca.$k) { throw "Ca.$k must be one of: $($units -join ', ')." }
    }
    $dupe = @($c.Targets | ForEach-Object { ([string]$_.Name).ToUpperInvariant() } | Group-Object | Where-Object Count -gt 1 | ForEach-Object Name)
    if ($dupe.Count) { throw "Duplicate target(s) in '$Path': $($dupe -join ', ')." }
    $c
}

# ---------------------------------------------------------------------------------------------------------------
# Collector 1: machine certificates (runs ON each server; read-only; self-contained)
# Takes an optional list of X509Certificate2 objects so the same code can be tested away from Windows.
# ---------------------------------------------------------------------------------------------------------------

$script:CertCollector = {
    param($Certificates)
    $ErrorActionPreference = 'Stop'
    $errors = New-Object System.Collections.ArrayList
    if ($null -eq $Certificates) {
        try { $Certificates = @(Get-ChildItem -Path 'Cert:\LocalMachine\My') } catch { [void]$errors.Add("Cert store: $($_.Exception.Message)"); $Certificates = @() }
    }
    $list = New-Object System.Collections.ArrayList
    foreach ($c in @($Certificates)) {
        $ekus = @(); $san = $null; $tplName = $null; $tplInfo = $null; $cdp = @()
        foreach ($e in $c.Extensions) {
            $oid = [string]$e.Oid.Value
            if ($oid -eq '2.5.29.37') {
                $ekus = @(([System.Security.Cryptography.X509Certificates.X509EnhancedKeyUsageExtension]$e).EnhancedKeyUsages | ForEach-Object { [string]$_.Value })
            }
            elseif ($oid -eq '2.5.29.17') { $san = [string]$e.Format($false) }
            elseif ($oid -eq '1.3.6.1.4.1.311.20.2') {
                # v1 template name: a DER BMPString (tag 0x1E, length, UTF-16BE)
                $raw = [byte[]]$e.RawData
                if ($raw.Length -ge 2 -and $raw[0] -eq 0x1E) { $tplName = [System.Text.Encoding]::BigEndianUnicode.GetString($raw, 2, [int]$raw[1]) }
            }
            elseif ($oid -eq '1.3.6.1.4.1.311.21.7') { $tplInfo = [string]$e.Format($false) }
            elseif ($oid -eq '2.5.29.31') { $cdp = @([regex]::Matches([string]$e.Format($false), 'URL=(\S+)') | ForEach-Object { $_.Groups[1].Value }) }
        }
        $alg = [string]$c.PublicKey.Oid.FriendlyName
        $bits = $null
        try {
            # the size comes from the exported public parameters: KeySize is write-only through the PowerShell 7 adapter on some key classes
            if ($alg -eq 'RSA') {
                $k = [System.Security.Cryptography.X509Certificates.RSACertificateExtensions]::GetRSAPublicKey($c)
                if ($k) { $bits = 8 * @($k.ExportParameters($false).Modulus).Length; $k.Dispose() }
            }
            else {
                $k = [System.Security.Cryptography.X509Certificates.ECDsaCertificateExtensions]::GetECDsaPublicKey($c)
                if ($k) { $bits = 8 * @($k.ExportParameters($false).Q.X).Length; $k.Dispose() }
            }
        } catch { [void]$errors.Add("Key size of $($c.Thumbprint): $($_.Exception.Message)") }
        [void]$list.Add([pscustomobject]@{
                Subject            = [string]$c.Subject
                Issuer             = [string]$c.Issuer
                Thumbprint         = [string]$c.Thumbprint
                NotBefore          = $c.NotBefore.ToUniversalTime().ToString('o')
                NotAfter           = $c.NotAfter.ToUniversalTime().ToString('o')
                KeyAlgorithm       = $alg
                KeySize            = $bits
                SignatureAlgorithm = [string]$c.SignatureAlgorithm.FriendlyName
                SignatureOid       = [string]$c.SignatureAlgorithm.Value
                HasPrivateKey      = [bool]$c.HasPrivateKey
                Ekus               = @($ekus)
                San                = $san
                TemplateName       = $tplName
                TemplateInfo       = $tplInfo
                CdpUrls            = @($cdp)
            })
    }
    [pscustomobject]@{
        ComputerName = [string]$env:COMPUTERNAME
        CollectedAt  = [datetime]::UtcNow.ToString('o')
        Certificates = @($list)
        Errors       = @($errors)
    }
}

# ---------------------------------------------------------------------------------------------------------------
# Collector 2: the CA (runs ON the CA; read-only; self-contained)
# ---------------------------------------------------------------------------------------------------------------

$script:CaCollector = {
    $ErrorActionPreference = 'Stop'
    $errors = New-Object System.Collections.ArrayList
    $enrollGuid = [guid]'0e10c968-78fb-11d2-90d4-00c04f79dc55'
    $svc = $null
    try { $svc = [string](Get-Service -Name CertSvc).Status } catch { [void]$errors.Add("CertSvc: $($_.Exception.Message)") }

    $caCert = $null
    try {
        $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ('ca-' + [guid]::NewGuid().ToString('N') + '.cer')
        & certutil.exe -ca.cert $tmp | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "certutil -ca.cert exited with $LASTEXITCODE" }
        $x = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2 -ArgumentList $tmp
        Remove-Item -LiteralPath $tmp -Force
        $alg = [string]$x.PublicKey.Oid.FriendlyName
        $bits = $null
        if ($alg -eq 'RSA') { $k = [System.Security.Cryptography.X509Certificates.RSACertificateExtensions]::GetRSAPublicKey($x); $bits = 8 * @($k.ExportParameters($false).Modulus).Length; $k.Dispose() }
        $caCert = [pscustomobject]@{
            Subject = [string]$x.Subject; Name = [string]$x.GetNameInfo('SimpleName', $false); Thumbprint = [string]$x.Thumbprint
            NotAfter = $x.NotAfter.ToUniversalTime().ToString('o'); KeyAlgorithm = $alg; KeySize = $bits
            SignatureAlgorithm = [string]$x.SignatureAlgorithm.FriendlyName; SignatureOid = [string]$x.SignatureAlgorithm.Value
        }
    } catch { [void]$errors.Add("CA certificate: $($_.Exception.Message)") }

    # newest base CRL in the CertEnroll folder; certutil prints NextUpdate in the language of the server
    $crl = $null
    try {
        $dir = Join-Path $env:SystemRoot 'System32\CertSrv\CertEnroll'
        $f = Get-ChildItem -LiteralPath $dir -Filter '*.crl' | Where-Object { $_.Name -notlike '*+.crl' } | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($f) {
            $dump = @(& certutil.exe -dump $f.FullName)
            $next = $dump | Select-String -Pattern '^\s*NextUpdate:\s*(.+)$' | Select-Object -First 1
            if (-not $next) { throw "No NextUpdate line in the certutil -dump output of $($f.Name) (is the server not in English?)" }
            $when = [datetime]::Parse($next.Matches[0].Groups[1].Value.Trim(), [System.Globalization.CultureInfo]::CurrentCulture)
            $crl = [pscustomobject]@{ File = [string]$f.Name; NextUpdate = $when.ToUniversalTime().ToString('o') }
        }
    } catch { [void]$errors.Add("CRL: $($_.Exception.Message)") }

    $cdps = @()
    try {
        $cdps = @(Get-CACrlDistributionPoint | ForEach-Object {
                [pscustomobject]@{
                    Uri = [string]$_.Uri; PublishToServer = [bool]$_.PublishToServer; PublishDeltaToServer = [bool]$_.PublishDeltaToServer
                    AddToCertificateCdp = [bool]$_.AddToCertificateCdp; AddToFreshestCrl = [bool]$_.AddToFreshestCrl
                    AddToCrlCdp = [bool]$_.AddToCrlCdp; AddToCrlIdp = [bool]$_.AddToCrlIdp
                } })
    } catch { [void]$errors.Add("Get-CACrlDistributionPoint: $($_.Exception.Message)") }

    $templates = New-Object System.Collections.ArrayList
    try {
        $cfg = [string]([ADSI]'LDAP://RootDSE').Properties['configurationNamingContext'][0]
        foreach ($t in @(Get-CATemplate)) {
            $n = [string]$t.Name
            try {
                $e = [ADSI]"LDAP://CN=$n,CN=Certificate Templates,CN=Public Key Services,CN=Services,$cfg"
                $p = $e.Properties
                $enroll = New-Object System.Collections.ArrayList
                foreach ($r in $e.ObjectSecurity.GetAccessRules($true, $true, [System.Security.Principal.NTAccount])) {
                    if ([string]$r.AccessControlType -ne 'Allow') { continue }
                    $rights = [string]$r.ActiveDirectoryRights
                    $isEnroll = ($rights -match 'GenericAll') -or (($rights -match 'ExtendedRight') -and ($r.ObjectType -eq $enrollGuid -or $r.ObjectType -eq [guid]::Empty))
                    if ($isEnroll) { [void]$enroll.Add([string]$r.IdentityReference.Value) }
                }
                [void]$templates.Add([pscustomobject]@{
                        Name = $n
                        NameFlags = [int]$p['msPKI-Certificate-Name-Flag'].Value
                        EnrollmentFlags = [int]$p['msPKI-Enrollment-Flag'].Value
                        RaSignatures = [int]$p['msPKI-RA-Signature'].Value
                        Ekus = @($p['pKIExtendedKeyUsage'] | ForEach-Object { [string]$_ })
                        EnrollPrincipals = @($enroll | Select-Object -Unique)
                    })
            } catch { [void]$errors.Add("Template ${n}: $($_.Exception.Message)") }
        }
    } catch { [void]$errors.Add("Templates: $($_.Exception.Message)") }

    [pscustomobject]@{
        ComputerName = [string]$env:COMPUTERNAME
        CollectedAt  = [datetime]::UtcNow.ToString('o')
        Service      = $svc
        CaCertificate = $caCert
        Crl          = $crl
        Cdp          = @($cdps)
        Templates    = @($templates)
        Errors       = @($errors)
    }
}

function Get-CertCollectorScript { $script:CertCollector }
function Get-CaCollectorScript { $script:CaCollector }

function Get-CertFacts {
    <# Machine certificates from each computer over WinRM, and the CA facts from the CA. Read-only. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [string[]] $ComputerName, [string] $CaServer, [pscredential] $Credential)
    $p = @{ ComputerName = $ComputerName; ScriptBlock = $script:CertCollector; ErrorAction = 'Stop' }
    if ($Credential) { $p.Credential = $Credential }
    $hosts = @(Invoke-Command @p | ForEach-Object { $_ | Select-Object -Property * -ExcludeProperty PSComputerName, RunspaceId, PSShowComputerName })
    $ca = $null
    if ($CaServer) {
        $q = @{ ComputerName = $CaServer; ScriptBlock = $script:CaCollector; ErrorAction = 'Stop' }
        if ($Credential) { $q.Credential = $Credential }
        $ca = Invoke-Command @q | Select-Object -Property * -ExcludeProperty PSComputerName, RunspaceId, PSShowComputerName
    }
    [pscustomobject]@{ Hosts = $hosts; Ca = $ca }
}

# ---------------------------------------------------------------------------------------------------------------
# Rules (pure)
# ---------------------------------------------------------------------------------------------------------------

function Get-CertTemplateName {
    <# The v1 extension gives the name; the v2 extension prints as "Template=<name>(<oid>), Major Version Number=..." #>
    param($Certificate)
    $n = Get-CertProp $Certificate 'TemplateName'
    if ($n) { return [string]$n }
    $i = [string](Get-CertProp $Certificate 'TemplateInfo' '')
    if ($i -match 'Template=(.+?)\s*\(') { return $Matches[1].Trim() }
    $null
}

function Test-CertHost {
    [CmdletBinding()]
    param([Parameter(Mandatory)] $Facts, [Parameter(Mandatory)] $Config, [datetime] $Now = [datetime]::UtcNow)
    $out = New-Object System.Collections.ArrayList
    $pol = $Config.Policy
    $host_ = [string]$Facts.ComputerName
    $warn = [int]$pol.CertWarnDays; $crit = [int]$pol.CertCriticalDays; $minBits = [int]$pol.MinRsaKeyBits
    foreach ($c in @(Get-CertProp $Facts 'Certificates' @())) {
        $subj = [string]$c.Subject
        $tag = "$subj [$(([string]$c.Thumbprint).Substring(0, [Math]::Min(8, ([string]$c.Thumbprint).Length)))]"
        $left = [int][Math]::Floor(((ConvertTo-CertUtc $c.NotAfter) - $Now.ToUniversalTime()).TotalDays)
        if ($left -lt 0) {
            [void]$out.Add((New-CertFinding $host_ High 'CertExpired' "$tag expired $(-$left) day(s) ago." 'Renew'))
        }
        elseif ($left -lt $crit) {
            [void]$out.Add((New-CertFinding $host_ High 'CertExpiring' "$tag expires in $left day(s) (critical below $crit)." 'Renew'))
        }
        elseif ($left -lt $warn) {
            [void]$out.Add((New-CertFinding $host_ Medium 'CertExpiring' "$tag expires in $left day(s) (warning below $warn)." 'Renew'))
        }
        $sigOid = [string](Get-CertProp $c 'SignatureOid' '')
        $weak = @($pol.WeakSignatureAlgorithms)
        if ($script:WeakSignatureOids.ContainsKey($sigOid) -or $weak -contains [string](Get-CertProp $c 'SignatureAlgorithm' '')) {
            [void]$out.Add((New-CertFinding $host_ High 'CertWeakSignature' "$tag is signed with $(Get-CertProp $c 'SignatureAlgorithm' $sigOid): an SHA-1 or MD5 signature is not acceptable for a new certificate."))
        }
        if ((Get-CertProp $c 'KeyAlgorithm') -eq 'RSA' -and $null -ne (Get-CertProp $c 'KeySize') -and [int]$c.KeySize -lt $minBits) {
            [void]$out.Add((New-CertFinding $host_ High 'CertWeakKey' "$tag has an RSA key of $($c.KeySize) bits (policy: at least $minBits)."))
        }
        $self = ([string]$c.Subject -eq [string]$c.Issuer)
        $isOurCa = $self -and ([string]$c.Subject -like "*CN=$($Config.Ca.CommonName)*")   # a root CA is self-signed by definition
        if ($self -and -not $isOurCa) {
            [void]$out.Add((New-CertFinding $host_ Low 'CertSelfSigned' "$tag is self-signed: nobody else can chain it to a trusted root."))
        }
        $ekus = @(Get-CertProp $c 'Ekus' @())
        if (-not [bool](Get-CertProp $c 'HasPrivateKey' $true) -and $ekus -contains $script:ServerAuthEku) {
            [void]$out.Add((New-CertFinding $host_ Low 'CertNoPrivateKey' "$tag is a server authentication certificate without a private key on this machine."))
        }
        $tpl = Get-CertTemplateName $c
        if ($tpl -and -not $self -and [bool](Get-CertProp $pol 'RequireHttpCdp' $true)) {
            $http = @(Get-CertProp $c 'CdpUrls' @()) | Where-Object { $_ -match '^http://' }
            if (-not $http) {
                [void]$out.Add((New-CertFinding $host_ Medium 'CertNoHttpCdp' "$tag (template $tpl) has no HTTP CRL distribution point. Learn: publish an HTTP location so clients outside the domain and non-Windows clients can check revocation."))
            }
        }
    }
    foreach ($e in @(Get-CertProp $Facts 'Errors' @())) { [void]$out.Add((New-CertFinding $host_ Info 'CollectorError' ([string]$e))) }
    @($out | Sort-Object { $script:Severity[$_.Severity] }, Check)
}

function Test-CaTemplate {
    <# Pure. Can a requester choose WHO the certificate says it is, for a purpose that signs someone in? #>
    param([Parameter(Mandatory)] $Template, [Parameter(Mandatory)] $Config, [string] $Target)
    $pol = $Config.Policy
    $name = [string]$Template.Name
    $flags = [int]$Template.NameFlags
    $suppliesIdentity = (($flags -band $script:SubjectNameEnrolleeSupplies) -ne 0) -or (($flags -band $script:SanEnrolleeSupplies) -ne 0)
    if (-not $suppliesIdentity) { return @() }
    $auth = @{}
    foreach ($p in $pol.AuthenticationEkus.PSObject.Properties) { $auth[$p.Name] = $p.Value }
    $ekus = @(Get-CertProp $Template 'Ekus' @())
    $signsIn = ($ekus.Count -eq 0) -or (@($ekus | Where-Object { $auth.ContainsKey($_) }).Count -gt 0)
    if (-not $signsIn) { return @() }
    $needsApproval = (([int]$Template.EnrollmentFlags -band $script:EnrollmentPendAllRequests) -ne 0) -or ([int]$Template.RaSignatures -gt 0)
    $broadNames = @($pol.BroadEnrollPrincipals)
    $broad = @(@(Get-CertProp $Template 'EnrollPrincipals' @()) | Where-Object {
            $short = ([string]$_) -replace '^.*\\', ''
            $broadNames -contains $short
        })
    $what = if ($ekus.Count -eq 0) { 'no EKU (usable for any purpose)' } else { 'an EKU that can sign someone in' }
    if ($broad.Count -gt 0 -and -not $needsApproval) {
        return , (New-CertFinding $Target High 'TemplateSuppliesIdentity' "Template '$name': the requester supplies the subject or subject alternative name (Learn: SubjectNameEnrolleeSupplies), the certificate has $what, nobody approves, and $($broad -join ', ') can enroll. Anyone in that group can ask for a certificate that names someone else.")
    }
    $why = if ($needsApproval) { 'requests need approval' } else { 'only named principals can enroll' }
    , (New-CertFinding $Target Low 'TemplateSuppliesIdentityGuarded' "Template '$name': the requester supplies the subject or subject alternative name and the certificate has $what, but $why. Keep it that way: review who may enroll.")
}

function Test-CaFacts {
    [CmdletBinding()]
    param([Parameter(Mandatory)] $CaFacts, [Parameter(Mandatory)] $Config, [datetime] $Now = [datetime]::UtcNow)
    $out = New-Object System.Collections.ArrayList
    $pol = $Config.Policy
    $n = [string]$CaFacts.ComputerName
    $nowU = $Now.ToUniversalTime()

    if ((Get-CertProp $CaFacts 'Service') -ne 'Running') {
        [void]$out.Add((New-CertFinding $n High 'CaServiceNotRunning' "The CertSvc service is '$(Get-CertProp $CaFacts 'Service' 'unknown')': nothing can be issued and no CRL is published."))
    }
    $ca = Get-CertProp $CaFacts 'CaCertificate'
    if ($ca) {
        $left = [int][Math]::Floor(((ConvertTo-CertUtc $ca.NotAfter) - $nowU).TotalDays)
        if ($left -lt 0) { [void]$out.Add((New-CertFinding $n High 'CaCertificateExpired' "The CA certificate expired $(-$left) day(s) ago.")) }
        elseif ($left -lt [int]$pol.CaCertWarnDays) {
            [void]$out.Add((New-CertFinding $n Medium 'CaCertificateExpiring' "The CA certificate expires in $left day(s) (warning below $($pol.CaCertWarnDays)). Every certificate it issued stops validating on that day, so renew the CA first."))
        }
        if ($script:WeakSignatureOids.ContainsKey([string](Get-CertProp $ca 'SignatureOid' ''))) {
            [void]$out.Add((New-CertFinding $n High 'CaWeakSignature' "The CA certificate is signed with $($ca.SignatureAlgorithm)."))
        }
        if ((Get-CertProp $ca 'KeyAlgorithm') -eq 'RSA' -and $null -ne (Get-CertProp $ca 'KeySize') -and [int]$ca.KeySize -lt [int]$pol.MinRsaKeyBits) {
            [void]$out.Add((New-CertFinding $n High 'CaWeakKey' "The CA key is RSA $($ca.KeySize) bits (policy: at least $($pol.MinRsaKeyBits))."))
        }
    }
    $crl = Get-CertProp $CaFacts 'Crl'
    if (-not $crl) {
        [void]$out.Add((New-CertFinding $n Medium 'CrlNotFound' 'No base CRL file was found or readable in CertEnroll (see Errors).'))
    }
    else {
        $hours = ((ConvertTo-CertUtc $crl.NextUpdate) - $nowU).TotalHours
        if ($hours -lt 0) { [void]$out.Add((New-CertFinding $n High 'CrlExpired' "The base CRL ($($crl.File)) passed its next-update time $([int][Math]::Ceiling(-$hours)) hour(s) ago: clients that need a fresh CRL will fail validation.")) }
        elseif ($hours -lt [int]$pol.CrlWarnHours) { [void]$out.Add((New-CertFinding $n Medium 'CrlExpiringSoon' "The base CRL ($($crl.File)) reaches its next-update time in $([int][Math]::Floor($hours)) hour(s) (warning below $($pol.CrlWarnHours)). Publish and copy a new one before then.")) }
    }
    $cdp = @(Get-CertProp $CaFacts 'Cdp' @())
    $inCerts = @($cdp | Where-Object { $_.AddToCertificateCdp })
    if ([bool](Get-CertProp $pol 'RequireHttpCdp' $true) -and $cdp.Count -gt 0 -and -not @($inCerts | Where-Object { $_.Uri -match '^http://' })) {
        [void]$out.Add((New-CertFinding $n Medium 'CdpNoHttp' 'No HTTP URL is added to the CRL distribution point extension of issued certificates. Learn: publish an HTTP CRL location so clients outside the organization and non-Windows clients can validate certificates.' 'HttpCdp'))
    }
    foreach ($d in @($inCerts | Where-Object { $_.Uri -match '^(\\\\|[A-Za-z]:\\|file:)' })) {
        [void]$out.Add((New-CertFinding $n Medium 'CdpLocalPathInCertificates' "A local or UNC path ($($d.Uri)) is added to issued certificates as a distribution point. Learn: don't assume a local folder or UNC path is suitable as a client-facing CDP."))
    }
    $tpls = @(Get-CertProp $CaFacts 'Templates' @())
    if ($tpls.Count -eq 0) {
        [void]$out.Add((New-CertFinding $n Info 'NoTemplatesRead' 'No published template could be read. An enterprise CA with no templates issues nothing (Learn: CAPolicy.inf LoadDefaultTemplates).'))
    }
    foreach ($t in $tpls) { foreach ($f in @(Test-CaTemplate -Template $t -Config $Config -Target $n)) { [void]$out.Add($f) } }
    foreach ($e in @(Get-CertProp $CaFacts 'Errors' @())) { [void]$out.Add((New-CertFinding $n Info 'CollectorError' ([string]$e))) }
    @($out | Sort-Object { $script:Severity[$_.Severity] }, Check)
}

function ConvertTo-CertMarkdown {
    [CmdletBinding()]
    param([object[]] $Hosts = @(), $Ca, [object[]] $Findings = @(), [datetime] $Now = [datetime]::UtcNow)
    $sb = New-Object System.Text.StringBuilder
    [void]$sb.AppendLine('# Certificate check')
    [void]$sb.AppendLine()
    [void]$sb.AppendLine('## Certificates in the machine store')
    [void]$sb.AppendLine()
    [void]$sb.AppendLine('| Server | Subject | Template | Not after (UTC) | Days left | Key | Signature | CDP http |')
    [void]$sb.AppendLine('|---|---|---|---|---|---|---|---|')
    foreach ($h in $Hosts) {
        foreach ($c in @(Get-CertProp $h 'Certificates' @())) {
            $left = [int][Math]::Floor(((ConvertTo-CertUtc $c.NotAfter) - $Now.ToUniversalTime()).TotalDays)
            $tpl = Get-CertTemplateName $c
            $http = if (@(Get-CertProp $c 'CdpUrls' @()) | Where-Object { $_ -match '^http://' }) { 'yes' } else { 'no' }
            [void]$sb.AppendLine(('| {0} | {1} | {2} | {3:yyyy-MM-dd} | {4} | {5} {6} | {7} | {8} |' -f $h.ComputerName, ($c.Subject -replace '\|', '/'), $(if ($tpl) { $tpl } else { '-' }),
                    (ConvertTo-CertUtc $c.NotAfter), $left, $c.KeyAlgorithm, $c.KeySize, $c.SignatureAlgorithm, $http))
        }
    }
    if ($Ca) {
        [void]$sb.AppendLine()
        [void]$sb.AppendLine('## The CA')
        [void]$sb.AppendLine()
        $cc = Get-CertProp $Ca 'CaCertificate'
        [void]$sb.AppendLine("- Server: **$($Ca.ComputerName)**, CertSvc: **$(Get-CertProp $Ca 'Service' 'unknown')**")
        if ($cc) { [void]$sb.AppendLine(('- CA certificate: {0}, {1} {2}, {3}, not after {4:yyyy-MM-dd}' -f $cc.Name, $cc.KeyAlgorithm, $cc.KeySize, $cc.SignatureAlgorithm, (ConvertTo-CertUtc $cc.NotAfter))) }
        $crl = Get-CertProp $Ca 'Crl'
        if ($crl) { [void]$sb.AppendLine(('- Base CRL: {0}, next update {1:yyyy-MM-dd HH:mm} UTC' -f $crl.File, (ConvertTo-CertUtc $crl.NextUpdate))) }
        foreach ($d in @(Get-CertProp $Ca 'Cdp' @())) {
            [void]$sb.AppendLine(('- CDP: `{0}` publish={1} in-certificates={2}' -f $d.Uri, $d.PublishToServer, $d.AddToCertificateCdp))
        }
        $tp = @(Get-CertProp $Ca 'Templates' @())
        if ($tp.Count) { [void]$sb.AppendLine("- Published templates: $(($tp | ForEach-Object { $_.Name }) -join ', ')") }
    }
    [void]$sb.AppendLine()
    [void]$sb.AppendLine('## Findings')
    [void]$sb.AppendLine()
    if (-not @($Findings).Count) { [void]$sb.AppendLine('None.') }
    else {
        [void]$sb.AppendLine('| Severity | Target | Check | Message |')
        [void]$sb.AppendLine('|---|---|---|---|')
        foreach ($x in $Findings) { [void]$sb.AppendLine(('| {0} | {1} | {2} | {3} |' -f $x.Severity, $x.Target, $x.Check, ($x.Message -replace '\|', '/'))) }
    }
    $sb.ToString()
}

# ---------------------------------------------------------------------------------------------------------------
# Renewal: plan (pure), then apply with -WhatIf
# ---------------------------------------------------------------------------------------------------------------

function Get-CertRenewalPlan {
    <# One step per expired or expiring certificate. A template name makes it an Enroll step (Get-Certificate); no template means Manual. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [object[]] $Hosts, [Parameter(Mandatory)] [object[]] $Findings, [datetime] $Now = [datetime]::UtcNow)
    $steps = New-Object System.Collections.ArrayList
    foreach ($h in $Hosts) {
        $hit = @($Findings | Where-Object { $_.Target -eq $h.ComputerName -and $_.Check -in 'CertExpired', 'CertExpiring' })
        if (-not $hit.Count) { continue }
        foreach ($c in @(Get-CertProp $h 'Certificates' @())) {
            $tag = ([string]$c.Thumbprint).Substring(0, [Math]::Min(8, ([string]$c.Thumbprint).Length))
            if (-not @($hit | Where-Object { $_.Message -like "*[[]$tag]*" }).Count) { continue }
            $tpl = Get-CertTemplateName $c
            $left = [int][Math]::Floor(((ConvertTo-CertUtc $c.NotAfter) - $Now.ToUniversalTime()).TotalDays)
            $self = ([string]$c.Subject -eq [string]$c.Issuer)
            if ($tpl -and -not $self) {
                [void]$steps.Add([pscustomobject]@{ Target = [string]$h.ComputerName; Kind = 'Enroll'; Subject = [string]$c.Subject; Thumbprint = [string]$c.Thumbprint; DaysLeft = $left; Template = $tpl
                        Command = "Get-Certificate -Template '$tpl' -CertStoreLocation Cert:\LocalMachine\My"; Why = "Issued from template ${tpl}: request a new one from the enterprise CA. The old one stays in the store until you remove it." })
            }
            else {
                $why = if ($self) { 'Self-signed: whoever created it has to create a new one (and update what trusts it).' } else { 'No template name in the certificate: find out who requested it and how before renewing.' }
                [void]$steps.Add([pscustomobject]@{ Target = [string]$h.ComputerName; Kind = 'Manual'; Subject = [string]$c.Subject; Thumbprint = [string]$c.Thumbprint; DaysLeft = $left; Template = $null; Command = ''; Why = $why })
            }
        }
    }
    @($steps | Sort-Object DaysLeft)
}

function Invoke-CertRenewal {
    <# Runs the Enroll steps (Get-Certificate on the server that owns the certificate). Manual steps are never run. Honors -WhatIf. #>
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)] [object[]] $Plan, [pscredential] $Credential)
    foreach ($s in $Plan) {
        if ($s.Kind -ne 'Enroll') { [pscustomobject]@{ Target = $s.Target; Thumbprint = $s.Thumbprint; Result = 'Manual'; Detail = $s.Why }; continue }
        if (-not $PSCmdlet.ShouldProcess($s.Target, "Get-Certificate -Template $($s.Template) (replaces $($s.Thumbprint))")) { continue }
        $p = @{ ComputerName = $s.Target; ErrorAction = 'Stop'; ArgumentList = @($s.Template)
            ScriptBlock = { param($t) $r = Get-Certificate -Template $t -CertStoreLocation Cert:\LocalMachine\My; [pscustomobject]@{ Status = [string]$r.Status; Thumbprint = [string]$r.Certificate.Thumbprint } } }
        if ($Credential) { $p.Credential = $Credential }
        try { $r = Invoke-Command @p; [pscustomobject]@{ Target = $s.Target; Thumbprint = $s.Thumbprint; Result = [string]$r.Status; Detail = "new certificate $($r.Thumbprint)" } }
        catch { [pscustomobject]@{ Target = $s.Target; Thumbprint = $s.Thumbprint; Result = 'Failed'; Detail = $_.Exception.Message } }
    }
}

# ---------------------------------------------------------------------------------------------------------------
# Build the CA: a plan (pure) and an apply function. Step 'Install' writes to Active Directory (an enterprise CA is
# integrated with AD DS, Learn), so it needs -AllowCaInstall.
# ---------------------------------------------------------------------------------------------------------------

function Get-CertCaPlan {
    [CmdletBinding()]
    param([Parameter(Mandatory)] $Config, [ValidateSet('Ca', 'Http')] [string] $Step = 'Ca')
    $c = $Config.Ca
    $steps = New-Object System.Collections.ArrayList
    $add = { param($id, $desc, $irreversible, $script) [void]$steps.Add([pscustomobject]@{ Id = $id; Description = $desc; Irreversible = $irreversible; Script = $script }) }
    if ($Step -eq 'Ca') {
        & $add 'Features' 'Install the CA role service, IIS and the IIS scripting tools (the CRL is served over HTTP)' $false 'Install-WindowsFeature -Name ADCS-Cert-Authority, Web-Server, Web-Scripting-Tools -IncludeManagementTools | Out-Null'
        & $add 'Install' "Configure an enterprise root CA '$($c.CommonName)' (RSA $($c.KeyLength), $($c.HashAlgorithm), $($c.ValidityPeriodUnits) $($c.ValidityPeriod)); writes to Active Directory" $true @"
`$p = @{
    CAType              = 'EnterpriseRootCa'
    CACommonName        = '$($c.CommonName)'
    CryptoProviderName  = '$($c.CryptoProvider)'
    KeyLength           = $($c.KeyLength)
    HashAlgorithmName   = '$($c.HashAlgorithm)'
    ValidityPeriod      = '$($c.ValidityPeriod)'
    ValidityPeriodUnits = $($c.ValidityPeriodUnits)
    Force               = `$true
}
Install-AdcsCertificationAuthority @p | Out-Null
"@
        & $add 'CrlPeriods' "Base CRL every $($c.CrlPeriodUnits) $($c.CrlPeriod), delta CRL every $($c.CrlDeltaPeriodUnits) $($c.CrlDeltaPeriod), then restart CertSvc" $false @"
certutil.exe -setreg CA\CRLPeriod $($c.CrlPeriod) | Out-Null
certutil.exe -setreg CA\CRLPeriodUnits $($c.CrlPeriodUnits) | Out-Null
certutil.exe -setreg CA\CRLDeltaPeriod $($c.CrlDeltaPeriod) | Out-Null
certutil.exe -setreg CA\CRLDeltaPeriodUnits $($c.CrlDeltaPeriodUnits) | Out-Null
Restart-Service -Name CertSvc
"@
    }
    else {
        $uri = "http://$($c.HttpCdpHost)/$($c.HttpCdpPath)/<CAName><CRLNameSuffix><DeltaCRLAllowed>.crl"
        & $add 'WebDirectory' "Serve the CertEnroll folder as http://$($c.HttpCdpHost)/$($c.HttpCdpPath) (lab shortcut: the CA also hosts its own CRL)" $false @"
Import-Module WebAdministration
if (-not (Get-WebVirtualDirectory -Site 'Default Web Site' -Name '$($c.HttpCdpPath)')) { New-WebVirtualDirectory -Site 'Default Web Site' -Name '$($c.HttpCdpPath)' -PhysicalPath (Join-Path `$env:SystemRoot 'System32\CertSrv\CertEnroll') | Out-Null }
"@
        & $add 'Cdp' "Add $uri to issued certificates and to the freshest-CRL extension (Learn: Add-CACrlDistributionPoint)" $false @"
`$have = @(Get-CACrlDistributionPoint | Where-Object { `$_.Uri -eq '$uri' -and `$_.AddToCertificateCdp })
if (-not `$have) { Add-CACrlDistributionPoint -Uri '$uri' -AddToCertificateCdp -AddToFreshestCrl -Force | Out-Null }
"@
        & $add 'Publish' 'Restart CertSvc and publish new CRLs (certutil -CRL)' $false @'
Restart-Service -Name CertSvc
Start-Sleep -Seconds 5
certutil.exe -CRL | Out-Null
'@
    }
    $steps
}

function Invoke-CertCaPlan {
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)] [object[]] $Plan, [Parameter(Mandatory)] [string] $ComputerName, [pscredential] $Credential, [switch] $AllowCaInstall)
    foreach ($s in $Plan) {
        if ($s.Irreversible -and -not $AllowCaInstall) {
            [pscustomobject]@{ Id = $s.Id; Result = 'Skipped'; Detail = 'Writes to Active Directory: run again with -AllowCaInstall. The steps after it are not run either.' }
            break
        }
        if (-not $PSCmdlet.ShouldProcess($ComputerName, $s.Description)) { continue }
        $p = @{ ComputerName = $ComputerName; ScriptBlock = [scriptblock]::Create($s.Script); ErrorAction = 'Stop' }
        if ($Credential) { $p.Credential = $Credential }
        try { Invoke-Command @p | Out-Null; [pscustomobject]@{ Id = $s.Id; Result = 'Done'; Detail = '' } }
        catch { [pscustomobject]@{ Id = $s.Id; Result = 'Failed'; Detail = $_.Exception.Message }; break }
    }
}

Export-ModuleMember -Function Read-CertLabConfig, Get-CertCollectorScript, Get-CaCollectorScript, Get-CertFacts, Get-CertTemplateName, Test-CertHost, Test-CaTemplate, Test-CaFacts, ConvertTo-CertMarkdown, Get-CertRenewalPlan, Invoke-CertRenewal, Get-CertCaPlan, Invoke-CertCaPlan
