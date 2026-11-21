using namespace System.Management.Automation.Language

BeforeAll {
    $script:Src = Join-Path $PSScriptRoot '../src'
    $script:Fixtures = Join-Path $PSScriptRoot 'fixtures'
    Import-Module (Join-Path $script:Src 'OpsLab/OpsLab.psd1') -Force
    $script:DefPath = Join-Path $script:Src 'jea-definition.json'
    $script:ModPath = Join-Path $script:Src 'ContosoOps/ContosoOps.psm1'
    $script:Def = Read-OpsEndpointDefinition -Path $script:DefPath
    $script:Risky = Read-OpsEndpointDefinition -Path (Join-Path $script:Fixtures 'risky-definition.json')
    $script:Now = [datetime]::new(2026, 11, 20, 9, 0, 0, [DateTimeKind]::Utc)

    function New-TestConfig([string] $LogDir) {
        $c = Get-Content -Raw (Join-Path $script:Src 'ops-job.json') | ConvertFrom-Json
        $c.LogDirectory = $LogDir
        $c.Retry.BaseDelaySeconds = 0
        $c
    }
    function Get-Health([string] $W3svc = 'Stopped', [double] $LogMB = 72.5) {
        $h = (Get-Content -Raw (Join-Path $script:Fixtures 'health-con-srv01.json') | ConvertFrom-Json)[0]
        $h.Services[0].Status = $W3svc
        $h.LogFolderMB = $LogMB
        $h
    }
}

Describe 'Read-OpsEndpointDefinition' {
    It 'reads the lab definition' {
        $script:Def.EndpointName | Should -Be 'Contoso.AppOps'
        @($script:Def.Session.RoleDefinitions.'CONTOSO\GG-AppOps-Operators') | Should -Be @('AppOpsReader', 'AppOpsOperator')
    }
    It 'refuses endpoint names reserved for Windows' {
        $f = Join-Path $TestDrive 'ms.json'
        (Get-Content -Raw $script:DefPath).Replace('"Contoso.AppOps"', '"microsoft.ops"') | Set-Content $f
        { Read-OpsEndpointDefinition -Path $f } | Should -Throw '*microsoft*'
    }
    It 'refuses a definition without RoleDefinitions' {
        $f = Join-Path $TestDrive 'nodefs.json'
        $j = Get-Content -Raw $script:DefPath | ConvertFrom-Json
        $j.Session.PSObject.Properties.Remove('RoleDefinitions')
        $j | ConvertTo-Json -Depth 10 | Set-Content $f
        { Read-OpsEndpointDefinition -Path $f } | Should -Throw '*RoleDefinitions*'
    }
}

