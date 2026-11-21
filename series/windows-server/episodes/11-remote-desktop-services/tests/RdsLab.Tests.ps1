BeforeAll {
    $script:Src = Join-Path $PSScriptRoot '../src'
    $script:Fixtures = Join-Path $PSScriptRoot 'fixtures'
    Import-Module (Join-Path $script:Src 'RdsLab/RdsLab.psd1') -Force
    $script:ConfigPath = Join-Path $script:Src 'rds-lab.json'
    $script:Config = Read-RdsLabConfig -Path $script:ConfigPath
    $script:Now = [datetime]'2026-11-25T12:00:00Z'
    function Get-Facts([string] $Name) { Get-Content -Raw (Join-Path $script:Fixtures "$Name.json") | ConvertFrom-Json }
    function Get-ConfigCopy { Get-Content -Raw $script:ConfigPath | ConvertFrom-Json }
    function Test-Facts($Facts) { @(Test-RdsDeployment -Facts $Facts -Config $script:Config -Now $script:Now) }
    function Get-Checks($Findings) { @($Findings | ForEach-Object Check) }

    # RemoteDesktop module cmdlets exist only on Windows with the role: stubs with the parameters the module passes, so Pester can mock them
    $script:Stub = {
        [CmdletBinding(SupportsShouldProcess)]
        param($ConnectionBroker, $WebAccessServer, $SessionHost, $Server, $Role, $LicenseServer, $Mode, [switch] $Force,
            $CollectionName, $CollectionDescription, $UserGroup, $AuthenticateUsingNLA, $SecurityLayer, $EncryptionLevel,
            $IdleSessionLimitMin, $DisconnectedSessionLimitMin, $ActiveSessionLimitMin, $AutomaticReconnectionEnabled,
            $TemporaryFoldersDeletedOnExit, $HostServer, $UnifiedSessionID)
    }
    foreach ($n in 'New-RDSessionDeployment', 'Add-RDServer', 'Set-RDLicenseConfiguration', 'New-RDSessionCollection', 'Set-RDSessionCollectionConfiguration', 'Invoke-RDUserLogoff') {
        Set-Item -Path "function:global:$n" -Value $script:Stub
    }
    Set-Item -Path 'function:global:Get-RDUserSession' -Value { param($ConnectionBroker, $CollectionName) }
}

AfterAll {
    foreach ($n in 'New-RDSessionDeployment', 'Add-RDServer', 'Set-RDLicenseConfiguration', 'New-RDSessionCollection', 'Set-RDSessionCollectionConfiguration', 'Invoke-RDUserLogoff', 'Get-RDUserSession') {
        Remove-Item "function:global:$n" -ErrorAction SilentlyContinue
    }
}

Describe 'Read-RdsLabConfig' {
    It 'reads the lab config' {
        $script:Config.Collection.Name | Should -Be 'MG Lab Desktops'
        @($script:Config.Deployment.SessionHosts).Count | Should -Be 1
        $script:Config.Policy.LicensingMode | Should -Be 'PerUser'
    }
    It 'rejects bad values' {
        $f = Join-Path $TestDrive 'c.json'
        $c = Get-ConfigCopy; $c.Policy.LicensingMode = 'PerSeat'; $c | ConvertTo-Json -Depth 5 | Set-Content $f
        { Read-RdsLabConfig -Path $f } | Should -Throw '*PerDevice, PerUser, NotConfigured*'
        $c = Get-ConfigCopy; $c.Policy.SecurityLayer = 'TLS13'; $c | ConvertTo-Json -Depth 5 | Set-Content $f
        { Read-RdsLabConfig -Path $f } | Should -Throw '*SecurityLayer*'
        $c = Get-ConfigCopy; $c.Policy.EncryptionLevel = 'Maximum'; $c | ConvertTo-Json -Depth 5 | Set-Content $f
        { Read-RdsLabConfig -Path $f } | Should -Throw '*EncryptionLevel*'
        $c = Get-ConfigCopy; $c.Deployment.ConnectionBroker = 'con-rds01'; $c | ConvertTo-Json -Depth 5 | Set-Content $f
        { Read-RdsLabConfig -Path $f } | Should -Throw '*fully qualified*'
        $c = Get-ConfigCopy; $c.Deployment.SessionHosts = @(); $c | ConvertTo-Json -Depth 5 | Set-Content $f
        { Read-RdsLabConfig -Path $f } | Should -Throw '*at least one*'
        $c = Get-ConfigCopy; $c.Policy.IdleSessionLimitMin = -5; $c | ConvertTo-Json -Depth 5 | Set-Content $f
        { Read-RdsLabConfig -Path $f } | Should -Throw '*negative*'
    }
}

