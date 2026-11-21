BeforeAll {
    # Invoke-MgGraphRequest only exists after Install-Module Microsoft.Graph.Authentication: a stub with the documented
    # parameter names lets Pester mock it. When the real module is installed, it is used instead (and one test checks our calls against it).
    if (-not (Get-Command Invoke-MgGraphRequest -ErrorAction SilentlyContinue)) {
        Set-Item -Path function:global:Invoke-MgGraphRequest -Value ([scriptblock]::Create("[CmdletBinding()] param(`$Method, `$Uri, `$Body, `$ContentType, `$OutputType, `$Headers, `$OutputFilePath) throw 'stub: not connected'"))
    }
    Import-Module "$PSScriptRoot/../src/IntuneDevices/IntuneDevices.psd1" -Force
    $script:cfgPath = "$PSScriptRoot/../src/intune.json"
    $script:config = Get-IntuneConfig -Path $cfgPath
    $script:devices = @((Get-Content "$PSScriptRoot/fixtures/devices.json" -Raw | ConvertFrom-Json).value)
    $script:now = [datetimeoffset]::Parse('2026-11-21T12:00:00Z')
    $script:realGroup = '11111111-2222-3333-4444-555555555555'

    # The writable properties of windows10CompliancePolicy, copied from Microsoft Learn (resource type page).
    $script:learnProps = @('displayName', 'description', 'version', 'passwordRequired', 'passwordBlockSimple', 'passwordRequiredToUnlockFromIdle',
        'passwordMinutesOfInactivityBeforeLock', 'passwordExpirationDays', 'passwordMinimumLength', 'passwordMinimumCharacterSetCount', 'passwordRequiredType',
        'passwordPreviousPasswordBlockCount', 'requireHealthyDeviceReport', 'osMinimumVersion', 'osMaximumVersion', 'mobileOsMinimumVersion', 'mobileOsMaximumVersion',
        'earlyLaunchAntiMalwareDriverEnabled', 'bitLockerEnabled', 'secureBootEnabled', 'codeIntegrityEnabled', 'storageRequireEncryption')

    function script:New-Config([scriptblock]$Change) {
        $c = Get-Content $cfgPath -Raw | ConvertFrom-Json; & $Change $c
        $p = Join-Path $TestDrive ("cfg-{0}.json" -f [guid]::NewGuid()); $c | ConvertTo-Json -Depth 8 | Set-Content $p; $p
    }
    function script:Live-Config { Get-IntuneConfig -Path (New-Config { param($c) $c.compliancePolicy.assignTo.groupId = $realGroup }) }

    # A tiny fake Graph tenant, held in a global so the module-scope mock can see it.
    function script:Reset-Tenant([object]$Policy = $null, [string[]]$Actions = @(), [object[]]$Assignments = @()) {
        $global:T07 = @{ Policy = $Policy; Actions = $Actions; Assignments = $Assignments; Calls = [System.Collections.Generic.List[object]]::new() }
    }
    function script:Policy-From($Config, [hashtable]$Override = @{}) {
        $b = ConvertTo-IDCompliancePolicyBody -Config $Config
        $o = [ordered]@{ id = 'aaaaaaaa-0000-0000-0000-000000000007' }
        foreach ($k in $b.Keys) { if ($k -ne 'scheduledActionsForRule') { $o[$k] = $b[$k] } }
        foreach ($k in $Override.Keys) { $o[$k] = $Override[$k] }
        [pscustomobject]$o
    }
}

