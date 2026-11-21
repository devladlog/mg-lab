using namespace System.Management.Automation.Language

BeforeAll {
    $script:Src = Join-Path $PSScriptRoot '../src'
    $script:Fixtures = Join-Path $PSScriptRoot 'fixtures'
    Import-Module (Join-Path $script:Src 'WacLab/WacLab.psd1') -Force
    $script:ConfigPath = Join-Path $script:Src 'wac-lab.json'
    $script:Config = Read-WacLabConfig -Path $script:ConfigPath
    $script:Now = [datetime]::new(2026, 11, 20, 9, 0, 0, [DateTimeKind]::Utc)
    function Get-Facts([string] $Name) { Get-Content -Raw (Join-Path $script:Fixtures "$Name.json") | ConvertFrom-Json }
    function Get-ConfigCopy { Get-Content -Raw $script:ConfigPath | ConvertFrom-Json }
    $script:GwDn = 'CN=CON-SRV02,CN=Computers,DC=lab,DC=contoso,DC=com'
}

Describe 'Read-WacLabConfig' {
    It 'reads the lab config' {
        $script:Config.Gateway.ComputerName | Should -Be 'CON-SRV02'
        @($script:Config.Nodes).Count | Should -Be 5
    }
    It 'rejects duplicate nodes and unknown modes' {
        $c = Get-ConfigCopy
        $c.Nodes += $c.Nodes[0]
        $f = Join-Path $TestDrive 'dupe.json'; $c | ConvertTo-Json -Depth 5 | Set-Content $f
        { Read-WacLabConfig -Path $f } | Should -Throw '*Duplicate*CON-DC01*'
        $c = Get-ConfigCopy; $c.Gateway.Mode = 'Desktop'
        $c | ConvertTo-Json -Depth 5 | Set-Content $f
        { Read-WacLabConfig -Path $f } | Should -Throw '*Mode*'
    }
    It 'builds the gateway URL (443 has no port suffix)' {
        Get-WacGatewayUrl -Config $script:Config | Should -Be 'https://con-srv02.lab.contoso.com'
        $c = Get-ConfigCopy; $c.Gateway.HttpsPort = 6601
        Get-WacGatewayUrl -Config $c | Should -Be 'https://con-srv02.lab.contoso.com:6601'
    }
}