Describe 'Test-RdsDeployment: nothing deployed yet' {
    BeforeAll { $script:F = Test-Facts (Get-Facts 'facts-nodeployment') }
    It 'says there is no deployment, and the rest is information only' {
        $script:F[0].Check | Should -Be 'NoDeployment'
        $script:F[0].Severity | Should -Be 'High'
        @($script:F | Where-Object Severity -ne 'Info').Count | Should -Be 1
        Get-Checks $script:F | Should -Contain 'OnGracePeriod'
    }
}

Describe 'Test-RdsDeployment: Server Manager defaults' {
    BeforeAll { $script:F = Test-Facts (Get-Facts 'facts-defaults') }
    It 'finds what the defaults leave open' {
        $c = Get-Checks $script:F
        $c | Should -Contain 'NoLicensingServer'
        $c | Should -Contain 'OnGracePeriod'
        $c | Should -Contain 'CollectionOpenToEveryone'
        $c | Should -Contain 'SecurityLayerBelowPolicy'
        $c | Should -Contain 'EncryptionBelowPolicy'
        $c | Should -Contain 'NoIdleLimit'
        $c | Should -Contain 'NoDisconnectLimit'
        @($c | Where-Object { $_ -eq 'CertSelfSigned' }).Count | Should -Be 3
        $c | Should -Contain 'SingleBroker'
        $c | Should -Contain 'SingleSessionHost'
    }
    It 'has no High finding' {
        @($script:F | Where-Object Severity -eq 'High').Count | Should -Be 0
    }
    It 'treats the grace period as information while days are left and no license server is needed yet' {
        ($script:F | Where-Object Check -eq 'OnGracePeriod').Severity | Should -Be 'Info'
        ($script:F | Where-Object Check -eq 'OnGracePeriod').Message | Should -BeLike '*118 day(s)*120 days*'
    }
    It 'reports a security layer of Negotiate as Low, not High' {
        ($script:F | Where-Object Check -eq 'SecurityLayerBelowPolicy').Severity | Should -Be 'Low'
        ($script:F | Where-Object Check -eq 'EncryptionBelowPolicy').Severity | Should -Be 'Low'
    }
    It 'warns when the grace period is nearly over' {
        $f = Get-Facts 'facts-defaults'; $f.Hosts[0].GraceDays = 12
        $r = Test-Facts $f
        ($r | Where-Object Check -eq 'GracePeriodEnding').Severity | Should -Be 'Medium'
        Get-Checks $r | Should -Not -Contain 'OnGracePeriod'
    }
    It 'sorts High before Medium before Low before Info' {
        $order = @{ High = 0; Medium = 1; Low = 2; Info = 3 }
        $ranks = @($script:F | ForEach-Object { $order[$_.Severity] })
        $ranks | Should -Be @($ranks | Sort-Object)
    }
}

Describe 'Test-RdsDeployment: after the plan' {
    BeforeAll { $script:F = Test-Facts (Get-Facts 'facts-tuned') }
    It 'leaves only the self-signed certificates and the single-server notes' {
        $c = Get-Checks $script:F
        @($c | Where-Object { $_ -notin 'CertSelfSigned', 'SingleBroker', 'SingleSessionHost' }).Count | Should -Be 0
        @($c | Where-Object { $_ -eq 'CertSelfSigned' }).Count | Should -Be 3
    }
    It 'does not talk about the grace period when a license server is configured' {
        Get-Checks $script:F | Should -Not -Contain 'OnGracePeriod'
    }
    It 'can accept self-signed certificates if the policy says so' {
        $cfg = Get-ConfigCopy; $cfg.Policy.RequireTrustedCertificates = $false
        $r = @(Test-RdsDeployment -Facts (Get-Facts 'facts-tuned') -Config $cfg -Now $script:Now)
        Get-Checks $r | Should -Not -Contain 'CertSelfSigned'
    }
}

