using namespace System.Management.Automation.Language
using namespace System.Security.Cryptography
using namespace System.Security.Cryptography.X509Certificates

BeforeAll {
    $script:Src = Join-Path $PSScriptRoot '../src'
    $script:Fixtures = Join-Path $PSScriptRoot 'fixtures'
    Import-Module (Join-Path $script:Src 'CertLab/CertLab.psd1') -Force
    $script:ConfigPath = Join-Path $script:Src 'cert-lab.json'
    $script:Config = Read-CertLabConfig -Path $script:ConfigPath
    $script:Now = [datetime]::Parse('2026-11-21T09:00:00Z', [cultureinfo]::InvariantCulture, [System.Globalization.DateTimeStyles]::AdjustToUniversal)
    function Get-Facts([string] $Name) { Get-Content -Raw (Join-Path $script:Fixtures "facts-$Name.json") | ConvertFrom-Json }
    function Get-ConfigCopy { Get-Content -Raw $script:ConfigPath | ConvertFrom-Json }
    function Test-Facts($Facts) {
        $f = @(); foreach ($h in @($Facts.Hosts)) { $f += @(Test-CertHost -Facts $h -Config $script:Config -Now $script:Now) }
        if ($Facts.Ca) { $f += @(Test-CaFacts -CaFacts $Facts.Ca -Config $script:Config -Now $script:Now) }
        , @($f | Sort-Object @{ Expression = { @{ High = 0; Medium = 1; Low = 2; Info = 3 }[$_.Severity] } }, Target, Check)
    }
    function Get-Checks($Findings, [string] $Target) { @($Findings | Where-Object { $_.Target -eq $Target } | ForEach-Object Check) }
    function New-Tpl($Name = 'T', $NameFlags = 0, $EnrollFlags = 0, $Ra = 0, $Ekus = @('1.3.6.1.5.5.7.3.2'), $Principals = @('CONTOSO\Domain Users')) {
        [pscustomobject]@{ Name = $Name; NameFlags = $NameFlags; EnrollmentFlags = $EnrollFlags; RaSignatures = $Ra; Ekus = $Ekus; EnrollPrincipals = $Principals }
    }
    # Real X509 certificates, generated here (no store, no CA): the collector code runs on them for real
    function New-TestCert([string] $Cn, [int] $Bits = 2048, [string] $Hash = 'SHA256', [datetime] $NotBefore, [datetime] $NotAfter, [string] $TemplateV1, [string[]] $Eku, [string[]] $Dns) {
        $rsa = [RSA]::Create($Bits)
        $req = [CertificateRequest]::new("CN=$Cn", $rsa, [HashAlgorithmName]::$Hash, [RSASignaturePadding]::Pkcs1)
        if ($Eku) {
            $oids = [OidCollection]::new(); foreach ($e in $Eku) { [void]$oids.Add([Oid]::new($e)) }
            $req.CertificateExtensions.Add([X509EnhancedKeyUsageExtension]::new($oids, $false))
        }
        if ($Dns) { $b = [SubjectAlternativeNameBuilder]::new(); foreach ($d in $Dns) { $b.AddDnsName($d) }; $req.CertificateExtensions.Add($b.Build()) }
        if ($TemplateV1) {
            $u = [System.Text.Encoding]::BigEndianUnicode.GetBytes($TemplateV1)
            $der = [byte[]](@(0x1E, $u.Length) + $u)
            $req.CertificateExtensions.Add([X509Extension]::new('1.3.6.1.4.1.311.20.2', $der, $false))
        }
        $req.CreateSelfSigned([DateTimeOffset]$NotBefore, [DateTimeOffset]$NotAfter)
    }
}