Describe 'Merge-OpsRoleCapability (the merge rules on Learn)' {
    BeforeAll {
        # Learn's own example: "How role capabilities are merged"
        $script:LearnDef = [pscustomobject]@{
            Roles = [pscustomobject]@{
                A = [pscustomobject]@{ VisibleCmdlets = @(
                        'Get-Service',
                        [pscustomobject]@{ Name = 'Restart-Service'; Parameters = @([pscustomobject]@{ Name = 'DisplayName'; ValidateSet = @('DNS Client') }) }
                    ) }
                B = [pscustomobject]@{ VisibleCmdlets = @(
                        [pscustomobject]@{ Name = 'Get-Service'; Parameters = @([pscustomobject]@{ Name = 'DisplayName'; ValidatePattern = 'DNS.*' }) },
                        [pscustomobject]@{ Name = 'Restart-Service'; Parameters = @([pscustomobject]@{ Name = 'DisplayName'; ValidateSet = @('DNS Server') }) }
                    ) }
            }
        }
    }
    It 'reproduces the Learn example: Get-Service loses its pattern, the Restart-Service sets are combined' {
        $m = Merge-OpsRoleCapability -Definition $script:LearnDef -RoleNames A, B
        $get = $m.VisibleCmdlets | Where-Object Name -eq 'Get-Service'
        $restart = $m.VisibleCmdlets | Where-Object Name -eq 'Restart-Service'
        $get.Parameters | Should -BeNullOrEmpty
        $restart.Parameters[0].Name | Should -Be 'DisplayName'
        $restart.Parameters[0].ValidateSet | Should -Be @('DNS Client', 'DNS Server')
        @($m.Dropped | Where-Object Command -eq 'Get-Service').Count | Should -Be 1
        @($m.Dropped | Where-Object Command -eq 'Restart-Service').Count | Should -Be 0
    }
    It 'ignores a ValidateSet when another role allows the parameter with any value (rule 4)' {
        $d = [pscustomobject]@{ Roles = [pscustomobject]@{
                X = [pscustomobject]@{ VisibleCmdlets = @([pscustomobject]@{ Name = 'Stop-Service'; Parameters = @([pscustomobject]@{ Name = 'Name'; ValidateSet = @('Spooler') }) }) }
                Y = [pscustomobject]@{ VisibleCmdlets = @([pscustomobject]@{ Name = 'Stop-Service'; Parameters = @([pscustomobject]@{ Name = 'Name' }) }) }
            } }
        $m = Merge-OpsRoleCapability -Definition $d -RoleNames X, Y
        $m.VisibleCmdlets[0].Parameters[0].ValidateSet.Count | Should -Be 0
        $m.Dropped[0].Role | Should -Be 'X'
    }
    It 'ORs patterns and drops sets when patterns and sets meet (rules 6 and 7)' {
        $d = [pscustomobject]@{ Roles = [pscustomobject]@{
                X = [pscustomobject]@{ VisibleCmdlets = @([pscustomobject]@{ Name = 'Stop-Website'; Parameters = @([pscustomobject]@{ Name = 'Name'; ValidatePattern = '^HR_' }) }) }
                Y = [pscustomobject]@{ VisibleCmdlets = @([pscustomobject]@{ Name = 'Stop-Website'; Parameters = @([pscustomobject]@{ Name = 'Name'; ValidatePattern = '^IT_' }) }) }
                Z = [pscustomobject]@{ VisibleCmdlets = @([pscustomobject]@{ Name = 'Stop-Website'; Parameters = @([pscustomobject]@{ Name = 'Name'; ValidateSet = @('Default Web Site') }) }) }
            } }
        $m = Merge-OpsRoleCapability -Definition $d -RoleNames X, Y, Z
        $p = $m.VisibleCmdlets[0].Parameters[0]
        'HR_Payroll' | Should -Match $p.ValidatePattern
        'IT_Wiki' | Should -Match $p.ValidatePattern
        $p.ValidateSet.Count | Should -Be 0
        ($m.Dropped | Where-Object Role -eq 'Z').Reason | Should -Match 'ValidateSet is ignored'
    }
    It 'gives the lab Operators exactly two constrained commands plus the reader ones' {
        $m = Merge-OpsRoleCapability -Definition $script:Def -RoleNames AppOpsReader, AppOpsOperator
        ($m.VisibleCmdlets | Where-Object Name -eq 'Restart-Service').Parameters[0].ValidateSet | Should -Be @('W3SVC', 'WAS')
        @($m.VisibleFunctions.Name) | Should -Be @('Get-OpsHealth', 'Clear-OpsLogFolder')
        $m.Dropped | Should -BeNullOrEmpty
    }
}