Describe 'Config file' {
    It 'loads the sample config' {
        $config.compliancePolicy.displayName | Should -Be 'MG Lab - Windows 11 baseline'
        $config.audit.staleDays | Should -Be 30
    }
    It 'refuses a setting that is not a windows10CompliancePolicy property' {
        { Get-IntuneConfig -Path (New-Config { param($c) $c.compliancePolicy.settings | Add-Member tpmRequired $true }) } | Should -Throw "*'tpmRequired' is not a windows10CompliancePolicy setting*"
    }
    It 'refuses a setting of the wrong type' {
        { Get-IntuneConfig -Path (New-Config { param($c) $c.compliancePolicy.settings.bitLockerEnabled = 'yes' }) } | Should -Throw '*bitLockerEnabled must be true or false*'
    }
    It 'refuses an OS version that is not major.minor.build.revision' {
        { Get-IntuneConfig -Path (New-Config { param($c) $c.compliancePolicy.settings.osMinimumVersion = '10.0.26100' }) } | Should -Throw '*major.minor.build.revision*'
    }
    It 'refuses a password type outside the Graph enum' {
        { Get-IntuneConfig -Path (New-Config { param($c) $c.compliancePolicy.settings.passwordRequiredType = 'pin' }) } | Should -Throw '*must be one of deviceDefault,alphanumeric,numeric*'
    }
    It 'refuses a missing block action' {
        { Get-IntuneConfig -Path (New-Config { param($c) $c.compliancePolicy.actions = @() }) } | Should -Throw '*one block action*'
    }
    It 'refuses two block actions (Learn: one and only one)' {
        { Get-IntuneConfig -Path (New-Config { param($c) $c.compliancePolicy.actions = @(@{ type = 'block'; gracePeriodHours = 0 }, @{ type = 'block'; gracePeriodHours = 48 }) }) } | Should -Throw '*exactly one block action*'
    }
    It 'refuses a grace period over 8760 hours (Learn: 0 to 8760)' {
        { Get-IntuneConfig -Path (New-Config { param($c) $c.compliancePolicy.actions[0].gracePeriodHours = 9000 }) } | Should -Throw '*0 to 8760*'
    }
    It 'refuses a wipe action' {
        { Get-IntuneConfig -Path (New-Config { param($c) $c.compliancePolicy.actions = @($c.compliancePolicy.actions[0], @{ type = 'wipe'; gracePeriodHours = 240 }) }) } | Should -Throw "*'wipe' is not allowed*"
    }
    It 'refuses a notification action without a template id' {
        { Get-IntuneConfig -Path (New-Config { param($c) $c.compliancePolicy.actions = @($c.compliancePolicy.actions[0], @{ type = 'notification'; gracePeriodHours = 48 }) }) } | Should -Throw '*notificationTemplateId*'
    }
    It 'refuses both groupId and allLicensedUsers, and neither' {
        { Get-IntuneConfig -Path (New-Config { param($c) $c.compliancePolicy.assignTo | Add-Member allLicensedUsers $true }) } | Should -Throw '*exactly one of groupId or allLicensedUsers*'
        { Get-IntuneConfig -Path (New-Config { param($c) $c.compliancePolicy.assignTo = [pscustomobject]@{} }) } | Should -Throw '*exactly one of groupId or allLicensedUsers*'
    }
    It 'refuses a groupId that is not a GUID' {
        { Get-IntuneConfig -Path (New-Config { param($c) $c.compliancePolicy.assignTo.groupId = 'All Staff' }) } | Should -Throw '*not a GUID*'
    }
    It 'refuses a stale limit over 270 days' {
        { Get-IntuneConfig -Path (New-Config { param($c) $c.audit.staleDays = 300 }) } | Should -Throw '*1 to 270*'
    }
}

Describe 'Request bodies' {
    BeforeAll { $script:body = ConvertTo-IDCompliancePolicyBody -Config $config }
    It 'is a windows10CompliancePolicy' { $body['@odata.type'] | Should -Be '#microsoft.graph.windows10CompliancePolicy' }
    It 'only uses properties that Learn documents for windows10CompliancePolicy' {
        $names = @($body.Keys | Where-Object { $_ -notin '@odata.type', 'scheduledActionsForRule' })
        $names | Where-Object { $_ -notin $learnProps } | Should -BeNullOrEmpty
    }
    It 'keeps numbers numbers and booleans booleans after ConvertTo-Json' {
        $j = $body | ConvertTo-Json -Depth 10 | ConvertFrom-Json
        $j.passwordMinimumLength | Should -BeOfType [long]
        $j.bitLockerEnabled | Should -BeOfType [bool]
        $j.osMinimumVersion | Should -Be '10.0.26100.0'
    }
    It 'carries the actions in scheduledActionsForRule with the fixed rule name' {
        $rule = $body.scheduledActionsForRule[0]
        $rule['@odata.type'] | Should -Be '#microsoft.graph.deviceComplianceScheduledActionForRule'
        $rule.ruleName | Should -Be 'PasswordRequired'
        $a = $rule.scheduledActionConfigurations[0]
        $a['@odata.type'] | Should -Be '#microsoft.graph.deviceComplianceActionItem'
        $a.actionType | Should -Be 'block'
        $a.gracePeriodHours | Should -Be 24
        $a.gracePeriodHours | Should -BeOfType [int]
    }
    It 'adds the template id to a notification action only' {
        $cfg = Get-IntuneConfig -Path (New-Config { param($c) $c.compliancePolicy.actions = @($c.compliancePolicy.actions[0], @{ type = 'notification'; gracePeriodHours = 48; notificationTemplateId = '99999999-0000-0000-0000-000000000007' }) })
        $items = (ConvertTo-IDCompliancePolicyBody -Config $cfg).scheduledActionsForRule[0].scheduledActionConfigurations
        $items.Count | Should -Be 2
        $items[0].Contains('notificationTemplateId') | Should -BeFalse
        $items[1].notificationTemplateId | Should -Be '99999999-0000-0000-0000-000000000007'
    }
    It 'builds a group assignment' {
        $t = (ConvertTo-IDAssignmentBody -Config (Live-Config)).assignments[0].target
        $t['@odata.type'] | Should -Be '#microsoft.graph.groupAssignmentTarget'
        $t.groupId | Should -Be $realGroup
    }
    It 'builds an all-licensed-users assignment' {
        $cfg = Get-IntuneConfig -Path (New-Config { param($c) $c.compliancePolicy.assignTo = [pscustomobject]@{ allLicensedUsers = $true } })
        (ConvertTo-IDAssignmentBody -Config $cfg).assignments[0].target['@odata.type'] | Should -Be '#microsoft.graph.allLicensedUsersAssignmentTarget'
    }
}

