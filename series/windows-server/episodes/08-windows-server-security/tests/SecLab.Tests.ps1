using namespace System.Management.Automation.Language

BeforeAll {
    $script:Src = Join-Path $PSScriptRoot '../src'
    $script:Fixtures = Join-Path $PSScriptRoot 'fixtures'
    Import-Module (Join-Path $script:Src 'SecLab/SecLab.psd1') -Force
    $script:ConfigPath = Join-Path $script:Src 'sec-lab.json'
    $script:Config = Read-SecLabConfig -Path $script:ConfigPath
    function Get-Facts([string] $Name) { @(Get-Content -Raw (Join-Path $script:Fixtures "$Name.json") | ConvertFrom-Json) }
    function Get-ConfigCopy { Get-Content -Raw $script:ConfigPath | ConvertFrom-Json }
    function Get-Checks($Findings, [string] $Target) { @($Findings | Where-Object { $_.Target -eq $Target } | ForEach-Object Check) }
    function Test-All($Facts) { @($Facts | ForEach-Object { Test-SecHost -Facts $_ -Config $script:Config }) }

    # Cmdlets that exist only on Windows (or with RSAT): stubs with the parameters the module passes, so Pester can mock them
    $script:Stub = {
        [CmdletBinding(SupportsShouldProcess)]
        param($Identity, $Name, $Target, $Key, $ValueName, $Type, $Value, $ComputerName, $ScriptBlock, $ArgumentList, $Credential)
    }
    foreach ($n in 'Update-LapsADSchema', 'Set-LapsADComputerSelfPermission', 'Get-GPO', 'New-GPO', 'Set-GPRegistryValue', 'Get-GPInheritance', 'New-GPLink') {
        Set-Item -Path "function:global:$n" -Value $script:Stub
    }
}

AfterAll {
    foreach ($n in 'Update-LapsADSchema', 'Set-LapsADComputerSelfPermission', 'Get-GPO', 'New-GPO', 'Set-GPRegistryValue', 'Get-GPInheritance', 'New-GPLink') {
        Remove-Item "function:global:$n" -ErrorAction SilentlyContinue
    }
}

Describe 'Read-SecLabConfig' {
    It 'reads the lab config' {
        @($script:Config.Targets).Count | Should -Be 5
        $script:Config.Laps.BackupDirectory | Should -Be 2
    }
    It 'rejects bad values' {
        $f = Join-Path $TestDrive 'c.json'
        $c = Get-ConfigCopy; $c.Policy.MinLmCompatibilityLevel = 9; $c | ConvertTo-Json -Depth 5 | Set-Content $f
        { Read-SecLabConfig -Path $f } | Should -Throw '*0 to 5*'
        $c = Get-ConfigCopy; $c.Laps.PasswordLength = 4; $c | ConvertTo-Json -Depth 5 | Set-Content $f
        { Read-SecLabConfig -Path $f } | Should -Throw '*8 to 64*'
        $c = Get-ConfigCopy; $c.Laps.PasswordAgeDays = 400; $c | ConvertTo-Json -Depth 5 | Set-Content $f
        { Read-SecLabConfig -Path $f } | Should -Throw '*1 to 365*'
        $c = Get-ConfigCopy; $c.Targets += $c.Targets[0]; $c | ConvertTo-Json -Depth 5 | Set-Content $f
        { Read-SecLabConfig -Path $f } | Should -Throw '*Duplicate*CON-DC01*'
    }
}