Describe 'Test-OpsEndpointDefinition' {
    It 'finds nothing High in the lab definition and marks the virtual-account risk as accepted' {
        $f = @(Test-OpsEndpointDefinition -Definition $script:Def -ModulePath $script:ModPath)
        @($f | Where-Object Severity -eq 'High') | Should -BeNullOrEmpty
        ($f | Where-Object Check -eq 'VirtualAccountIsAdmin').Severity | Should -Be 'Accepted'
    }
    It 'catches every "quick fix" in the risky definition' {
        $f = @(Test-OpsEndpointDefinition -Definition $script:Risky -ModulePath $script:ModPath)
        $checks = @($f.Check | Select-Object -Unique)
        foreach ($c in 'WildcardCommand', 'DangerousCommand', 'UnconstrainedStateChange', 'MergeWidening', 'SetAndPattern',
            'UnanchoredPattern', 'ExternalCommandNotRooted', 'BadPrincipal', 'FunctionNotInModule', 'NoTranscript', 'VirtualAccountIsAdmin') {
            $checks | Should -Contain $c
        }
        ($f | Select-Object -First 1).Severity | Should -Be 'High'
    }
    It 'reports the merge trap: Operators lose the W3SVC/WAS limit because Readers allow Restart-Service unconstrained' {
        $w = @(Test-OpsEndpointDefinition -Definition $script:Risky | Where-Object { $_.Check -eq 'MergeWidening' -and $_.Scope -eq 'group CONTOSO\GG-AppOps-Operators' })
        $w.Count | Should -BeGreaterThan 0
        $w[0].Severity | Should -Be 'High'
        $w[0].Message | Should -Match 'Restart-Service'
    }
    It 'raises the virtual account to High on a domain controller' {
        $dc = Get-Content -Raw $script:DefPath | ConvertFrom-Json
        $dc.TargetRole = 'DomainController'
        $dc.AcceptedRisks = @()
        (Test-OpsEndpointDefinition -Definition $dc | Where-Object Check -eq 'VirtualAccountIsAdmin').Severity | Should -Be 'High'
    }
    It 'never lets an accepted risk hide a High finding' {
        $r = Get-Content -Raw (Join-Path $script:Fixtures 'risky-definition.json') | ConvertFrom-Json
        $r | Add-Member AcceptedRisks @([pscustomobject]@{ Check = 'DangerousCommand'; Reason = 'trust me' })
        (Test-OpsEndpointDefinition -Definition $r | Where-Object Check -eq 'DangerousCommand').Severity | Should -Be 'High'
    }
    It 'flags the FileSystem provider combined with Remove-Item' {
        $d = Get-Content -Raw $script:DefPath | ConvertFrom-Json
        $d.Roles.AppOpsOperator | Add-Member VisibleProviders @('FileSystem')
        $d.Roles.AppOpsOperator.VisibleCmdlets += [pscustomobject]@{ Name = 'Remove-Item'; Parameters = @([pscustomobject]@{ Name = 'Path' }) }
        @(Test-OpsEndpointDefinition -Definition $d | Where-Object Check -eq 'ProviderWithFileCmdlet').Count | Should -Be 1
    }
    It 'flags dynamic code in the functions module (JEA functions run unconstrained)' {
        $bad = Join-Path $TestDrive 'Bad.psm1'
        Set-Content $bad 'function Get-OpsHealth { param($x) Invoke-Expression $x }; function Clear-OpsLogFolder { [scriptblock]::Create("dir").Invoke() }'
        $f = @(Test-OpsEndpointDefinition -Definition $script:Def -ModulePath $bad | Where-Object Check -eq 'DynamicCode')
        $f.Count | Should -Be 2
    }
    It 'writes a markdown report with the merged view per group' {
        $md = ConvertTo-OpsLintMarkdown -Definition $script:Risky -Findings @(Test-OpsEndpointDefinition -Definition $script:Risky)
        $md | Should -Match '\| CONTOSO\\GG-AppOps-Operators \| AppOpsReader, AppOpsOperator \| .*Restart-Service \(any parameters\)'
    }
}

Describe 'Splats for New-PSRoleCapabilityFile and New-PSSessionConfigurationFile' {
    It 'builds the Operator role with a ValidateSet on Restart-Service' {
        $p = ConvertTo-OpsRoleCapabilityParams -Definition $script:Def -RoleName AppOpsOperator -Path 'C:\x\AppOpsOperator.psrc'
        $p.ModulesToImport | Should -Be @('ContosoOps')
        $p.VisibleCmdlets[0].Name | Should -Be 'Restart-Service'
        $p.VisibleCmdlets[0].Parameters[0].ValidateSet | Should -Be @('W3SVC', 'WAS')
        $p.VisibleFunctions | Should -Be @('Clear-OpsLogFolder')
        $p.ContainsKey('VisibleExternalCommands') | Should -BeFalse
        $p.ContainsKey('VisibleProviders') | Should -BeFalse
    }
    It 'builds a RestrictedRemoteServer session with a virtual account, transcripts and role definitions' {
        $p = ConvertTo-OpsSessionConfigParams -Definition $script:Def -Path 'C:\x\e.pssc'
        $p.SessionType | Should -Be 'RestrictedRemoteServer'
        $p.RunAsVirtualAccount | Should -BeTrue
        $p.ContainsKey('RunAsVirtualAccountGroups') | Should -BeFalse
        $p.TranscriptDirectory | Should -Be 'C:\ProgramData\JEAConfiguration\Transcripts'
        $p.RoleDefinitions['CONTOSO\GG-AppOps-Operators'].RoleCapabilities | Should -Be @('AppOpsReader', 'AppOpsOperator')
    }
    It 'prefers a gMSA over a virtual account when one is set' {
        $d = Get-Content -Raw $script:DefPath | ConvertFrom-Json
        $d.Session | Add-Member GroupManagedServiceAccount 'CONTOSO\gmsa-jea'
        $p = ConvertTo-OpsSessionConfigParams -Definition $d -Path 'x.pssc'
        $p.GroupManagedServiceAccount | Should -Be 'CONTOSO\gmsa-jea'
        $p.ContainsKey('RunAsVirtualAccount') | Should -BeFalse
    }
}