Describe 'Reading the policy (mocked Graph)' {
    BeforeEach {
        Reset-Tenant -Policy (Policy-From (Live-Config)) -Actions @('block|24h') -Assignments @("group:$realGroup")
        Mock Invoke-MgGraphRequest -ModuleName IntuneDevices {
            $global:T07.Calls.Add(@{ Method = $Method; Uri = $Uri; Body = $Body })
            switch -Regex ($Uri) {
                '/deviceCompliancePolicies$' {
                    $other = [pscustomobject]@{ id = 'bbbbbbbb-0000-0000-0000-000000000007'; displayName = 'iOS baseline'; '@odata.type' = '#microsoft.graph.iosCompliancePolicy' }
                    $mine = $global:T07.Policy | Add-Member '@odata.type' '#microsoft.graph.windows10CompliancePolicy' -PassThru -Force
                    return [pscustomobject]@{ value = @($other, $mine) }
                }
                '/scheduledActionsForRule$' { return [pscustomobject]@{ value = @([pscustomobject]@{ id = 'r1'; ruleName = 'PasswordRequired' }) } }
                '/scheduledActionConfigurations$' { return [pscustomobject]@{ value = @($global:T07.Actions | ForEach-Object { $p = $_ -split '\|'; [pscustomobject]@{ actionType = $p[0]; gracePeriodHours = [int]($p[1] -replace 'h', '') } }) } }
                '/assignments$' { return [pscustomobject]@{ value = @($global:T07.Assignments | ForEach-Object { [pscustomobject]@{ target = [pscustomobject]@{ '@odata.type' = '#microsoft.graph.groupAssignmentTarget'; groupId = ($_ -replace '^group:', '') } } }) } }
            }
        }
    }
    It 'finds the Windows policy by name and ignores other platforms with the same list' {
        $p = Get-IntuneCompliancePolicy -DisplayName 'MG Lab - Windows 11 baseline'
        $p.Id | Should -Be 'aaaaaaaa-0000-0000-0000-000000000007'
        $p.Actions | Should -Be @('block|24h')
        $p.Assignments | Should -Be @("group:$realGroup")
    }
    It 'returns $null when there is none' { Get-IntuneCompliancePolicy -DisplayName 'nope' | Should -BeNullOrEmpty }
    It 'follows @odata.nextLink' {
        Mock Invoke-MgGraphRequest -ModuleName IntuneDevices -ParameterFilter { $Uri -match '/deviceCompliancePolicies$' } {
            [pscustomobject]@{ value = @(); '@odata.nextLink' = '/v1.0/deviceManagement/deviceCompliancePolicies?$skiptoken=2' }
        }
        Mock Invoke-MgGraphRequest -ModuleName IntuneDevices -ParameterFilter { $Uri -match 'skiptoken=2' } {
            [pscustomobject]@{ value = @([pscustomobject]@{ id = 'cccccccc-0000-0000-0000-000000000007'; displayName = 'paged'; '@odata.type' = '#microsoft.graph.windows10CompliancePolicy' }) }
        }
        Mock Invoke-MgGraphRequest -ModuleName IntuneDevices { [pscustomobject]@{ value = @() } }
        (Get-IntuneCompliancePolicy -DisplayName 'paged').Id | Should -Be 'cccccccc-0000-0000-0000-000000000007'
    }
    It 'refuses to guess when two policies share the name' {
        Mock Invoke-MgGraphRequest -ModuleName IntuneDevices {
            [pscustomobject]@{ value = @(1, 2 | ForEach-Object { [pscustomobject]@{ id = "d$_"; displayName = 'dup'; '@odata.type' = '#microsoft.graph.windows10CompliancePolicy' } }) }
        }
        { Get-IntuneCompliancePolicy -DisplayName 'dup' } | Should -Throw '*More than one*'
    }
}