Describe 'Test-SecHost on the lab before hardening' {
    BeforeAll { $script:Before = Test-All (Get-Facts 'facts-before') }
    It 'finds 26 things, none High' {
        $script:Before.Count | Should -Be 26
        @($script:Before | Where-Object Severity -eq 'High').Count | Should -Be 0
    }
    It 'asks for process creation auditing, the command line, inbound SMB signing and LAPS' {
        Get-Checks $script:Before 'CON-SRV01' | Should -Contain 'ProcessCreationNotAudited'
        Get-Checks $script:Before 'CON-SRV01' | Should -Contain 'CommandLineNotLogged'
        Get-Checks $script:Before 'CON-SRV01' | Should -Contain 'SmbServerSigningNotRequired'
        Get-Checks $script:Before 'CON-SRV01' | Should -Contain 'LapsNotBackingUpToAd'
    }
    It 'does not ask a domain controller for LAPS, and reports a missing LDAP value as Info, not as a finding' {
        Get-Checks $script:Before 'CON-DC01' | Should -Not -Contain 'LapsNotBackingUpToAd'
        ($script:Before | Where-Object Check -eq 'LdapSigningNotInRegistry').Severity | Should -Be 'Info'
        ($script:Before | Where-Object Check -eq 'LdapSigningNotInRegistry').Message | Should -BeLike '*Windows Server 2025 requires LDAP signing by default*'
    }
    It 'treats Credential Guard on a domain controller as Info and does not flag a member that runs it' {
        ($script:Before | Where-Object Check -eq 'CredentialGuardNotRunningOnDc').Severity | Should -Be 'Info'
        Get-Checks $script:Before 'CON-SRV01' | Should -Not -Contain 'CredentialGuardNotRunning'
    }
    It 'sorts High first, Info last' {
        $script:Before[0].Severity | Should -Be 'Medium'
        $script:Before[-1].Severity | Should -Be 'Info'
    }
}

Describe 'Test-SecHost after hardening' {
    It 'leaves only the Credential Guard note for the domain controller' {
        $r = Test-All (Get-Facts 'facts-after')
        $r.Count | Should -Be 1
        $r[0].Check | Should -Be 'CredentialGuardNotRunningOnDc'
    }
}

Describe 'Test-SecHost on the bad servers' {
    BeforeAll { $script:Bad = Test-All (Get-Facts 'facts-bad') }
    It 'finds 27 things, 9 of them High' {
        $script:Bad.Count | Should -Be 27
        @($script:Bad | Where-Object Severity -eq 'High').Count | Should -Be 9
    }
    It 'flags SMB 1, WDigest, weak LM level and unsigned LDAP' {
        Get-Checks $script:Bad 'OLD-FS01' | Should -Contain 'Smb1Enabled'
        Get-Checks $script:Bad 'OLD-FS01' | Should -Contain 'WDigestEnabled'
        Get-Checks $script:Bad 'OLD-FS01' | Should -Contain 'LmCompatibilityWeak'
        Get-Checks $script:Bad 'HV-DC02' | Should -Contain 'LdapSigningNotRequired'
    }
    It 'treats level 3 as below policy (Medium), not as weak' {
        ($script:Bad | Where-Object { $_.Target -eq 'APP-SRV03' -and $_.Check -eq 'LmCompatibilityBelowPolicy' }).Severity | Should -Be 'Medium'
    }
    It 'flags a missing Defender, real-time off, old signatures' {
        Get-Checks $script:Bad 'OLD-FS01' | Should -Contain 'DefenderNotReadable'
        Get-Checks $script:Bad 'APP-SRV03' | Should -Contain 'DefenderRealTimeOff'
        Get-Checks $script:Bad 'HV-DC02' | Should -Contain 'DefenderSignaturesOld'
    }
    It 'flags LAPS going to Entra ID instead of AD (policy wants AD)' {
        ($script:Bad | Where-Object { $_.Target -eq 'APP-SRV03' -and $_.Check -eq 'LapsNotBackingUpToAd' }).Message | Should -BeLike '*BackupDirectory is 1*'
    }
    It 'surfaces collector errors as Info' {
        ($script:Bad | Where-Object { $_.Target -eq 'OLD-FS01' -and $_.Check -eq 'CollectorError' }).Severity | Should -Be 'Info'
    }
    It 'LDAP value 1 is Medium, 2 is fine' {
        $f = Get-Facts 'facts-after' | Where-Object ComputerName -eq 'CON-DC01'
        $f.LdapServerIntegrity = 1
        (Test-SecHost -Facts $f -Config $script:Config | Where-Object Check -eq 'LdapSigningNegotiated').Severity | Should -Be 'Medium'
    }
}

Describe 'ConvertTo-SecMarkdown' {
    It 'renders the table and the findings' {
        $f = Get-Facts 'facts-bad'
        $md = ConvertTo-SecMarkdown -Facts $f -Findings (Test-All $f)
        $md | Should -BeLike '# Security baseline check*'
        $md | Should -BeLike '*| OLD-FS01 |*'
        $md | Should -BeLike '*| High | OLD-FS01 | Smb1Enabled |*'
    }
    It 'says None when clean' {
        (ConvertTo-SecMarkdown -Facts (Get-Facts 'facts-after') -Findings @()) | Should -BeLike '*None.*'
    }
}