Describe 'Install-OpsEndpoint (Windows cmdlets mocked)' {
    BeforeAll {
        # Pester can only mock commands that exist: stubs declare every parameter the module passes
        function global:New-PSRoleCapabilityFile { param($Path, $Description, $ModulesToImport, $VisibleCmdlets, $VisibleFunctions, $VisibleExternalCommands, $VisibleProviders) }
        function global:New-PSSessionConfigurationFile { param($Path, $SessionType, $Description, $RoleDefinitions, $RunAsVirtualAccount, $RunAsVirtualAccountGroups, $GroupManagedServiceAccount, $TranscriptDirectory) }
        function global:Test-PSSessionConfigurationFile { param($Path) }
        function global:Get-PSSessionConfiguration { param($Name) }
        function global:Unregister-PSSessionConfiguration { param($Name, [switch] $Force) }
        function global:Register-PSSessionConfiguration { param($Path, $Name, [switch] $Force) }
        function global:icacls.exe { $global:LASTEXITCODE = 0 }
    }
    AfterAll {
        foreach ($n in 'New-PSRoleCapabilityFile', 'New-PSSessionConfigurationFile', 'Test-PSSessionConfigurationFile', 'Get-PSSessionConfiguration',
            'Unregister-PSSessionConfiguration', 'Register-PSSessionConfiguration', 'icacls.exe') { Remove-Item "function:global:$n" -ErrorAction SilentlyContinue }
    }
    BeforeEach {
        Mock -ModuleName OpsLab New-PSRoleCapabilityFile { }
        Mock -ModuleName OpsLab New-PSSessionConfigurationFile { }
        Mock -ModuleName OpsLab Test-PSSessionConfigurationFile { $true }
        Mock -ModuleName OpsLab Get-PSSessionConfiguration { [pscustomobject]@{ Name = 'Contoso.AppOps' } }
        Mock -ModuleName OpsLab Unregister-PSSessionConfiguration { }
        Mock -ModuleName OpsLab Register-PSSessionConfiguration { }
        Mock -ModuleName OpsLab icacls.exe { $global:LASTEXITCODE = 0 }
        # The transcript folder is C:\ProgramData\...: no C: on Linux. Pester 6 has no fall-through, so pass the rest on.
        Mock -ModuleName OpsLab New-Item { Microsoft.PowerShell.Management\New-Item @PesterBoundParameters }
        # Only the transcript folder: on Windows TestDrive is also on C:, so match C:\ProgramData, not all of C:.
        Mock -ModuleName OpsLab New-Item -ParameterFilter { $Path -like 'C:\ProgramData\*' } { }
    }
    It 'refuses to register a definition with High findings' {
        $risky = Join-Path $script:Fixtures 'risky-definition.json'
        { Install-OpsEndpoint -DefinitionPath $risky -FunctionsModulePath $script:ModPath -ModulesRoot $TestDrive -Confirm:$false } | Should -Throw '*High finding*'
        Should -Invoke -ModuleName OpsLab Register-PSSessionConfiguration -Times 0
        Should -Invoke -ModuleName OpsLab New-PSRoleCapabilityFile -Times 0
    }
    It 'builds the module, one .psrc per role, then re-registers the endpoint' {
        $r = Install-OpsEndpoint -DefinitionPath $script:DefPath -FunctionsModulePath $script:ModPath -ModulesRoot $TestDrive -Confirm:$false
        $r.Steps | Should -Be @('module', 'transcripts', 'registered')
        Should -Invoke -ModuleName OpsLab New-PSRoleCapabilityFile -Times 2 -Exactly
        Should -Invoke -ModuleName OpsLab New-PSRoleCapabilityFile -Times 1 -ParameterFilter { $Path -like '*RoleCapabilities*AppOpsOperator.psrc' }
        Should -Invoke -ModuleName OpsLab Unregister-PSSessionConfiguration -Times 1 -ParameterFilter { $Name -eq 'Contoso.AppOps' }
        Should -Invoke -ModuleName OpsLab Register-PSSessionConfiguration -Times 1 -ParameterFilter { $Name -eq 'Contoso.AppOps' -and $Force }
        $manifest = Import-PowerShellDataFile (Join-Path $TestDrive 'ContosoOps/ContosoOps.psd1')
        $manifest.FunctionsToExport | Should -Be @('Get-OpsHealth', 'Clear-OpsLogFolder')
        (Get-Content -Raw (Join-Path $TestDrive 'ContosoOps/ContosoOps.settings.json') | ConvertFrom-Json).WatchedServices | Should -Be @('W3SVC', 'WAS')
    }
    It 'changes nothing with -WhatIf' {
        Install-OpsEndpoint -DefinitionPath $script:DefPath -FunctionsModulePath $script:ModPath -ModulesRoot (Join-Path $TestDrive 'wi') -WhatIf | Out-Null
        Should -Invoke -ModuleName OpsLab Register-PSSessionConfiguration -Times 0
        Test-Path (Join-Path $TestDrive 'wi') | Should -BeFalse
    }
}