Describe 'Connections CSV' {
    It 'writes the documented header, FQDNs, types, pipe-separated tags and global for shared connections' {
        $csv = ConvertTo-WacConnectionCsv -Config $script:Config
        $lines = $csv -split "`r`n"
        $lines[0] | Should -BeExactly '"name","type","tags","groupId"'
        $lines[2] | Should -BeExactly '"con-srv01.lab.contoso.com","msft.sme.connection-type.server","app|core","global"'
        @($lines | Where-Object { $_ }).Count | Should -Be 6
    }
    It 'refuses an undocumented type and a tag with a pipe' {
        $c = Get-ConfigCopy; $c.Nodes[0].Type = 'windows-server'
        { ConvertTo-WacConnectionCsv -Config $c } | Should -Throw "*type 'windows-server'*"
        $c = Get-ConfigCopy; $c.Nodes[0].Tags = @('a|b')
        { ConvertTo-WacConnectionCsv -Config $c } | Should -Throw '*tag*'
    }
    It 'passes its own validation' {
        Test-WacConnectionCsv -Content (ConvertTo-WacConnectionCsv -Config $script:Config) | Should -BeNullOrEmpty
    }
    It 'catches the two typos in the example CSV on Learn' {
        $f = @(Test-WacConnectionCsv -Content (Get-Content -Raw (Join-Path $script:Fixtures 'learn-sample.csv')))
        ($f | Where-Object Check -eq 'Malformed').Target | Should -Be 'line 5'
        ($f | Where-Object Check -eq 'UnknownType').Target | Should -Be 'line 3'
        $f.Count | Should -Be 2
    }
    It 'treats the header as case-sensitive' {
        $f = @(Test-WacConnectionCsv -Content ("`"Name`",`"Type`",`"Tags`",`"GroupId`"`n`"a.contoso.com`",`"msft.sme.connection-type.server`",`"`""))
        $f[0].Check | Should -Be 'Header'
    }
}

Describe 'Find-WacPowerShellModule' {
    It 'finds ConnectionTools under the current layout' {
        $root = Join-Path $TestDrive 'pf1'
        New-Item -ItemType Directory (Join-Path $root 'WindowsAdminCenter/PowerShellModules/Microsoft.WindowsAdminCenter.ConnectionTools') -Force | Out-Null
        Find-WacPowerShellModule -Name ConnectionTools -Root $root | Should -BeLike '*Microsoft.WindowsAdminCenter.ConnectionTools'
    }
    It 'finds ExtensionTools under the older layout' {
        $root = Join-Path $TestDrive 'pf2'
        New-Item -ItemType Directory (Join-Path $root 'Windows Admin Center/PowerShell/Modules/ExtensionTools') -Force | Out-Null
        Find-WacPowerShellModule -Name ExtensionTools -Root $root | Should -BeLike '*ExtensionTools'
    }
    It 'says where it looked when Windows Admin Center is not installed' {
        { Find-WacPowerShellModule -Name ConnectionTools -Root (Join-Path $TestDrive 'empty') } | Should -Throw '*Searched:*PowerShellModules*'
    }
    It 'shows why we search: the Import-Module line on Learn does not even parse' {
        $learn = 'Import-Module "$env:' + "'Program Files'" + '\WindowsAdminCenter\PowerShellModules\Microsoft.WindowsAdminCenter.ConnectionTools"'
        $tokens = $null; $errors = $null
        [void][Parser]::ParseInput($learn, [ref]$tokens, [ref]$errors)
        $errors[0].ErrorId | Should -Be 'InvalidVariableReferenceWithDrive'
    }
}

Describe 'Import-WacLabConnection (Import-WACConnection mocked)' {
    BeforeAll {
        function global:Import-WACConnection { param($Endpoint, $FileName, $AccessKey, $Credentials, [switch] $Prune) }
    }
    AfterAll { Remove-Item function:global:Import-WACConnection -ErrorAction SilentlyContinue }
    It 'validates, writes the CSV and passes the key as plain text only at the call' {
        Mock -ModuleName WacLab Find-WacPowerShellModule { 'X:\fake\ConnectionTools' }
        Mock -ModuleName WacLab Import-Module { }
        Mock -ModuleName WacLab Import-WACConnection { }
        $csv = Join-Path $TestDrive 'c.csv'
        $key = ConvertTo-SecureString 'lab-only-key' -AsPlainText -Force
        Import-WacLabConnection -Config $script:Config -AccessKey $key -CsvPath $csv -Confirm:$false
        Should -Invoke -ModuleName WacLab Import-WACConnection -Times 1 -ParameterFilter {
            $Endpoint -eq 'https://con-srv02.lab.contoso.com' -and $FileName -eq $csv -and $AccessKey -eq 'lab-only-key' -and -not $Prune
        }
        (Get-Content $csv -TotalCount 1) | Should -BeExactly '"name","type","tags","groupId"'
    }
    It 'imports nothing with -WhatIf' {
        Mock -ModuleName WacLab Import-WACConnection { }
        Import-WacLabConnection -Config $script:Config -AccessKey (ConvertTo-SecureString 'k' -AsPlainText -Force) -CsvPath (Join-Path $TestDrive 'w.csv') -WhatIf
        Should -Invoke -ModuleName WacLab Import-WACConnection -Times 0
    }
}

Describe 'Test-WacGateway (preflight rules)' {
    It 'passes the lab gateway: nothing High, self-signed and optional SQL node as Info' {
        $f = @(Test-WacGateway -Facts (Get-Facts 'facts-con-srv02') -Config $script:Config -Now $script:Now)
        @($f | Where-Object Severity -eq 'High') | Should -BeNullOrEmpty
        ($f | Where-Object Check -eq 'SelfSignedCertificate').Message | Should -Match '60 days'
        ($f | Where-Object Check -eq 'NodeUnreachable').Severity | Should -Be 'Info'
        ($f | Where-Object Check -eq 'NodeUnreachable').Target | Should -Be 'CON-SQL01'
    }
    It 'stops a gateway on a domain controller, with port 443 taken and a bad certificate' {
        $c = Get-ConfigCopy; $c.Gateway.CertificateThumbprint = '0000000000000000000000000000000000000000'
        $f = @(Test-WacGateway -Facts (Get-Facts 'facts-bad') -Config $c -Now $script:Now)
        $high = @($f | Where-Object Severity -eq 'High').Check
        foreach ($x in 'GatewayOnDomainController', 'PortInUse', 'CertificateExpired', 'CertificateEku', 'NodeUnreachable') { $high | Should -Contain $x }
        ($f | Where-Object Check -eq 'CertificateName').Severity | Should -Be 'Medium'
        ($f | Where-Object Check -eq 'NodeOldOs').Target | Should -Be 'CON-SQL01'
    }
    It 'warns before the certificate expires' {
        $facts = Get-Facts 'facts-con-srv02'
        $facts.Gateway.Certificate = [pscustomobject]@{ Thumbprint = 'AB'; NotAfter = $script:Now.AddDays(10).ToString('o'); DnsNames = @('con-srv02.lab.contoso.com'); Eku = @('1.3.6.1.5.5.7.3.1'); HasPrivateKey = $true }
        (Test-WacGateway -Facts $facts -Config $script:Config -Now $script:Now | Where-Object Check -eq 'CertificateExpiring').Message | Should -Match '10 day'
    }
    It 'checks the Virtualization Mode minimums (4 cores, 8 GB, 10 GB free)' {
        $c = Get-ConfigCopy; $c.Gateway.Mode = 'Virtualization'
        $checks = @(Test-WacGateway -Facts (Get-Facts 'facts-con-srv02') -Config $c -Now $script:Now | Where-Object Severity -eq 'High').Check
        $checks | Should -Contain 'VmModeCpu'
        $checks | Should -Contain 'VmModeMemory'
        $checks | Should -Not -Contain 'VmModeDisk'
    }
    It 'flags more nodes than Administration Mode is sized for' {
        $c = Get-ConfigCopy; $c.Policy.MaxNodesAdministrationMode = 3
        (Test-WacGateway -Facts (Get-Facts 'facts-con-srv02') -Config $c -Now $script:Now | Where-Object Check -eq 'ManyNodes').Severity | Should -Be 'Medium'
    }
    It 'flags SSO configured for a domain controller' {
        $c = Get-ConfigCopy; $c.Nodes[0].KerberosSso = $true
        (Test-WacGateway -Facts (Get-Facts 'facts-con-srv02') -Config $c -Now $script:Now | Where-Object Check -eq 'SsoToDomainController').Target | Should -Be 'CON-DC01'
    }
    It 'writes a markdown report with gateway and node tables' {
        $facts = Get-Facts 'facts-con-srv02'
        $md = ConvertTo-WacMarkdown -Facts $facts -Config $script:Config -Findings @(Test-WacGateway -Facts $facts -Config $script:Config -Now $script:Now)
        $md | Should -Match '\| con-srv01\.lab\.contoso\.com \| yes \| 26100 \| yes \| yes \|'
        $md | Should -Match 'https://con-srv02\.lab\.contoso\.com'
    }
}

Describe 'Installer' {
    It 'uses the documented silent switches; port and thumbprint only when needed' {
        Get-WacInstallerArgument -Config $script:Config | Should -Be @('/VERYSILENT', '/Mode=Administration')
        $c = Get-ConfigCopy; $c.Gateway.HttpsPort = 6601; $c.Gateway.CertificateThumbprint = 'aa11bb22cc33dd44ee55ff66aa77bb88cc99dd00'
        Get-WacInstallerArgument -Config $c | Should -Be @('/VERYSILENT', '/Mode=Administration', '/HTTPSPortNumber=6601', '/CertificateThumbprint=AA11BB22CC33DD44EE55FF66AA77BB88CC99DD00')
    }
    It 'rejects a malformed thumbprint' {
        $c = Get-ConfigCopy; $c.Gateway.CertificateThumbprint = 'not-a-thumbprint'
        { Get-WacInstallerArgument -Config $c } | Should -Throw '*40 hex*'
    }
    Context 'Install-WacGateway (Start-Process and the service mocked)' {
        BeforeAll {
            $script:Exe = Join-Path $TestDrive 'WindowsAdminCenter.exe'
            Set-Content $script:Exe 'fake'
            function global:Get-Service { param($Name, $ErrorAction) }
            function global:Start-Service { param($Name) }
        }
        AfterAll { Remove-Item function:global:Get-Service, function:global:Start-Service -ErrorAction SilentlyContinue }
        It 'installs, waits for the service, returns the URL' {
            Mock -ModuleName WacLab Start-Process { [pscustomobject]@{ ExitCode = 0 } }
            $script:polls = 0
            Mock -ModuleName WacLab Get-Service { $script:polls++; if ($script:polls -lt 3) { $null } else { [pscustomobject]@{ Status = 'Running' } } }
            $r = Install-WacGateway -Config $script:Config -InstallerPath $script:Exe -Sleep { } -Confirm:$false
            $r.Url | Should -Be 'https://con-srv02.lab.contoso.com'
            Should -Invoke -ModuleName WacLab Start-Process -Times 1 -ParameterFilter { ($ArgumentList -join ' ') -eq '/VERYSILENT /Mode=Administration' -and $Wait }
        }
        It 'throws on a non-zero exit code' {
            Mock -ModuleName WacLab Start-Process { [pscustomobject]@{ ExitCode = 1603 } }
            { Install-WacGateway -Config $script:Config -InstallerPath $script:Exe -Sleep { } -Confirm:$false } | Should -Throw '*1603*'
        }
        It 'runs nothing with -WhatIf' {
            Mock -ModuleName WacLab Start-Process { }
            Install-WacGateway -Config $script:Config -InstallerPath $script:Exe -WhatIf
            Should -Invoke -ModuleName WacLab Start-Process -Times 0
        }
    }
}

Describe 'Get-WacDelegationPlan (the attribute is replaced, so carry the full list)' {
    It 'adds the gateway and keeps a principal that was already there' {
        $old = 'CN=CON-OLDGW,CN=Computers,DC=lab,DC=contoso,DC=com'
        $p = Get-WacDelegationPlan -NodeName CON-SRV01 -GatewayDn $script:GwDn -Current @{ 'CON-SRV01' = @($old) }
        $p.Action | Should -Be 'Add'
        $p.Desired | Should -Be @($old, $script:GwDn)
    }
    It 'changes nothing when the gateway is already allowed' {
        (Get-WacDelegationPlan -NodeName CON-SRV01 -GatewayDn $script:GwDn -Current @{ 'CON-SRV01' = @($script:GwDn) }).Action | Should -Be 'NoChange'
    }
    It 'removes only the gateway, or clears when it was the only one' {
        $old = 'CN=CON-OLDGW,CN=Computers,DC=lab,DC=contoso,DC=com'
        $p = @(Get-WacDelegationPlan -NodeName A, B -GatewayDn $script:GwDn -Current @{ A = @($old, $script:GwDn); B = @($script:GwDn) } -Remove)
        $p[0].Action | Should -Be 'Remove'; $p[0].Desired | Should -Be @($old)
        $p[1].Action | Should -Be 'Clear'
    }
}

Describe 'Set-WacKerberosDelegation (ActiveDirectory mocked)' {
    BeforeAll {
        function global:Get-ADComputer { param($Identity, $Properties) }
        function global:Set-ADComputer { param($Identity, $PrincipalsAllowedToDelegateToAccount) }
    }
    AfterAll { Remove-Item function:global:Get-ADComputer, function:global:Set-ADComputer -ErrorAction SilentlyContinue }
    BeforeEach {
        $script:OldGw = 'CN=CON-OLDGW,CN=Computers,DC=lab,DC=contoso,DC=com'
        Mock -ModuleName WacLab Get-ADComputer -ParameterFilter { $Identity -eq 'CON-SRV02' } { [pscustomobject]@{ Name = 'CON-SRV02'; DistinguishedName = $script:GwDn } }
        Mock -ModuleName WacLab Get-ADComputer -ParameterFilter { $Identity -eq 'CON-SRV01' } { [pscustomobject]@{ PrimaryGroupID = 515; PrincipalsAllowedToDelegateToAccount = @($script:OldGw) } }
        Mock -ModuleName WacLab Get-ADComputer -ParameterFilter { $Identity -in 'CON-SQL01', 'CON-CLI01' } { [pscustomobject]@{ PrimaryGroupID = 515; PrincipalsAllowedToDelegateToAccount = @() } }
        Mock -ModuleName WacLab Get-ADComputer -ParameterFilter { $Identity -eq 'CON-DC01' } { [pscustomobject]@{ PrimaryGroupID = 516; PrincipalsAllowedToDelegateToAccount = @() } }
        Mock -ModuleName WacLab Set-ADComputer { }
    }
    It 'sets the full list on each SSO node, keeping the existing principal' {
        $r = @(Set-WacKerberosDelegation -Config $script:Config -Confirm:$false)
        @($r | Where-Object Result -eq 'Done').Node | Should -Be @('CON-SRV01', 'CON-SQL01', 'CON-CLI01')
        Should -Invoke -ModuleName WacLab Set-ADComputer -Times 1 -ParameterFilter {
            $Identity -eq 'CON-SRV01' -and ($PrincipalsAllowedToDelegateToAccount -join ';') -eq "$($script:OldGw);$($script:GwDn)"
        }
    }
    It 'skips a domain controller unless asked' {
        $c = Get-ConfigCopy; $c.Nodes[0].KerberosSso = $true
        $r = @(Set-WacKerberosDelegation -Config $c -Confirm:$false)
        ($r | Where-Object Node -eq 'CON-DC01').Action | Should -Be 'Skipped'
        Should -Invoke -ModuleName WacLab Set-ADComputer -Times 0 -ParameterFilter { $Identity -eq 'CON-DC01' }
    }
    It 'clears the attribute with $null when the gateway was the only principal (tear-down)' {
        Mock -ModuleName WacLab Get-ADComputer -ParameterFilter { $Identity -in 'CON-SQL01', 'CON-CLI01' } { [pscustomobject]@{ PrimaryGroupID = 515; PrincipalsAllowedToDelegateToAccount = @($script:GwDn) } }
        Mock -ModuleName WacLab Get-ADComputer -ParameterFilter { $Identity -eq 'CON-SRV01' } { [pscustomobject]@{ PrimaryGroupID = 515; PrincipalsAllowedToDelegateToAccount = @($script:OldGw, $script:GwDn) } }
        Set-WacKerberosDelegation -Config $script:Config -Remove -Confirm:$false | Out-Null
        Should -Invoke -ModuleName WacLab Set-ADComputer -Times 2 -ParameterFilter { $null -eq $PrincipalsAllowedToDelegateToAccount }
        Should -Invoke -ModuleName WacLab Set-ADComputer -Times 1 -ParameterFilter { $Identity -eq 'CON-SRV01' -and ($PrincipalsAllowedToDelegateToAccount -join ';') -eq $script:OldGw }
    }
    It 'changes nothing with -WhatIf' {
        $r = @(Set-WacKerberosDelegation -Config $script:Config -WhatIf)
        Should -Invoke -ModuleName WacLab Set-ADComputer -Times 0
        @($r | Where-Object Result -eq 'WhatIf').Count | Should -Be 3
    }
}

Describe 'RBAC' {
    It 'reports the missing reader and the unexpected administrator' {
        $f = @(Test-WacRbac -Status (Get-Content -Raw (Join-Path $script:Fixtures 'rbac-status.json') | ConvertFrom-Json) -Config $script:Config)
        ($f | Where-Object Check -eq 'RbacMemberMissing').Message | Should -Be "CONTOSO\ALEX.DEMO isn't in 'Windows Admin Center Readers'."
        ($f | Where-Object Check -eq 'RbacUnexpectedMember').Message | Should -Match 'JORDAN.DEMO'
    }
    It 'reports a node where RBAC was never applied' {
        $s = [pscustomobject]@{ ComputerName = 'CON-SRV01'; EndpointPresent = $false; Groups = @() }
        (Test-WacRbac -Status @($s) -Config $script:Config)[0].Check | Should -Be 'RbacNotApplied'
    }
    It 'adds the missing member on the node' {
        function global:Invoke-Command { param($ComputerName, $ScriptBlock, $ArgumentList, $Credential) }
        try {
            Mock -ModuleName WacLab Get-WacRbacStatus { Get-Content -Raw (Join-Path $script:Fixtures 'rbac-status.json') | ConvertFrom-Json }
            Mock -ModuleName WacLab Invoke-Command { }
            $r = @(Add-WacRbacMember -Config $script:Config -Confirm:$false)
            $r[0].Group | Should -Be 'Windows Admin Center Readers'
            Should -Invoke -ModuleName WacLab Invoke-Command -Times 1 -ParameterFilter { $ComputerName -eq 'CON-SRV01' -and $ArgumentList[0] -eq 'Windows Admin Center Readers' }
        }
        finally { Remove-Item function:global:Invoke-Command -ErrorAction SilentlyContinue }
    }
}

Describe 'Invoke-WacPreflight.ps1 (offline, end to end)' {
    It 'exits 0 on the lab gateway and 1 on the bad one with -FailOnHigh' {
        $s = Join-Path $script:Src 'Invoke-WacPreflight.ps1'
        $out = pwsh -NoProfile -Command "& '$s' -FromFacts '$(Join-Path $script:Fixtures 'facts-con-srv02.json')' -Now '2026-11-20T09:00:00Z' -FailOnHigh"
        $LASTEXITCODE | Should -Be 0
        $out[-1] | Should -Be 'CON-SRV02: 5 node(s), 2 finding(s), 0 high.'
        pwsh -NoProfile -Command "& '$s' -FromFacts '$(Join-Path $script:Fixtures 'facts-bad.json')' -FailOnHigh" | Out-Null
        $LASTEXITCODE | Should -Be 1
    }
}

Describe 'Runs on Windows PowerShell 5.1 (the gateway)' {
    It '<_> has no PowerShell 7-only syntax' -ForEach @('src/WacLab/WacLab.psm1', 'src/Invoke-WacPreflight.ps1', 'src/Deploy-WacLab.ps1') {
        $tokens = $null; $errors = $null
        $ast = [Parser]::ParseFile((Join-Path $PSScriptRoot "../$_"), [ref]$tokens, [ref]$errors)
        $errors | Should -BeNullOrEmpty
        @($ast.FindAll({
                    param($n)
                    $n -is [TernaryExpressionAst] -or $n -is [PipelineChainAst] -or
                    ($n -is [BinaryExpressionAst] -and "$($n.Operator)" -eq 'QuestionQuestion') -or
                    ($n -is [AssignmentStatementAst] -and "$($n.Operator)" -eq 'QuestionQuestionEquals') -or
                    ($n -is [MemberExpressionAst] -and $n.NullConditional)
                }, $true)).Count | Should -Be 0
    }
    It 'the remote collectors call no WacLab function (only the script block travels)' {
        $exported = (Get-Module WacLab).ExportedFunctions.Keys
        foreach ($sb in (Get-WacCollectorScript), (Get-WacRbacCollectorScript)) {
            $cmds = $sb.Ast.FindAll({ param($n) $n -is [CommandAst] }, $true) | ForEach-Object { $_.GetCommandName() }
            $cmds | Where-Object { $_ -in $exported } | Should -BeNullOrEmpty
        }
    }
}