Describe 'Get-SecRemediationPlan and Get-SecRollbackPlan' {
    BeforeAll {
        $script:BeforeFacts = Get-Facts 'facts-before'
        $script:BeforeFindings = Test-All $script:BeforeFacts
        $script:Plan = @(Get-SecRemediationPlan -Findings $script:BeforeFindings -Config $script:Config -Facts $script:BeforeFacts)
    }
    It 'has three steps per server for the lab, and LAPS is not one of them (it has its own plan)' {
        $script:Plan.Count | Should -Be 15
        @($script:Plan | Where-Object Fix -eq 'LapsGpo').Count | Should -Be 0
    }
    It 'carries the value it read before' {
        ($script:Plan | Where-Object { $_.Target -eq 'CON-SRV01' -and $_.Fix -eq 'RequireSmbServerSigning' }).Before | Should -BeFalse
        ($script:Plan | Where-Object { $_.Target -eq 'CON-SRV01' -and $_.Fix -eq 'AuditProcessCreation' }).Before | Should -Be 'No Auditing'
    }
    It 'leaves out the risky LmCompatibilityLevel step unless asked' {
        $bad = Get-Facts 'facts-bad'
        $f = Test-All $bad
        @(Get-SecRemediationPlan -Findings $f -Config $script:Config -Facts $bad | Where-Object Fix -eq 'LmCompat').Count | Should -Be 0
        $with = @(Get-SecRemediationPlan -Findings $f -Config $script:Config -Facts $bad -IncludeRisky | Where-Object Fix -eq 'LmCompat')
        $with.Count | Should -BeGreaterThan 0
        $with[0].Value | Should -Be 5
    }
    It 'uses the Process Creation GUID, not the localized name' {
        ($script:Plan | Where-Object Fix -eq 'AuditProcessCreation')[0].Subcategory | Should -Be '{0CCE922B-69AE-11D9-BED3-505054503030}'
    }
    It 'rolls back: removes values that did not exist, restores values that did, turns the audit off again' {
        $bad = Get-Facts 'facts-bad'
        $plan = @(Get-SecRemediationPlan -Findings (Test-All $bad) -Config $script:Config -Facts $bad -IncludeRisky)
        $rb = @(Get-SecRollbackPlan -Plan $plan)
        $rb.Count | Should -Be $plan.Count
        $wd = $rb | Where-Object { $_.Target -eq 'OLD-FS01' -and $_.Fix -like '*WDigestOff' }
        $wd.Value | Should -Be 1
        $cmd = @(Get-SecRollbackPlan -Plan @($script:Plan | Where-Object { $_.Target -eq 'CON-SRV01' -and $_.Fix -eq 'ProcessCreationCmdLine' }))[0]
        $cmd.Remove | Should -BeTrue
        $au = @(Get-SecRollbackPlan -Plan @($script:Plan | Where-Object { $_.Target -eq 'CON-SRV01' -and $_.Fix -eq 'AuditProcessCreation' }))[0]
        $au.Value | Should -Be 'disable'
    }
    It 'marks an SMB step with an unknown old value as Manual' {
        $s = [pscustomobject]@{ Target = 'X'; Fix = 'DisableSmb1'; Kind = 'SmbServer'; Property = 'EnableSMB1Protocol'; Value = $false; Before = $null }
        @(Get-SecRollbackPlan -Plan @($s))[0].Kind | Should -Be 'Manual'
    }
}