Describe 'Compare-IntuneCompliancePolicy' {
    BeforeAll { $script:live = Live-Config }
    function script:Existing($Override = @{}, $Actions = @('block|24h'), $Assign = @("group:$realGroup")) {
        [pscustomobject]@{ Id = 'x'; Policy = (Policy-From $live $Override); Actions = $Actions; Assignments = $Assign }
    }
    It 'is empty when the tenant matches the file' { @(Compare-IntuneCompliancePolicy -Existing (Existing) -Config $live).Count | Should -Be 0 }
    It 'names a changed setting with desired and actual' {
        $d = @(Compare-IntuneCompliancePolicy -Existing (Existing @{ passwordMinimumLength = 8 }) -Config $live)
        $d.Count | Should -Be 1
        $d[0].Name | Should -Be 'passwordMinimumLength'; $d[0].Desired | Should -Be 14; $d[0].Actual | Should -Be 8
    }
    It 'reports a setting the portal never set (property missing)' {
        $e = Existing; $e.Policy.PSObject.Properties.Remove('secureBootEnabled')
        (@(Compare-IntuneCompliancePolicy -Existing $e -Config $live) | Where-Object Name -eq 'secureBootEnabled').Count | Should -Be 1
    }
    It 'reports a different grace period' {
        $d = @(Compare-IntuneCompliancePolicy -Existing (Existing -Actions @('block|72h')) -Config $live)
        $d.Area | Should -Be 'Actions'; $d[0].Desired | Should -Be 'block|24h'
    }
    It 'reports a missing and a foreign assignment' {
        @(Compare-IntuneCompliancePolicy -Existing (Existing -Assign @()) -Config $live).Area | Should -Be 'Assignment'
        @(Compare-IntuneCompliancePolicy -Existing (Existing -Assign @('allLicensedUsers')) -Config $live).Area | Should -Be 'Assignment'
    }
}