Describe 'Read-CertLabConfig' {
    It 'reads the lab config' {
        $script:Config.Ca.Server | Should -Be 'CON-CA01'
        @($script:Config.Targets).Count | Should -Be 6
    }
    It 'rejects bad values' {
        $f = Join-Path $TestDrive 'c.json'
        $c = Get-ConfigCopy; $c.Policy.CertCriticalDays = 60; $c | ConvertTo-Json -Depth 6 | Set-Content $f
        { Read-CertLabConfig -Path $f } | Should -Throw '*smaller than*'
        $c = Get-ConfigCopy; $c.Policy.MinRsaKeyBits = 1024; $c | ConvertTo-Json -Depth 6 | Set-Content $f
        { Read-CertLabConfig -Path $f } | Should -Throw '*2048*'
        $c = Get-ConfigCopy; $c.Ca.CrlPeriod = 'Fortnights'; $c | ConvertTo-Json -Depth 6 | Set-Content $f
        { Read-CertLabConfig -Path $f } | Should -Throw '*Ca.CrlPeriod*'
        $c = Get-ConfigCopy; $c.Targets += $c.Targets[0]; $c | ConvertTo-Json -Depth 6 | Set-Content $f
        { Read-CertLabConfig -Path $f } | Should -Throw '*Duplicate*CON-DC01*'
    }
}

Describe 'The certificate collector, run on real X509 certificates' {
    BeforeAll {
        $good = New-TestCert -Cn 'web.lab.contoso.com' -NotBefore $script:Now.AddDays(-10) -NotAfter $script:Now.AddDays(355) -TemplateV1 'WebServer' -Eku @('1.3.6.1.5.5.7.3.1', '1.3.6.1.5.5.7.3.2') -Dns @('web.lab.contoso.com')
        $old = New-TestCert -Cn 'legacy' -Bits 1024 -Hash 'SHA384' -NotBefore $script:Now.AddDays(-2000) -NotAfter $script:Now.AddDays(-41)
        $script:Facts = & (Get-CertCollectorScript) -Certificates @($good, $old)
        $script:Good = $script:Facts.Certificates | Where-Object Subject -eq 'CN=web.lab.contoso.com'
        $script:Old = $script:Facts.Certificates | Where-Object Subject -eq 'CN=legacy'
    }
    It 'returns one fact per certificate' { @($script:Facts.Certificates).Count | Should -Be 2 }
    It 'reads key, signature, validity and private key' {
        $script:Good.KeyAlgorithm | Should -Be 'RSA'
        $script:Good.KeySize | Should -Be 2048
        $script:Good.SignatureOid | Should -Be '1.2.840.113549.1.1.11'
        $script:Good.HasPrivateKey | Should -BeTrue
        ([datetime]::Parse($script:Good.NotAfter, [cultureinfo]::InvariantCulture, 'RoundtripKind') - $script:Now.AddDays(355)).TotalMinutes | Should -BeLessThan 2
    }
    It 'reads EKUs and the subject alternative name' {
        @($script:Good.Ekus) | Should -Contain '1.3.6.1.5.5.7.3.1'
        $script:Good.San | Should -Match 'web.lab.contoso.com'
    }
    It 'decodes the v1 template name (a DER BMPString)' { $script:Good.TemplateName | Should -Be 'WebServer' }
    It 'sees the signature algorithm and a 1024-bit key' {
        $script:Old.SignatureOid | Should -Be '1.2.840.113549.1.1.12'   # sha384RSA; this OpenSSL refuses to SIGN with SHA-1, so SHA-1 is covered by the fixtures
        $script:Old.KeySize | Should -Be 1024
    }
    It 'feeds the rules end to end' {
        $f = @(Test-CertHost -Facts $script:Facts -Config $script:Config -Now $script:Now)
        (Get-Checks $f $script:Facts.ComputerName) | Should -Contain 'CertExpired'
        (Get-Checks $f $script:Facts.ComputerName) | Should -Contain 'CertWeakKey'
        @($f | Where-Object { $_.Message -like '*web.lab*' -and $_.Severity -in 'High', 'Medium' }).Count | Should -Be 0
    }
    It 'accepts an empty store' {
        $e = & (Get-CertCollectorScript) -Certificates @()
        @($e.Certificates).Count | Should -Be 0
    }
}