Describe 'Invoke-SecRemediation (Invoke-Command mocked)' {
    BeforeEach { Mock -ModuleName SecLab Invoke-Command { } }
    It 'runs one remote call per step' {
        $plan = @(Get-SecRemediationPlan -Findings $script:BeforeFindings -Config $script:Config -Facts $script:BeforeFacts)
        $r = @(Invoke-SecRemediation -Plan $plan -Confirm:$false)
        $r.Count | Should -Be 15
        Should -Invoke -ModuleName SecLab Invoke-Command -Times 15 -Exactly
        Should -Invoke -ModuleName SecLab Invoke-Command -Times 3 -Exactly -ParameterFilter { $ComputerName -eq 'CON-SRV01' }
    }
    It 'does nothing with -WhatIf' {
        $plan = @(Get-SecRemediationPlan -Findings $script:BeforeFindings -Config $script:Config -Facts $script:BeforeFacts)
        Invoke-SecRemediation -Plan $plan -WhatIf | Out-Null
        Should -Invoke -ModuleName SecLab Invoke-Command -Times 0 -Exactly
    }
    It 'a rollback plan survives the JSON round trip the Deploy script uses' {
        $plan = @(Get-SecRemediationPlan -Findings $script:BeforeFindings -Config $script:Config -Facts $script:BeforeFacts)
        $json = ConvertTo-Json -InputObject @(Get-SecRollbackPlan -Plan $plan) -Depth 5
        $back = @($json | ConvertFrom-Json)
        $back.Count | Should -Be 15
        $r = @(Invoke-SecRemediation -Plan $back -Confirm:$false)
        $r.Count | Should -Be 15
        Should -Invoke -ModuleName SecLab Invoke-Command -Times 15 -Exactly -ParameterFilter { $ArgumentList[0].Fix -like 'Undo-*' }
    }
    It 'warns about, and skips, a Manual step' {
        $s = [pscustomobject]@{ Target = 'X'; Fix = 'Undo-DisableSmb1'; Kind = 'Manual'; Why = 'Old value unknown.' }
        Invoke-SecRemediation -Plan @($s) -Confirm:$false -WarningAction SilentlyContinue | Out-Null
        Should -Invoke -ModuleName SecLab Invoke-Command -Times 0 -Exactly
    }
}

Describe 'The remote step block' {
    It 'is self-contained and refuses a step kind it does not know' {
        InModuleScope SecLab {
            $cmds = @($script:ApplyStep.Ast.FindAll({ param($n) $n -is [CommandAst] }, $true) | ForEach-Object { $_.GetCommandName() } | Where-Object { $_ })
            @($cmds | Where-Object { $_ -match '-Sec' }).Count | Should -Be 0
            { & $script:ApplyStep ([pscustomobject]@{ Kind = 'Manual' }) } | Should -Throw "*cannot be applied*"
        }
    }
}

Describe 'Get-SecLapsPlan' {
    It 'includes the irreversible schema step first when the schema lacks LAPS' {
        $p = @(Get-SecLapsPlan -Config $script:Config -SchemaPresent $false -DomainDn 'DC=lab,DC=contoso,DC=com')
        $p[0].Cmdlet | Should -Be 'Update-LapsADSchema'
        $p[0].Irreversible | Should -BeTrue
        ($p | ForEach-Object Cmdlet | Select-Object -Unique) | Should -Contain 'New-GPLink'
    }
    It 'leaves it out when the schema already has it, and builds the OU DN and the three policy values' {
        $p = @(Get-SecLapsPlan -Config $script:Config -SchemaPresent $true -DomainDn 'DC=lab,DC=contoso,DC=com')
        @($p | Where-Object Irreversible).Count | Should -Be 0
        ($p | Where-Object Action -eq 'OuPermission').Parameters['Identity'] | Should -Be 'OU=LabServers,DC=lab,DC=contoso,DC=com'
        $vals = @($p | Where-Object Action -eq 'GpoValue')
        ($vals | ForEach-Object { $_.Parameters['ValueName'] }) | Should -Be @('BackupDirectory', 'PasswordAgeDays', 'PasswordLength')
        $vals[0].Parameters['Key'] | Should -Be 'HKLM\Software\Microsoft\Windows\CurrentVersion\Policies\LAPS'
        $vals[0].Parameters['Value'] | Should -Be 2
    }
    It 'adds the custom administrator account value only when configured' {
        $c = Get-ConfigCopy; $c.Laps.AdministratorAccountName = 'lab-admin'
        $p = @(Get-SecLapsPlan -Config $c -SchemaPresent $true -DomainDn 'DC=lab,DC=contoso,DC=com')
        @($p | Where-Object { $_.Parameters['ValueName'] -eq 'AdministratorAccountName' }).Count | Should -Be 1
    }
}