Describe 'ContosoOps functions (the JEA side)' {
    BeforeAll {
        Import-Module (Join-Path $script:Src 'ContosoOps/ContosoOps.psd1') -Force
        $script:LogRoot = Join-Path $TestDrive 'LogFiles'
        $settings = Join-Path $TestDrive 'settings.json'
        @{ WatchedServices = @('W3SVC', 'WAS'); LogRoot = $script:LogRoot } | ConvertTo-Json | Set-Content $settings
        Set-OpsSetting -Path $settings
    }
    BeforeEach {
        Remove-Item $script:LogRoot -Recurse -Force -ErrorAction SilentlyContinue
        $site = New-Item -ItemType Directory -Path (Join-Path $script:LogRoot 'W3SVC1') -Force
        foreach ($d in 40, 20, 3) {
            $f = New-Item -ItemType File -Path (Join-Path $site "u_ex$d.log") -Force
            Set-Content $f.FullName ('x' * 1024)
            $f.LastWriteTime = (Get-Date).AddDays(-$d)
        }
        $keep = New-Item -ItemType File -Path (Join-Path $site 'old-notes.txt') -Force
        $keep.LastWriteTime = (Get-Date).AddDays(-90)
    }
    It 'deletes only *.log files older than N days, under the configured root' {
        $r = Clear-OpsLogFolder -OlderThanDays 14 -Confirm:$false
        $r.FilesRemoved | Should -Be 2
        @(Get-ChildItem $script:LogRoot -Recurse -File).Name | Sort-Object | Should -Be @('old-notes.txt', 'u_ex3.log')
    }
    It 'changes nothing with -WhatIf (common parameters are always allowed in JEA)' {
        $r = Clear-OpsLogFolder -OlderThanDays 14 -WhatIf
        $r.Candidates | Should -Be 2
        $r.FilesRemoved | Should -Be 0
        @(Get-ChildItem $script:LogRoot -Recurse -File).Count | Should -Be 4
    }
    It 'rejects a retention under 7 days' {
        { Clear-OpsLogFolder -OlderThanDays 3 } | Should -Throw
    }
    It 'reports health facts' {
        function global:Get-CimInstance { param($ClassName, $Filter) }
        function global:Get-Service { param($Name, $ErrorAction) }
        try {
            Mock -ModuleName ContosoOps Get-CimInstance -ParameterFilter { $ClassName -eq 'Win32_OperatingSystem' } { [pscustomobject]@{ SystemDrive = 'C:'; LastBootUpTime = (Get-Date).AddDays(-2) } }
            Mock -ModuleName ContosoOps Get-CimInstance -ParameterFilter { $ClassName -eq 'Win32_LogicalDisk' } { [pscustomobject]@{ Size = 100GB; FreeSpace = 25GB } }
            Mock -ModuleName ContosoOps Get-Service -ParameterFilter { $Name -eq 'W3SVC' } { [pscustomobject]@{ Status = 'Stopped' } }
            Mock -ModuleName ContosoOps Get-Service -ParameterFilter { $Name -eq 'WAS' } { $null }
            Mock -ModuleName ContosoOps Test-Path -ParameterFilter { $Path -like 'HKLM:*' } { $false }
            $h = Get-OpsHealth
            $h.SystemFreePercent | Should -Be 25
            ($h.Services | Where-Object Name -eq 'W3SVC').Status | Should -Be 'Stopped'
            ($h.Services | Where-Object Name -eq 'WAS').Status | Should -Be 'Missing'
            $h.RebootPending | Should -BeFalse
            $h.LogFolderMB | Should -Be 0
            [math]::Round($h.UptimeDays) | Should -Be 2
        }
        finally {
            Remove-Item function:global:Get-CimInstance, function:global:Get-Service -ErrorAction SilentlyContinue
        }
    }
}