Describe 'The collectors are read-only and Windows PowerShell 5.1 safe' {
    BeforeAll {
        $script:Asts = @{ Cert = [Parser]::ParseInput((Get-CertCollectorScript).ToString(), [ref]$null, [ref]$null); Ca = [Parser]::ParseInput((Get-CaCollectorScript).ToString(), [ref]$null, [ref]$null) }
    }
    It 'uses no PowerShell 7 only syntax (<_>)' -ForEach 'Cert', 'Ca' {
        $a = $script:Asts[$_]
        @($a.FindAll({ param($n) $n -is [TernaryExpressionAst] -or $n -is [PipelineChainAst] }, $true)).Count | Should -Be 0
        $a.ToString() | Should -Not -Match '\?\?|\?\.\w|\?\['
    }
    It 'calls no command that changes state (<_>)' -ForEach 'Cert', 'Ca' {
        $a = $script:Asts[$_]
        $cmds = @($a.FindAll({ param($n) $n -is [CommandAst] }, $true) | ForEach-Object { $_.GetCommandName() } | Where-Object { $_ })
        @($cmds | Where-Object { $_ -match '^(Set|Add|Remove|New|Install|Uninstall|Restart|Start|Stop|Enable|Disable|Revoke|Publish|Import|Clear)-' -and $_ -notin 'New-Object', 'Remove-Item' }).Count | Should -Be 0
    }
    It 'only deletes its own temporary CA certificate file' {
        $a = $script:Asts['Ca']
        $rm = @($a.FindAll({ param($n) $n -is [CommandAst] -and $n.GetCommandName() -eq 'Remove-Item' }, $true))
        $rm.Count | Should -Be 1
        $rm[0].ToString() | Should -Match '\$tmp'
    }
    It 'passes only read verbs of certutil' {
        $t = (Get-CaCollectorScript).ToString()
        $t | Should -Match '-ca\.cert'
        $t | Should -Match '-dump'
        $t | Should -Not -Match '-setreg|-revoke|-CRL\b|-resubmit|-deny'
    }
}

Describe 'Test-CertHost on the lab before the fixes' {
    BeforeAll { $script:Before = Get-Facts 'before'; $script:BeforeF = Test-Facts $script:Before }
    It 'finds 11 things, 6 High' {
        @($script:BeforeF).Count | Should -Be 11
        @($script:BeforeF | Where-Object Severity -eq 'High').Count | Should -Be 6
    }
    It 'flags the expired, weak legacy certificate three ways' {
        (Get-Checks $script:BeforeF 'CON-SQL01') | Should -Contain 'CertExpired'
        (Get-Checks $script:BeforeF 'CON-SQL01') | Should -Contain 'CertWeakKey'
        (Get-Checks $script:BeforeF 'CON-SQL01') | Should -Contain 'CertWeakSignature'
    }
    It 'warns critical at 8 days and at 13 days, and uses the policy thresholds' {
        $x = @($script:BeforeF | Where-Object Check -eq 'CertExpiring')
        $x.Count | Should -Be 2
        ($x | Where-Object Severity -ne 'High').Count | Should -Be 0
        $y = Test-CertHost -Facts $script:Before.Hosts[2] -Config $script:Config -Now $script:Now.AddDays(-7)   # 20 days left
        ($y | Where-Object Check -eq 'CertExpiring').Severity | Should -Be 'Medium'
    }
    It 'asks for an HTTP CRL location on certificates issued with only LDAP' {
        (Get-Checks $script:BeforeF 'CON-DC01') | Should -Contain 'CertNoHttpCdp'
        (Get-Checks $script:BeforeF 'CON-SRV01') | Should -Contain 'CertNoHttpCdp'
    }
    It 'does not call the root CA certificate a self-signed problem' {
        (Get-Checks $script:BeforeF 'CON-CA01') | Should -Not -Contain 'CertSelfSigned'
        (Get-Checks $script:BeforeF 'CON-SRV02') | Should -Contain 'CertSelfSigned'
    }
    It 'sorts worst first' { $script:BeforeF[0].Severity | Should -Be 'High'; $script:BeforeF[-1].Severity | Should -Not -Be 'High' }
}