Describe 'Invoke-SecLapsPlan (GroupPolicy and LAPS mocked)' {
    BeforeEach {
        foreach ($c in 'Update-LapsADSchema', 'Set-LapsADComputerSelfPermission', 'New-GPO', 'Set-GPRegistryValue', 'New-GPLink') { Mock -ModuleName SecLab $c { } }
        Mock -ModuleName SecLab Get-GPO { $null }
        Mock -ModuleName SecLab Get-GPInheritance { [pscustomobject]@{ GpoLinks = @() } }
        $script:Plan = @(Get-SecLapsPlan -Config $script:Config -SchemaPresent $false -DomainDn 'DC=lab,DC=contoso,DC=com')
    }
    It 'skips the schema update without -AllowSchemaUpdate' {
        Invoke-SecLapsPlan -Plan $script:Plan -Confirm:$false -WarningAction SilentlyContinue
        Should -Invoke -ModuleName SecLab Update-LapsADSchema -Times 0 -Exactly
        Should -Invoke -ModuleName SecLab Set-LapsADComputerSelfPermission -Times 1 -Exactly
        Should -Invoke -ModuleName SecLab New-GPO -Times 1 -Exactly
        Should -Invoke -ModuleName SecLab Set-GPRegistryValue -Times 3 -Exactly
        Should -Invoke -ModuleName SecLab New-GPLink -Times 1 -Exactly
    }
    It 'runs the schema update with -AllowSchemaUpdate' {
        Invoke-SecLapsPlan -Plan $script:Plan -AllowSchemaUpdate -Confirm:$false
        Should -Invoke -ModuleName SecLab Update-LapsADSchema -Times 1 -Exactly
    }
    It 'is idempotent: an existing GPO and an existing link are left alone' {
        Mock -ModuleName SecLab Get-GPO { [pscustomobject]@{ DisplayName = 'MGLab - Windows LAPS' } }
        Mock -ModuleName SecLab Get-GPInheritance { [pscustomobject]@{ GpoLinks = @([pscustomobject]@{ DisplayName = 'MGLab - Windows LAPS' }) } }
        Invoke-SecLapsPlan -Plan $script:Plan -Confirm:$false -WarningAction SilentlyContinue
        Should -Invoke -ModuleName SecLab New-GPO -Times 0 -Exactly
        Should -Invoke -ModuleName SecLab New-GPLink -Times 0 -Exactly
    }
    It 'changes nothing with -WhatIf' {
        Invoke-SecLapsPlan -Plan $script:Plan -AllowSchemaUpdate -WhatIf
        Should -Invoke -ModuleName SecLab Update-LapsADSchema -Times 0 -Exactly
        Should -Invoke -ModuleName SecLab Set-GPRegistryValue -Times 0 -Exactly
    }
}

Describe 'Collector script block' {
    BeforeAll { $script:Ast = [Parser]::ParseInput((Get-SecCollectorScript).ToString(), [ref]$null, [ref]$null) }
    It 'is self-contained (calls no SecLab function)' {
        $cmds = @($script:Ast.FindAll({ param($n) $n -is [CommandAst] }, $true) | ForEach-Object { $_.GetCommandName() } | Where-Object { $_ })
        @($cmds | Where-Object { $_ -match '-Sec(?!urity)' }).Count | Should -Be 0
    }
    It 'is read-only: only Get- cmdlets, auditpol /get and a registry read' {
        $cmds = @($script:Ast.FindAll({ param($n) $n -is [CommandAst] }, $true) | ForEach-Object { $_.GetCommandName() } | Where-Object { $_ })
        @($cmds | Where-Object { $_ -match '^(Set|New|Remove|Start|Stop|Enable|Disable|Add|Update|Import|Export|Invoke)-' -and $_ -ne 'New-Object' }).Count | Should -Be 0
        $script:Ast.Extent.Text | Should -Not -BeLike '*/set*'
        $script:Ast.Extent.Text | Should -BeLike '*/get /subcategory*'
    }
}

Describe 'Entry scripts' {
    It 'Invoke-SecCheck prints the summary and the plan from a fixture' {
        $out = & (Join-Path $script:Src 'Invoke-SecCheck.ps1') -FromFacts (Join-Path $script:Fixtures 'facts-bad.json') -PlanOnly
        ($out | Select-Object -Last 1) | Should -Be '3 server(s), 27 finding(s), 9 high.'
    }
    It 'both scripts parse cleanly' {
        foreach ($f in 'Deploy-SecLab.ps1', 'Invoke-SecCheck.ps1') {
            $errs = $null
            [void][Parser]::ParseFile((Join-Path $script:Src $f), [ref]$null, [ref]$errs)
            $errs.Count | Should -Be 0
        }
    }
}