Describe 'Test-RdsDeployment: a badly set up deployment' {
    BeforeAll { $script:F = Test-Facts (Get-Facts 'facts-bad') }
    It 'flags the session host on Server Core as High' {
        ($script:F | Where-Object Check -eq 'SessionHostOnServerCore').Severity | Should -Be 'High'
        ($script:F | Where-Object Check -eq 'SessionHostOnServerCore').Message | Should -BeLike '*not in Server Core*'
    }
    It 'flags an expired grace period with no license server' {
        ($script:F | Where-Object Check -eq 'GracePeriodOver').Severity | Should -Be 'High'
    }
    It 'flags NLA off, RDP security layer and Low encryption as High' {
        ($script:F | Where-Object Check -eq 'NlaOff').Severity | Should -Be 'High'
        ($script:F | Where-Object Check -eq 'SecurityLayerBelowPolicy').Severity | Should -Be 'High'
        ($script:F | Where-Object Check -eq 'EncryptionBelowPolicy').Severity | Should -Be 'High'
    }
    It 'flags Everyone as a user group' {
        ($script:F | Where-Object Check -eq 'CollectionOpenToEveryone').Message | Should -BeLike "*'Everyone'*"
    }
    It 'handles certificate levels and dates' {
        ($script:F | Where-Object Check -eq 'CertNotConfigured').Target | Should -Be 'RDRedirector'
        ($script:F | Where-Object Check -eq 'CertExpired').Target | Should -Be 'RDPublishing'
        ($script:F | Where-Object { $_.Check -eq 'CertExpiring' }).Target | Should -Be 'RDWebAccess'
    }
    It 'turns collector errors into Info findings' {
        ($script:F | Where-Object Check -eq 'CollectorError').Severity | Should -Be 'Info'
    }
}

Describe 'Test-RdsDeployment: missing role services' {
    It 'reports a deployment without a session host or web access' {
        $f = Get-Facts 'facts-defaults'
        $f.Servers[0].Roles = @('RDS-CONNECTION-BROKER')
        $c = Get-Checks (Test-Facts $f)
        $c | Should -Contain 'NoSessionHost'
        $c | Should -Contain 'NoWebAccess'
    }
    It 'reports a missing collection' {
        $f = Get-Facts 'facts-defaults'
        $f.Collection.Exists = $false
        Get-Checks (Test-Facts $f) | Should -Contain 'NoCollection'
    }
    It 'reports an empty user group list' {
        $f = Get-Facts 'facts-defaults'
        $f.Collection.UserGroups = @()
        Get-Checks (Test-Facts $f) | Should -Contain 'CollectionNoUsers'
    }
    It 'reports a license server without a licensing mode' {
        $f = Get-Facts 'facts-tuned'
        $f.License.Mode = 'NotConfigured'
        Get-Checks (Test-Facts $f) | Should -Contain 'LicensingModeNotSet'
    }
    It 'reports a licensing mode that differs from policy' {
        $f = Get-Facts 'facts-tuned'
        $f.License.Mode = 'PerDevice'
        ($script:x = Test-Facts $f | Where-Object Check -eq 'LicensingModeDiffers').Severity | Should -Be 'Low'
    }
}

Describe 'Get-RdsSessionSummary' {
    It 'counts active and disconnected sessions per host' {
        $s = @(Get-RdsSessionSummary -Sessions (Get-Facts 'facts-defaults').Sessions)
        $s.Count | Should -Be 1
        $s[0].Total | Should -Be 2
        $s[0].Active | Should -Be 1
        $s[0].Disconnected | Should -Be 1
        $s[0].Users | Should -Be 'alex.demo, sam.demo'
    }
    It 'returns nothing for no sessions' {
        @(Get-RdsSessionSummary -Sessions @()).Count | Should -Be 0
    }
}