Describe 'Retry with exponential backoff' {
    It 'doubles the delay and caps it' {
        1..5 | ForEach-Object { Get-OpsRetryDelay -Attempt $_ -BaseDelaySeconds 5 -MaxDelaySeconds 60 } | Should -Be @(5, 10, 20, 40, 60)
    }
    It 'succeeds on the third attempt after sleeping 5 then 10 seconds' {
        $script:calls = 0; $script:slept = @()
        $r = Invoke-OpsWithRetry -MaxAttempts 3 -BaseDelaySeconds 5 -Sleep { param($s) $script:slept += $s } -ScriptBlock {
            $script:calls++; if ($script:calls -lt 3) { throw 'WinRM cannot complete the operation' }; 'ok'
        }
        $r | Should -Be 'ok'
        $script:slept | Should -Be @(5, 10)
    }
    It 'gives up after MaxAttempts with the last error' {
        { Invoke-OpsWithRetry -MaxAttempts 2 -Activity 'connect to CON-SRV01' -Sleep { } -ScriptBlock { throw 'Access is denied' } } |
            Should -Throw 'connect to CON-SRV01 failed after 2 attempt(s): Access is denied'
    }
}

Describe 'Get-OpsDecision' {
    BeforeAll { $script:Policy = (Get-Content -Raw (Join-Path $script:Src 'ops-job.json') | ConvertFrom-Json).Policy }
    It 'restarts a stopped allowed service and trims logs over budget' {
        $d = Get-OpsDecision -ComputerName CON-SRV01 -Health (Get-Health) -Policy $script:Policy
        $d.Actions.Action | Should -Be @('RestartService', 'ClearLogs')
        $d.Actions[0].Arguments.Name | Should -Be 'W3SVC'
        $d.Actions[1].Arguments.OlderThanDays | Should -Be 14
        $d.Alerts | Should -BeNullOrEmpty
    }
    It 'stops restarting after MaxRestartsPer24h (circuit breaker)' {
        $d = Get-OpsDecision -ComputerName CON-SRV01 -Health (Get-Health) -Policy $script:Policy -RecentRestarts @{ 'CON-SRV01\W3SVC' = 3 }
        $d.Actions.Action | Should -Not -Contain 'RestartService'
        ($d.Alerts | Where-Object Check -eq 'RestartLoop').Severity | Should -Be 'High'
    }
    It 'alerts instead of acting on a service outside RestartAllowed, a missing one, and a pending reboot' {
        $h = Get-Health -W3svc Running -LogMB 1
        $h.Services += [pscustomobject]@{ Name = 'MSSQLSERVER'; Status = 'Stopped' }
        $h.Services[1].Status = 'Missing'
        $h.RebootPending = $true
        $d = Get-OpsDecision -ComputerName CON-SRV01 -Health $h -Policy $script:Policy
        $d.Actions | Should -BeNullOrEmpty
        ($d.Alerts | Where-Object Check -eq 'ServiceStopped').Severity | Should -Be 'High'
        ($d.Alerts | Where-Object Check -eq 'ServiceMissing').Severity | Should -Be 'Medium'
        ($d.Alerts | Where-Object Check -eq 'RebootPending').Severity | Should -Be 'Medium'
    }
    It 'reports an unreachable target as High' {
        (Get-OpsDecision -ComputerName CON-SRV01 -Health $null -Policy $script:Policy).Alerts[0].Check | Should -Be 'Unreachable'
    }
}