Describe 'Test-CaFacts and Test-CaTemplate' {
    It 'flags the template that lets anyone choose the subject' {
        $f = Test-Facts (Get-Facts 'before')
        $t = @($f | Where-Object Check -eq 'TemplateSuppliesIdentity')
        $t.Count | Should -Be 1
        $t[0].Severity | Should -Be 'High'
        $t[0].Message | Should -Match 'LabWebServer'
        (@($f | Where-Object Check -eq 'TemplateSuppliesIdentityGuarded')).Count | Should -Be 1
    }
    It 'treats approval, an RA signature, or a named group as a mitigation (Low, not High)' {
        $cfg = $script:Config
        (Test-CaTemplate -Template (New-Tpl -NameFlags 1 -EnrollFlags 2) -Config $cfg -Target X).Severity | Should -Be 'Low'
        (Test-CaTemplate -Template (New-Tpl -NameFlags 1 -Ra 1) -Config $cfg -Target X).Severity | Should -Be 'Low'
        (Test-CaTemplate -Template (New-Tpl -NameFlags 1 -Principals @('CONTOSO\PKI Web Admins')) -Config $cfg -Target X).Severity | Should -Be 'Low'
        (Test-CaTemplate -Template (New-Tpl -NameFlags 1) -Config $cfg -Target X).Severity | Should -Be 'High'
    }
    It 'also catches a supplied subject alternative name, and a template with no EKU' {
        $cfg = $script:Config
        (Test-CaTemplate -Template (New-Tpl -NameFlags 0x10000) -Config $cfg -Target X).Severity | Should -Be 'High'
        (Test-CaTemplate -Template (New-Tpl -NameFlags 1 -Ekus @() -Principals @('Everyone')) -Config $cfg -Target X).Check | Should -Be 'TemplateSuppliesIdentity'
    }
    It 'ignores templates that build the subject from Active Directory or cannot sign anyone in' {
        $cfg = $script:Config
        @(Test-CaTemplate -Template (New-Tpl -NameFlags 0x18000000) -Config $cfg -Target X).Count | Should -Be 0
        @(Test-CaTemplate -Template (New-Tpl -NameFlags 1 -Ekus @('1.3.6.1.5.5.7.3.1')) -Config $cfg -Target X).Count | Should -Be 0
    }
    It 'matches principals by name, whatever the domain prefix' {
        (Test-CaTemplate -Template (New-Tpl -NameFlags 1 -Principals @('NT AUTHORITY\Authenticated Users')) -Config $script:Config -Target X).Severity | Should -Be 'High'
        (Test-CaTemplate -Template (New-Tpl -NameFlags 1 -Principals @('BUILTIN\Users')) -Config $script:Config -Target X).Severity | Should -Be 'High'
    }
    It 'asks for an HTTP CDP when only LDAP and a file path exist' {
        (Get-Checks (Test-Facts (Get-Facts 'before')) 'CON-CA01') | Should -Contain 'CdpNoHttp'
    }
    It 'checks the CRL clock' {
        $ca = Get-Facts 'before'
        $f = @(Test-CaFacts -CaFacts $ca.Ca -Config $script:Config -Now $script:Now.AddDays(6.5))   # 11 h left
        ($f | Where-Object Check -eq 'CrlExpiringSoon').Severity | Should -Be 'Medium'
        $f = @(Test-CaFacts -CaFacts $ca.Ca -Config $script:Config -Now $script:Now.AddDays(8))
        ($f | Where-Object Check -eq 'CrlExpired').Severity | Should -Be 'High'
        @($f | Where-Object Check -eq 'CrlExpiringSoon').Count | Should -Be 0
    }
}

Describe 'The lab after the fixes, and a neglected CA' {
    It 'has one Low finding left after the fixes' {
        $f = Test-Facts (Get-Facts 'after')
        @($f).Count | Should -Be 1
        $f[0].Check | Should -Be 'TemplateSuppliesIdentityGuarded'
    }
    It 'flags every problem on the neglected CA' {
        $f = Test-Facts (Get-Facts 'bad')
        $c = Get-Checks $f 'CON-OLDCA'
        foreach ($x in 'CaServiceNotRunning', 'CaWeakSignature', 'CaWeakKey', 'CrlExpired', 'CdpNoHttp', 'CdpLocalPathInCertificates', 'TemplateSuppliesIdentity', 'CollectorError') { $c | Should -Contain $x }
        (Get-Checks $f 'CON-OLDWEB') | Should -Contain 'CertNoPrivateKey'
        (Get-Checks $f 'CON-OLDWEB') | Should -Contain 'CertExpiring'
    }
    It 'warns about a CA certificate that is close to expiring' {
        $ca = Get-Facts 'before'
        $f = @(Test-CaFacts -CaFacts $ca.Ca -Config $script:Config -Now ([datetime]'2031-06-01T00:00:00Z').ToUniversalTime())
        ($f | Where-Object Check -eq 'CaCertificateExpiring').Severity | Should -Be 'Medium'
    }
}