Describe 'Set-IntuneCompliancePolicy (mocked Graph)' {
    BeforeAll {
        $script:liveCfg = Live-Config
        function script:Writes { , @($global:T07.Calls | Where-Object { $_.Method -ne 'GET' }) }
    }
    BeforeEach {
        Mock Invoke-MgGraphRequest -ModuleName IntuneDevices {
            $global:T07.Calls.Add(@{ Method = $Method; Uri = $Uri; Body = $Body })
            if ($Method -eq 'POST' -and $Uri -match '/deviceCompliancePolicies$') { return [pscustomobject]@{ id = 'aaaaaaaa-0000-0000-0000-000000000007' } }
            if ($Method -ne 'GET') { return $null }
            switch -Regex ($Uri) {
                '/deviceCompliancePolicies$' {
                    if (-not $global:T07.Policy) { return [pscustomobject]@{ value = @() } }
                    return [pscustomobject]@{ value = @($global:T07.Policy | Add-Member '@odata.type' '#microsoft.graph.windows10CompliancePolicy' -PassThru -Force) }
                }
                '/scheduledActionsForRule$' { return [pscustomobject]@{ value = @([pscustomobject]@{ id = 'r1' }) } }
                '/scheduledActionConfigurations$' { return [pscustomobject]@{ value = @($global:T07.Actions | ForEach-Object { $p = $_ -split '\|'; [pscustomobject]@{ actionType = $p[0]; gracePeriodHours = [int]($p[1] -replace 'h', '') } }) } }
                '/assignments$' { return [pscustomobject]@{ value = @($global:T07.Assignments | ForEach-Object { [pscustomobject]@{ target = [pscustomobject]@{ '@odata.type' = '#microsoft.graph.groupAssignmentTarget'; groupId = ($_ -replace '^group:', '') } } }) } }
            }
        }
    }
    It 'refuses the zero-GUID placeholder group before any call' {
        Reset-Tenant
        { Set-IntuneCompliancePolicy -Config $config } | Should -Throw '*zero-GUID placeholder*'
        $global:T07.Calls.Count | Should -Be 0
    }
    It 'creates the policy with its actions, then assigns it' {
        Reset-Tenant
        $r = Set-IntuneCompliancePolicy -Config $liveCfg -Confirm:$false
        $r.Action | Should -Be 'Created'
        $w = Writes
        $w.Count | Should -Be 2
        $w[0].Method | Should -Be 'POST'; $w[0].Uri | Should -Be '/v1.0/deviceManagement/deviceCompliancePolicies'
        $b = $w[0].Body | ConvertFrom-Json
        $b.'@odata.type' | Should -Be '#microsoft.graph.windows10CompliancePolicy'
        $b.scheduledActionsForRule[0].scheduledActionConfigurations[0].actionType | Should -Be 'block'
        $w[1].Uri | Should -Be '/v1.0/deviceManagement/deviceCompliancePolicies/aaaaaaaa-0000-0000-0000-000000000007/assign'
        ($w[1].Body | ConvertFrom-Json).assignments[0].target.groupId | Should -Be $realGroup
    }
    It '-WhatIf creates nothing' {
        Reset-Tenant
        (Set-IntuneCompliancePolicy -Config $liveCfg -WhatIf).Action | Should -Be 'WhatIf-Create'
        (Writes).Count | Should -Be 0
    }
    It 'does nothing when the tenant already matches' {
        Reset-Tenant -Policy (Policy-From $liveCfg) -Actions @('block|24h') -Assignments @("group:$realGroup")
        (Set-IntuneCompliancePolicy -Config $liveCfg -Confirm:$false).Action | Should -Be 'Unchanged'
        (Writes).Count | Should -Be 0
    }
    It 'patches only the settings that differ, and nothing else' {
        Reset-Tenant -Policy (Policy-From $liveCfg @{ passwordMinimumLength = 8; secureBootEnabled = $false }) -Actions @('block|24h') -Assignments @("group:$realGroup")
        $r = Set-IntuneCompliancePolicy -Config $liveCfg -Confirm:$false
        $r.Action | Should -Be 'Updated'
        $w = Writes
        $w.Count | Should -Be 1
        $w[0].Method | Should -Be 'PATCH'
        $w[0].Uri | Should -Be '/v1.0/deviceManagement/deviceCompliancePolicies/aaaaaaaa-0000-0000-0000-000000000007'
        $p = $w[0].Body | ConvertFrom-Json
        ($p.PSObject.Properties.Name | Sort-Object) | Should -Be @('@odata.type', 'passwordMinimumLength', 'secureBootEnabled')
    }
    It 'uses scheduleActionsForRules for a changed grace period (a PATCH cannot change actions)' {
        Reset-Tenant -Policy (Policy-From $liveCfg) -Actions @('block|72h') -Assignments @("group:$realGroup")
        Set-IntuneCompliancePolicy -Config $liveCfg -Confirm:$false | Out-Null
        $w = Writes
        $w.Count | Should -Be 1
        $w[0].Uri | Should -Match '/scheduleActionsForRules$'
        $rules = ($w[0].Body | ConvertFrom-Json).deviceComplianceScheduledActionForRules
        $rules[0].scheduledActionConfigurations[0].gracePeriodHours | Should -Be 24
    }
    It 're-assigns when the assignment differs' {
        Reset-Tenant -Policy (Policy-From $liveCfg) -Actions @('block|24h') -Assignments @()
        Set-IntuneCompliancePolicy -Config $liveCfg -Confirm:$false | Out-Null
        (Writes).Uri | Should -Match '/assign$'
    }
    It '-WhatIf on an update lists the changes and writes nothing' {
        Reset-Tenant -Policy (Policy-From $liveCfg @{ passwordMinimumLength = 8 }) -Actions @('block|72h') -Assignments @()
        $r = Set-IntuneCompliancePolicy -Config $liveCfg -WhatIf
        $r.Action | Should -Be 'WhatIf-Update'
        ($r.Changes.Area | Sort-Object -Unique) | Should -Be @('Actions', 'Assignment', 'Setting')
        (Writes).Count | Should -Be 0
    }
}