Describe 'Get-RdsDeploymentPlan' {
    It 'plans every step for an empty deployment, in order, with the disruptive one marked' {
        $p = @(Get-RdsDeploymentPlan -Config $script:Config -Facts (Get-Facts 'facts-nodeployment'))
        @($p | ForEach-Object Id) | Should -Be @('InstallDeployment', 'AddLicensing', 'LicenseConfig', 'NewCollection', 'CollectionConfig')
        $p[0].Disruptive | Should -BeTrue
        $p[0].Cmdlet | Should -Be 'New-RDSessionDeployment'
        @($p[0].Parameters.SessionHost) | Should -Be @('con-rds01.lab.contoso.com')
        @($p | Where-Object Disruptive).Count | Should -Be 1
    }
    It 'plans the same from no facts at all' {
        @(Get-RdsDeploymentPlan -Config $script:Config -Facts $null | ForEach-Object Id) | Should -Be @('InstallDeployment', 'AddLicensing', 'LicenseConfig', 'NewCollection', 'CollectionConfig')
    }
    It 'plans only the differences for a defaults deployment, with the value found' {
        $p = @(Get-RdsDeploymentPlan -Config $script:Config -Facts (Get-Facts 'facts-defaults'))
        @($p | ForEach-Object Id) | Should -Be @('AddLicensing', 'LicenseConfig', 'CollectionConfig', 'Certificate')
        $cc = $p | Where-Object Id -eq 'CollectionConfig'
        @($cc.Parameters.Keys | Where-Object { $_ -notin 'CollectionName', 'ConnectionBroker' } | Sort-Object) |
            Should -Be @('DisconnectedSessionLimitMin', 'EncryptionLevel', 'IdleSessionLimitMin', 'SecurityLayer', 'UserGroup')
        $cc.Parameters.SecurityLayer | Should -Be 'SSL'
        $cc.Before.SecurityLayer | Should -Be 'Negotiate'
        $cc.Before.IdleSessionLimitMin | Should -Be 0
        $cc.Before.UserGroup | Should -Be 'CONTOSO\Domain Users'
        ($p | Where-Object Id -eq 'LicenseConfig').Parameters.Mode | Should -Be 'PerUser'
        ($p | Where-Object Id -eq 'Certificate').Manual | Should -BeTrue
    }
    It 'plans nothing but the manual certificate step after the plan ran' {
        $p = @(Get-RdsDeploymentPlan -Config $script:Config -Facts (Get-Facts 'facts-tuned'))
        @($p | ForEach-Object Id) | Should -Be @('Certificate')
    }
    It 'does not plan a certificate step when all certificates are trusted' {
        $f = Get-Facts 'facts-tuned'
        foreach ($c in $f.Certificates) { $c.Level = 'Trusted' }
        @(Get-RdsDeploymentPlan -Config $script:Config -Facts $f).Count | Should -Be 0
    }
    It 'replaces an open user group with the dedicated one' {
        $p = @(Get-RdsDeploymentPlan -Config $script:Config -Facts (Get-Facts 'facts-defaults'))
        @(($p | Where-Object Id -eq 'CollectionConfig').Parameters.UserGroup) | Should -Be @('CONTOSO\RDS Demo Users')
    }
}