Describe 'Invoke-OpsMaintenanceRun' {
    BeforeEach {
        $script:LogDir = Join-Path $TestDrive ([guid]::NewGuid().ToString('N'))
        $script:Config = New-TestConfig $script:LogDir
    }
    It 'plans actions offline from saved health, logs them and changes nothing' {
        $r = Invoke-OpsMaintenanceRun -Config $script:Config -Now $script:Now -HealthFile (Join-Path $script:Fixtures 'health-con-srv01.json') -RunId '00000000-0000-0000-0000-000000000000'
        $r.ExitCode | Should -Be 0
        $r.Results[0].Actions.Outcome | Should -Be @('Planned', 'Planned')
        $lines = Get-Content (Join-Path $script:LogDir 'ops-20261120.jsonl') | ForEach-Object { $_ | ConvertFrom-Json }
        $lines[0].Event | Should -Be 'RunStart'
        $lines[-1].Event | Should -Be 'RunEnd'
        @($lines | Where-Object Event -eq 'Action').Count | Should -Be 2
        (Get-Content (Join-Path $script:LogDir 'ops-20261120.jsonl'))[0] | Should -Match '^\{"TimestampUtc":"2026-11-20T09:00:00Z",'
    }

    Context 'live, with the endpoint mocked' {
        BeforeEach {
            $script:healthCalls = 0
            Mock -ModuleName OpsLab Connect-OpsTarget { [pscustomobject]@{ ComputerName = $ComputerName; Prefix = 'Jea'; Session = $null; Module = $null } }
            Mock -ModuleName OpsLab Disconnect-OpsTarget { }
            Mock -ModuleName OpsLab Invoke-OpsRemote -ParameterFilter { $Operation -eq 'Health' } {
                $script:healthCalls++
                if ($script:healthCalls -eq 1) { Get-Health } else { Get-Health -W3svc Running -LogMB 10 }
            }
            Mock -ModuleName OpsLab Invoke-OpsRemote -ParameterFilter { $Operation -eq 'ClearLogs' } { [pscustomobject]@{ FilesRemoved = 12; MBFreed = 61.2 } }
            Mock -ModuleName OpsLab Invoke-OpsRemote -ParameterFilter { $Operation -eq 'RestartService' } { }
        }
        It 'restarts W3SVC, trims logs, re-checks health and exits 0' {
            $r = Invoke-OpsMaintenanceRun -Config $script:Config -Now $script:Now -Confirm:$false
            $r.ExitCode | Should -Be 0
            $r.Results[0].Actions.Outcome | Should -Be @('Succeeded', 'Succeeded')
            $r.Results[0].Actions[1].Detail | Should -Be '12 file(s), 61.2 MB freed'
            Should -Invoke -ModuleName OpsLab Invoke-OpsRemote -Times 2 -Exactly -ParameterFilter { $Operation -eq 'Health' }
            Should -Invoke -ModuleName OpsLab Disconnect-OpsTarget -Times 1 -Exactly
        }
        It 'exits 1 and logs Failed when a change fails, without retrying it' {
            Mock -ModuleName OpsLab Invoke-OpsRemote -ParameterFilter { $Operation -eq 'RestartService' } { throw 'Cannot validate argument on parameter Name' }
            $r = Invoke-OpsMaintenanceRun -Config $script:Config -Now $script:Now -Confirm:$false
            $r.ExitCode | Should -Be 1
            ($r.Results[0].Actions | Where-Object Action -eq 'RestartService').Outcome | Should -Be 'Failed'
            Should -Invoke -ModuleName OpsLab Invoke-OpsRemote -Times 1 -Exactly -ParameterFilter { $Operation -eq 'RestartService' }
        }
        It 'retries the connection, then reports the target as unreachable' {
            Mock -ModuleName OpsLab Connect-OpsTarget { throw 'WinRM cannot complete the operation' }
            $r = Invoke-OpsMaintenanceRun -Config $script:Config -Now $script:Now -Confirm:$false
            $r.ExitCode | Should -Be 1
            $r.Results[0].Alerts[0].Check | Should -Be 'Unreachable'
            Should -Invoke -ModuleName OpsLab Connect-OpsTarget -Times 3 -Exactly
        }
        It 'stops restarting after three successful restarts in 24 hours (reads its own logs)' {
            Mock -ModuleName OpsLab Invoke-OpsRemote -ParameterFilter { $Operation -eq 'Health' } { Get-Health -LogMB 1 }
            foreach ($i in 0..2) { Invoke-OpsMaintenanceRun -Config $script:Config -Now $script:Now.AddHours($i) -Confirm:$false | Out-Null }
            $r = Invoke-OpsMaintenanceRun -Config $script:Config -Now $script:Now.AddHours(3) -Confirm:$false
            $r.Results[0].Actions | Should -BeNullOrEmpty
            $r.Results[0].Alerts.Check | Should -Contain 'RestartLoop'
            $r.ExitCode | Should -Be 1
            (Get-OpsRecentRestart -LogDirectory $script:LogDir -Since $script:Now.AddHours(-21))['CON-SRV01\W3SVC'] | Should -Be 3
        }
    }
}