Describe 'Managed devices (mocked Graph)' {
    It 'pages, asks for $select, and keeps only Windows' {
        $script:uris = [System.Collections.Generic.List[string]]::new()
        Mock Invoke-MgGraphRequest -ModuleName IntuneDevices {
            if ($Uri -match 'skiptoken') { return [pscustomobject]@{ value = @([pscustomobject]@{ deviceName = 'W2'; operatingSystem = 'Windows' }) } }
            [pscustomobject]@{ value = @([pscustomobject]@{ deviceName = 'W1'; operatingSystem = 'Windows' }, [pscustomobject]@{ deviceName = 'M1'; operatingSystem = 'macOS' }); '@odata.nextLink' = '/v1.0/deviceManagement/managedDevices?$skiptoken=1' }
        }
        $d = @(Get-IntuneManagedDevice)
        ($d.deviceName | Sort-Object) | Should -Be @('W1', 'W2')
        Should -Invoke Invoke-MgGraphRequest -ModuleName IntuneDevices -Times 1 -ParameterFilter { $Uri -match '\$select=id,deviceName,userId' -and $Uri -match '\$top=100' }
        Should -Invoke Invoke-MgGraphRequest -ModuleName IntuneDevices -Times 2 -Exactly
    }
    It 'can return every platform' {
        Mock Invoke-MgGraphRequest -ModuleName IntuneDevices { [pscustomobject]@{ value = @([pscustomobject]@{ deviceName = 'W1'; operatingSystem = 'Windows' }, [pscustomobject]@{ deviceName = 'M1'; operatingSystem = 'macOS' }) } }
        @(Get-IntuneManagedDevice -OperatingSystem '').Count | Should -Be 2
    }
}

Describe 'Findings (fictional fixture, now = 2026-11-21 12:00 UTC)' {
    BeforeAll {
        $script:win = @($devices | Where-Object operatingSystem -eq 'Windows')
        $script:findings = @(Get-IntuneDeviceFinding -Devices $win -Config $config -Now $now)
        function script:F($rule, $dev) { @($findings | Where-Object { $_.Rule -eq $rule -and $_.Device -eq $dev }) }
    }
    It 'has no finding for the healthy device' { @($findings | Where-Object Device -eq 'CON-W11-01').Count | Should -Be 0 }
    It 'flags a noncompliant device High' { (F 'NonCompliant' 'CON-W11-02').Severity | Should -Be 'High' }
    It 'flags an unencrypted device High' { (F 'NotEncrypted' 'CON-W11-02').Count | Should -Be 1 }
    It 'flags a grace period with its expiry' { (F 'InGracePeriod' 'CON-W11-03').Message | Should -BeLike '*2026-11-22 08:00 UTC*' }
    It 'flags a stale check-in with the day count' {
        (F 'StaleCheckIn' 'LAPTOP-STALE02').Message | Should -BeLike 'last sync 62 days ago (limit 30)*'
        (F 'StaleCheckIn' 'CON-W11-01').Count | Should -Be 0
    }
    It 'flags a device that never synced' { (F 'NeverSynced' 'CON-W11-04-OLD').Count | Should -Be 1 }
    It 'flags an OS below the policy minimum' { (F 'OsBelowMinimum' 'DESKTOP-OLD01').Message | Should -BeLike '*10.0.19045.5011*10.0.26100.0*' }
    It 'flags userless and personal devices Low' {
        (F 'NoPrimaryUser' 'KIOSK-01').Severity | Should -Be 'Low'
        (F 'PersonalOwned' 'BYOD-PC-01').Severity | Should -Be 'Low'
    }
    It 'flags both records that share a serial number' {
        (F 'DuplicateSerial' 'CON-W11-04').Count | Should -Be 1
        (F 'DuplicateSerial' 'CON-W11-04-OLD').Message | Should -BeLike '*SER-0009*2 records*'
    }
    It 'sorts High before Medium before Low' {
        $sev = @($findings.Severity)
        $sev | Should -Be @($sev | Sort-Object { @{ High = 0; Medium = 1; Low = 2 }[$_] })
    }
    It 'counts 10 findings: 2 High, 5 Medium, 3 Low' {
        $findings.Count | Should -Be 10
        @($findings | Where-Object Severity -eq 'High').Count | Should -Be 2
        @($findings | Where-Object Severity -eq 'Medium').Count | Should -Be 5
        @($findings | Where-Object Severity -eq 'Low').Count | Should -Be 3
    }
    It 'honours a longer stale limit and switched-off checks' {
        $cfg = Get-IntuneConfig -Path (New-Config { param($c) $c.audit.staleDays = 90; $c.audit.requireEncryption = $false; $c.audit.flagPersonalOwned = $false })
        $f = @(Get-IntuneDeviceFinding -Devices $win -Config $cfg -Now $now)
        ($f.Rule | Sort-Object -Unique) | Should -Not -Contain 'StaleCheckIn'
        ($f.Rule | Sort-Object -Unique) | Should -Not -Contain 'NotEncrypted'
        ($f.Rule | Sort-Object -Unique) | Should -Not -Contain 'PersonalOwned'
    }
    It 'handles an empty list' {
        @(Get-IntuneDeviceFinding -Devices @() -Config $config -Now $now).Count | Should -Be 0
        @(Get-IntuneComplianceSummary -Devices @()).Count | Should -Be 0
    }
    It 'summarises compliance states with percentages' {
        $s = @(Get-IntuneComplianceSummary -Devices $win)
        ($s | Where-Object State -eq 'compliant').Devices | Should -Be 7
        ($s | Where-Object State -eq 'compliant').Percent | Should -Be 78
        ($s | Measure-Object Devices -Sum).Sum | Should -Be 9
    }
    It 'renders markdown with the table and the finding count' {
        $md = ConvertTo-IntuneMarkdown -Summary (Get-IntuneComplianceSummary -Devices $win) -Findings $findings -DeviceCount 9
        $md | Should -BeLike '*## Findings (10)*'
        $md | Should -BeLike '*| High | NonCompliant | CON-W11-02 |*'
    }
}