Describe 'Invoke-RdsDeploymentPlan' {
    BeforeEach {
        foreach ($n in 'New-RDSessionDeployment', 'Add-RDServer', 'Set-RDLicenseConfiguration', 'New-RDSessionCollection', 'Set-RDSessionCollectionConfiguration') {
            Mock -CommandName $n -MockWith { } -ModuleName RdsLab
        }
    }
    It 'skips the disruptive step without -AllowDeployment and runs the rest' {
        $p = @(Get-RdsDeploymentPlan -Config $script:Config -Facts (Get-Facts 'facts-nodeployment'))
        $r = @(Invoke-RdsDeploymentPlan -Plan $p -Confirm:$false -WarningAction SilentlyContinue)
        Should -Invoke New-RDSessionDeployment -ModuleName RdsLab -Times 0 -Exactly
        Should -Invoke Add-RDServer -ModuleName RdsLab -Times 1 -Exactly
        Should -Invoke Set-RDLicenseConfiguration -ModuleName RdsLab -Times 1 -Exactly
        Should -Invoke New-RDSessionCollection -ModuleName RdsLab -Times 1 -Exactly
        Should -Invoke Set-RDSessionCollectionConfiguration -ModuleName RdsLab -Times 1 -Exactly
        $r.Count | Should -Be 4
    }
    It 'runs the install with -AllowDeployment' {
        $p = @(Get-RdsDeploymentPlan -Config $script:Config -Facts (Get-Facts 'facts-nodeployment'))
        Invoke-RdsDeploymentPlan -Plan $p -AllowDeployment -Confirm:$false | Out-Null
        Should -Invoke New-RDSessionDeployment -ModuleName RdsLab -Times 1 -Exactly
    }
    It 'passes the planned values to the cmdlet' {
        $p = @(Get-RdsDeploymentPlan -Config $script:Config -Facts (Get-Facts 'facts-defaults'))
        Invoke-RdsDeploymentPlan -Plan $p -Confirm:$false -WarningAction SilentlyContinue | Out-Null
        Should -Invoke Set-RDSessionCollectionConfiguration -ModuleName RdsLab -Times 1 -Exactly -ParameterFilter { $SecurityLayer -eq 'SSL' -and $EncryptionLevel -eq 'High' -and $CollectionName -eq 'MG Lab Desktops' -and $IdleSessionLimitMin -eq 30 }
        Should -Invoke Set-RDLicenseConfiguration -ModuleName RdsLab -Times 1 -Exactly -ParameterFilter { $Mode -eq 'PerUser' -and $LicenseServer -contains 'con-rds01.lab.contoso.com' }
    }
    It 'changes nothing with -WhatIf' {
        $p = @(Get-RdsDeploymentPlan -Config $script:Config -Facts (Get-Facts 'facts-nodeployment'))
        Invoke-RdsDeploymentPlan -Plan $p -AllowDeployment -WhatIf | Out-Null
        foreach ($n in 'New-RDSessionDeployment', 'Add-RDServer', 'Set-RDLicenseConfiguration', 'New-RDSessionCollection', 'Set-RDSessionCollectionConfiguration') {
            Should -Invoke $n -ModuleName RdsLab -Times 0 -Exactly
        }
    }
    It 'warns about the manual certificate step and never calls Set-RDCertificate' {
        $p = @(Get-RdsDeploymentPlan -Config $script:Config -Facts (Get-Facts 'facts-tuned'))
        $w = @(Invoke-RdsDeploymentPlan -Plan $p -Confirm:$false 3>&1)
        ($w | Out-String) | Should -BeLike '*manual step*'
    }
    It 'refuses a plan that names a cmdlet outside the allow-list' {
        $evil = [pscustomobject]@{ Id = 'X'; Cmdlet = 'Remove-Item'; Parameters = @{ Path = 'C:\' }; Disruptive = $false; Why = 'x'; Manual = $false }
        { Invoke-RdsDeploymentPlan -Plan @($evil) -Confirm:$false } | Should -Throw '*not an allowed cmdlet*'
    }
}

Describe 'Invoke-RdsDisconnectedLogoff' {
    BeforeEach {
        Mock -CommandName Get-RDUserSession -MockWith {
            @(
                [pscustomobject]@{ UserName = 'alex.demo'; HostServer = 'con-rds01.lab.contoso.com'; SessionState = 'STATE_ACTIVE'; UnifiedSessionId = 2 },
                [pscustomobject]@{ UserName = 'sam.demo'; HostServer = 'con-rds01.lab.contoso.com'; SessionState = 'STATE_DISCONNECTED'; UnifiedSessionId = 3 },
                [pscustomobject]@{ UserName = 'riley.demo'; HostServer = 'con-rds01.lab.contoso.com'; SessionState = 'STATE_DISCONNECTED'; UnifiedSessionId = 4 }
            )
        } -ModuleName RdsLab
        Mock -CommandName Invoke-RDUserLogoff -MockWith { } -ModuleName RdsLab
    }
    It 'logs off only disconnected sessions of the matching user' {
        $r = @(Invoke-RdsDisconnectedLogoff -UserName 'sam.demo' -Confirm:$false)
        $r.Count | Should -Be 1
        Should -Invoke Invoke-RDUserLogoff -ModuleName RdsLab -Times 1 -Exactly -ParameterFilter { $HostServer -eq 'con-rds01.lab.contoso.com' -and $UnifiedSessionID -eq 3 }
    }
    It 'never touches an active session even if the name matches' {
        Invoke-RdsDisconnectedLogoff -UserName 'alex.demo' -Confirm:$false | Out-Null
        Should -Invoke Invoke-RDUserLogoff -ModuleName RdsLab -Times 0 -Exactly
    }
    It 'supports a wildcard and -WhatIf' {
        Invoke-RdsDisconnectedLogoff -UserName '*.demo' -WhatIf | Out-Null
        Should -Invoke Invoke-RDUserLogoff -ModuleName RdsLab -Times 0 -Exactly
        $r = @(Invoke-RdsDisconnectedLogoff -UserName '*.demo' -Confirm:$false)
        $r.Count | Should -Be 2
    }
    It 'requires a user pattern' {
        (Get-Command Invoke-RdsDisconnectedLogoff).Parameters['UserName'].Attributes.Mandatory | Should -Contain $true
    }
}

Describe 'ConvertTo-RdsMarkdown' {
    It 'writes servers, hosts, findings and sessions' {
        $f = Get-Facts 'facts-defaults'
        $md = ConvertTo-RdsMarkdown -Facts $f -Findings (Test-Facts $f)
        $md | Should -BeLike '*RDS-CONNECTION-BROKER, RDS-WEB-ACCESS, RDS-RD-SERVER*'
        $md | Should -BeLike '*| CertSelfSigned |*'
        $md | Should -BeLike '*alex.demo, sam.demo*'
    }
    It 'says None when there are no findings' {
        $md = ConvertTo-RdsMarkdown -Facts (Get-Facts 'facts-nodeployment') -Findings @()
        $md | Should -BeLike '*None.*'
        $md | Should -BeLike '*No user sessions.*'
    }
}

Describe 'Scripts and collectors' {
    It 'parses every script without errors' {
        foreach ($f in Get-ChildItem (Join-Path $script:Src '*.ps1'), (Join-Path $script:Src 'RdsLab/*.ps*1'), (Join-Path $PSScriptRoot '../setup/*.ps1')) {
            $errors = $null
            [System.Management.Automation.Language.Parser]::ParseFile($f.FullName, [ref]$null, [ref]$errors) | Out-Null
            @($errors).Count | Should -Be 0 -Because $f.Name
        }
    }
    It 'collectors are read-only: no Set-, New-, Remove-, Add-, Invoke-RD* verbs' {
        $ast = (Get-RdsCollectorScript).Ast
        $cmds = @($ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.CommandAst] }, $true) | ForEach-Object { $_.GetCommandName() } | Where-Object { $_ })
        @($cmds | Where-Object { $_ -match '^(Set|New|Remove|Add|Invoke|Disconnect|Send)-RD' }).Count | Should -Be 0
        ($cmds | Where-Object { $_ -match '^Get-RD' }).Count | Should -BeGreaterThan 4
    }
    It 'the script blocks have the parameters Get-RdsFacts passes' {
        (Get-RdsCollectorScript).Ast.ParamBlock.Parameters.Name.VariablePath.UserPath | Should -Be @('Broker', 'CollectionName')
    }
}