Describe 'Entry scripts, end to end (offline)' {
    It 'Invoke-OpsLint.ps1 exits 1 on the risky definition and 0 on the lab one' {
        $lint = Join-Path $script:Src 'Invoke-OpsLint.ps1'
        pwsh -NoProfile -Command "& '$lint' -DefinitionPath '$(Join-Path $script:Fixtures 'risky-definition.json')' -FailOnHigh" | Out-Null
        $LASTEXITCODE | Should -Be 1
        $out = pwsh -NoProfile -Command "& '$lint' -FailOnHigh"
        $LASTEXITCODE | Should -Be 0
        $out[-1] | Should -Match 'Contoso.AppOps: 1 finding\(s\), 0 high.'
    }
    It 'Invoke-OpsMaintenance.ps1 runs offline and exits 0' {
        $script = Join-Path $script:Src 'Invoke-OpsMaintenance.ps1'
        $logs = Join-Path $TestDrive 'e2e'
        $out = pwsh -NoProfile -Command "& '$script' -HealthFile '$(Join-Path $script:Fixtures 'health-con-srv01.json')' -LogDirectory '$logs' -Now '2026-11-20T09:00:00Z'"
        $LASTEXITCODE | Should -Be 0
        ($out -join "`n") | Should -Match 'CON-SRV01\s+RestartService\s+W3SVC\s+Planned'
    }
}

Describe 'Runs on Windows PowerShell 5.1 (servers and the scheduled task)' {
    It '<_> has no PowerShell 7-only syntax' -ForEach @(
        'src/OpsLab/OpsLab.psm1', 'src/ContosoOps/ContosoOps.psm1', 'src/Invoke-OpsMaintenance.ps1', 'src/Invoke-OpsLint.ps1',
        'setup/New-OpsJobIdentity.ps1', 'setup/Register-OpsJobTask.ps1'
    ) {
        $tokens = $null; $errors = $null
        $ast = [Parser]::ParseFile((Join-Path $PSScriptRoot "../$_"), [ref]$tokens, [ref]$errors)
        $errors | Should -BeNullOrEmpty
        $bad = $ast.FindAll({
                param($n)
                $n -is [TernaryExpressionAst] -or $n -is [PipelineChainAst] -or
                ($n -is [BinaryExpressionAst] -and "$($n.Operator)" -eq 'QuestionQuestion') -or
                ($n -is [AssignmentStatementAst] -and "$($n.Operator)" -eq 'QuestionQuestionEquals') -or
                ($n -is [MemberExpressionAst] -and $n.NullConditional)
            }, $true)
        @($bad).Count | Should -Be 0
    }
    It 'setup scripts support -WhatIf' -ForEach @('setup/New-OpsJobIdentity.ps1', 'setup/Register-OpsJobTask.ps1') {
        $ast = [Parser]::ParseFile((Join-Path $PSScriptRoot "../$_"), [ref]$null, [ref]$null)
        $cb = $ast.ParamBlock.Attributes | Where-Object { $_.TypeName.Name -eq 'CmdletBinding' }
        ($cb.NamedArguments | Where-Object ArgumentName -eq 'SupportsShouldProcess') | Should -Not -BeNullOrEmpty
    }
}