Describe 'Invoke-IntuneDeviceSync (mocked Graph)' {
    It 'POSTs syncDevice and reports it' {
        Mock Invoke-MgGraphRequest -ModuleName IntuneDevices { $null }
        $r = Invoke-IntuneDeviceSync -DeviceId '00000001-0000-0000-0000-000000000007' -DeviceName 'CON-W11-01' -Confirm:$false
        $r.Requested | Should -BeTrue
        Should -Invoke Invoke-MgGraphRequest -ModuleName IntuneDevices -Times 1 -Exactly -ParameterFilter { $Method -eq 'POST' -and $Uri -eq '/v1.0/deviceManagement/managedDevices/00000001-0000-0000-0000-000000000007/syncDevice' }
    }
    It '-WhatIf sends nothing' {
        Mock Invoke-MgGraphRequest -ModuleName IntuneDevices { $null }
        Invoke-IntuneDeviceSync -DeviceId '00000001-0000-0000-0000-000000000007' -WhatIf | Should -BeNullOrEmpty
        Should -Invoke Invoke-MgGraphRequest -ModuleName IntuneDevices -Times 0 -Exactly
    }
    It 'refuses an id that is not a GUID' { { Invoke-IntuneDeviceSync -DeviceId 'CON-W11-01' } | Should -Throw '*not a GUID*' }
}

Describe 'Our Graph calls against the real Microsoft.Graph.Authentication module' {
    It 'only uses parameters that Invoke-MgGraphRequest really has' -Skip:(-not (Get-Module -ListAvailable Microsoft.Graph.Authentication)) {
        Import-Module Microsoft.Graph.Authentication -Force
        $params = (Get-Command Invoke-MgGraphRequest -Module Microsoft.Graph.Authentication).Parameters.Keys
        $ast = [System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path "$PSScriptRoot/../src/IntuneDevices/IntuneDevices.psm1").Path, [ref]$null, [ref]$null)
        $calls = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.CommandAst] -and $n.GetCommandName() -eq 'Invoke-MgGraphRequest' }, $true)
        $calls.Count | Should -BeGreaterThan 8
        $used = $calls | ForEach-Object { $_.CommandElements | Where-Object { $_ -is [System.Management.Automation.Language.CommandParameterAst] } | ForEach-Object ParameterName } | Sort-Object -Unique
        $used | Where-Object { $_ -notin $params } | Should -BeNullOrEmpty
        $used | Should -Contain 'Method'
    }
}