Describe 'Get-CertTemplateName' {
    It 'prefers the v1 name, then parses the v2 text' {
        Get-CertTemplateName ([pscustomobject]@{ TemplateName = 'Machine'; TemplateInfo = 'Template=Other(1.2.3)' }) | Should -Be 'Machine'
        Get-CertTemplateName ([pscustomobject]@{ TemplateName = $null; TemplateInfo = 'Template=Web Server (1.3.6.1.4.1.311.21.8.1), Major Version Number=100, Minor Version Number=4' }) | Should -Be 'Web Server'
        Get-CertTemplateName ([pscustomobject]@{ TemplateName = $null; TemplateInfo = $null }) | Should -BeNullOrEmpty
    }
}

Describe 'Renewal plan and apply' {
    BeforeAll {
        $script:B = Get-Facts 'before'
        $script:F = Test-Facts $script:B
        $script:Plan = @(Get-CertRenewalPlan -Hosts @($script:B.Hosts) -Findings $script:F -Now $script:Now)
    }
    It 'plans one step per expiring or expired certificate, worst first' {
        $script:Plan.Count | Should -Be 3
        $script:Plan[0].Target | Should -Be 'CON-SQL01'
        $script:Plan[0].DaysLeft | Should -BeLessThan 0
    }
    It 'enrolls only when a template is known and the certificate is not self-signed' {
        ($script:Plan | Where-Object Target -eq 'CON-SRV01').Kind | Should -Be 'Enroll'
        ($script:Plan | Where-Object Target -eq 'CON-SRV01').Command | Should -Be "Get-Certificate -Template 'Machine' -CertStoreLocation Cert:\LocalMachine\My"
        ($script:Plan | Where-Object Target -eq 'CON-SRV02').Kind | Should -Be 'Manual'
        ($script:Plan | Where-Object Target -eq 'CON-SQL01').Kind | Should -Be 'Manual'
    }
    It 'plans nothing for the healthy lab' { @(Get-CertRenewalPlan -Hosts @((Get-Facts 'after').Hosts) -Findings (Test-Facts (Get-Facts 'after')) -Now $script:Now).Count | Should -Be 0 }
    It 'changes nothing with -WhatIf' {
        Mock Invoke-Command { throw 'must not run' } -ModuleName CertLab
        { Invoke-CertRenewal -Plan $script:Plan -WhatIf } | Should -Not -Throw
        Should -Invoke Invoke-Command -ModuleName CertLab -Times 0
    }
    It 'runs Get-Certificate once, on the owning server, and never touches Manual steps' {
        Mock Invoke-Command { [pscustomobject]@{ Status = 'Issued'; Thumbprint = 'NEW' } } -ModuleName CertLab
        $r = @(Invoke-CertRenewal -Plan $script:Plan)
        Should -Invoke Invoke-Command -ModuleName CertLab -Times 1 -ParameterFilter { $ComputerName -eq 'CON-SRV01' -and $ArgumentList -contains 'Machine' }
        ($r | Where-Object Result -eq 'Manual').Count | Should -Be 2
        ($r | Where-Object Result -eq 'Issued').Count | Should -Be 1
    }
    It 'reports a failed enrollment instead of stopping' {
        Mock Invoke-Command { throw 'the RPC server is unavailable' } -ModuleName CertLab
        $r = @(Invoke-CertRenewal -Plan $script:Plan)
        ($r | Where-Object Result -eq 'Failed').Detail | Should -Match 'RPC'
    }
}

Describe 'The CA build plan' {
    It 'writes real, parseable scripts with the config values in them' {
        foreach ($step in 'Ca', 'Http') {
            foreach ($s in @(Get-CertCaPlan -Config $script:Config -Step $step)) {
                $err = $null; [void][Parser]::ParseInput($s.Script, [ref]$null, [ref]$err)
                @($err).Count | Should -Be 0 -Because "step $($s.Id) must parse"
            }
        }
        $install = (Get-CertCaPlan -Config $script:Config -Step Ca | Where-Object Id -eq 'Install').Script
        $install | Should -Match "CAType\s+= 'EnterpriseRootCa'"
        $install | Should -Match "CACommonName\s+= 'Contoso Lab Issuing CA'"
        $install | Should -Match 'KeyLength\s+= 2048'
        $install | Should -Match 'Install-AdcsCertificationAuthority @p'
    }
    It 'sets the CRL periods with certutil and restarts the service' {
        $s = (Get-CertCaPlan -Config $script:Config -Step Ca | Where-Object Id -eq 'CrlPeriods').Script
        $s | Should -Match 'setreg CA\\CRLPeriod Weeks'
        $s | Should -Match 'setreg CA\\CRLDeltaPeriodUnits 1'
        $s | Should -Match 'Restart-Service -Name CertSvc'
    }
    It 'builds the HTTP CDP as Learn shows it' {
        $s = (Get-CertCaPlan -Config $script:Config -Step Http | Where-Object Id -eq 'Cdp').Script
        $s | Should -Match 'Add-CACrlDistributionPoint -Uri ''http://con-ca01.lab.contoso.com/pki/<CAName><CRLNameSuffix><DeltaCRLAllowed>.crl'' -AddToCertificateCdp -AddToFreshestCrl -Force'
        $s | Should -Match 'Get-CACrlDistributionPoint'   # idempotent: only adds when the URI is not there
    }
    It 'marks the Active Directory step irreversible and stops there without -AllowCaInstall' {
        Mock Invoke-Command { } -ModuleName CertLab
        $plan = @(Get-CertCaPlan -Config $script:Config -Step Ca)
        ($plan | Where-Object Irreversible).Id | Should -Be 'Install'
        $r = @(Invoke-CertCaPlan -Plan $plan -ComputerName CON-CA01)
        ($r | Where-Object Id -eq 'Install').Result | Should -Be 'Skipped'
        Should -Invoke Invoke-Command -ModuleName CertLab -Times 1 -Exactly   # only Features; the steps after the skipped one do not run
    }
    It 'runs everything with -AllowCaInstall, nothing with -WhatIf, and stops at the first failure' {
        Mock Invoke-Command { } -ModuleName CertLab
        $plan = @(Get-CertCaPlan -Config $script:Config -Step Ca)
        [void](Invoke-CertCaPlan -Plan $plan -ComputerName CON-CA01 -AllowCaInstall)
        Should -Invoke Invoke-Command -ModuleName CertLab -Times 3 -Exactly
        Mock Invoke-Command { throw 'boom' } -ModuleName CertLab
        $r = @(Invoke-CertCaPlan -Plan $plan -ComputerName CON-CA01 -AllowCaInstall)
        @($r).Count | Should -Be 1
        $r[0].Result | Should -Be 'Failed'
        Mock Invoke-Command { throw 'must not run' } -ModuleName CertLab
        { Invoke-CertCaPlan -Plan $plan -ComputerName CON-CA01 -AllowCaInstall -WhatIf } | Should -Not -Throw
    }
}

Describe 'Report and entry scripts' {
    It 'writes a markdown report with the findings' {
        $b = Get-Facts 'before'
        $md = ConvertTo-CertMarkdown -Hosts @($b.Hosts) -Ca $b.Ca -Findings (Test-Facts $b) -Now $script:Now
        $md | Should -Match '# Certificate check'
        $md | Should -Match 'Contoso Lab Issuing CA'
        $md | Should -Match 'TemplateSuppliesIdentity'
    }
    It 'Invoke-CertCheck exits 1 with -FailOnHigh on the bad lab and 0 on the good one' {
        $s = Join-Path $script:Src 'Invoke-CertCheck.ps1'
        & pwsh -NoProfile -File $s -FromFacts (Join-Path $script:Fixtures 'facts-before.json') -Now 2026-11-21T09:00:00Z -FailOnHigh | Out-Null
        $LASTEXITCODE | Should -Be 1
        & pwsh -NoProfile -File $s -FromFacts (Join-Path $script:Fixtures 'facts-after.json') -Now 2026-11-21T09:00:00Z -FailOnHigh | Out-Null
        $LASTEXITCODE | Should -Be 0
    }
    It 'the scripts parse' {
        foreach ($f in 'Invoke-CertCheck.ps1', 'Deploy-CertLab.ps1', 'CertLab/CertLab.psm1') {
            $err = $null; [void][Parser]::ParseFile((Join-Path $script:Src $f), [ref]$null, [ref]$err)
            @($err).Count | Should -Be 0 -Because $f
        }
    }
}
