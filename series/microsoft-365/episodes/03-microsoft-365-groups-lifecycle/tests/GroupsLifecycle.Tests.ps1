BeforeAll {
    if (-not (Get-Command Invoke-MgGraphRequest -ErrorAction SilentlyContinue)) {
        function global:Invoke-MgGraphRequest { param($Method, $Uri, $Body, $Headers, $OutputFilePath, $OutputType, $ContentType, $ErrorAction) throw 'stub' }
    }
    Import-Module "$PSScriptRoot/../src/GroupsLifecycle/GroupsLifecycle.psd1" -Force
    $script:fx = "$PSScriptRoot/fixtures"
    $script:config = Get-GroupsLifecycleConfig -Path "$PSScriptRoot/../src/lifecycle.json"
    $script:inventory = Get-Content "$fx/inventory.json" -Raw | ConvertFrom-Json
    $script:now = [datetimeoffset]'2026-11-20T09:30:00Z'
    function script:New-Config([scriptblock]$Change) {
        $c = Get-Content "$PSScriptRoot/../src/lifecycle.json" -Raw | ConvertFrom-Json
        & $Change $c
        $p = Join-Path $TestDrive ("cfg-{0}.json" -f [guid]::NewGuid()); $c | ConvertTo-Json -Depth 5 | Set-Content $p; $p
    }
    function script:Find($Rule, $Target) { @($findings | Where-Object { $_.Rule -eq $Rule -and $_.Target -eq $Target }) }
}

Describe 'Config file' {
    It 'loads the sample config' {
        $config.expiration.groupLifetimeInDays | Should -Be 180
        $config.expiration.managedGroupTypes | Should -Be 'Selected'
    }
    It 'rejects a lifetime under 30 days' {
        { Get-GroupsLifecycleConfig -Path (New-Config { param($c) $c.expiration.groupLifetimeInDays = 29 }) } | Should -Throw '*30 or more*'
    }
    It 'accepts exactly 30 days' {
        (Get-GroupsLifecycleConfig -Path (New-Config { param($c) $c.expiration.groupLifetimeInDays = 30 })).expiration.groupLifetimeInDays | Should -Be 30
    }
    It 'rejects an unknown managedGroupTypes value (case-sensitive like the API values)' {
        { Get-GroupsLifecycleConfig -Path (New-Config { param($c) $c.expiration.managedGroupTypes = 'all' }) } | Should -Throw '*All, Selected or None*'
    }
    It 'rejects more than 500 selected groups' {
        $p = New-Config { param($c) $c.expiration.selectedGroupIds = @(1..501 | ForEach-Object { '00000000-0000-0000-0000-{0:D12}' -f $_ }) }
        { Get-GroupsLifecycleConfig -Path $p } | Should -Throw '*up to 500*'
    }
    It 'rejects Selected with no groups' {
        { Get-GroupsLifecycleConfig -Path (New-Config { param($c) $c.expiration.selectedGroupIds = @() }) } | Should -Throw '*selectedGroupIds is empty*'
    }
    It 'rejects a malformed alternate email' {
        { Get-GroupsLifecycleConfig -Path (New-Config { param($c) $c.expiration.alternateNotificationEmails = @('a@contoso.com;b@contoso.com') }) } | Should -Throw '*Not an email*'
    }
}

Describe 'Policy body and drift' {
    It 'builds the groupLifecyclePolicy body with a semicolon-separated email string' {
        $p = Get-GroupsLifecycleConfig -Path (New-Config { param($c) $c.expiration.alternateNotificationEmails = @('a@contoso.com', 'b@contoso.com') })
        $b = ConvertTo-GroupLifecyclePolicyBody $p
        $b.groupLifetimeInDays | Should -Be 180
        $b.managedGroupTypes | Should -Be 'Selected'
        $b.alternateNotificationEmails | Should -Be 'a@contoso.com;b@contoso.com'
        @($b.Keys) | Should -Not -Contain 'selectedGroupIds'
    }
    It 'reports only the properties that differ' {
        $cur = [pscustomobject]@{ groupLifetimeInDays = 365; managedGroupTypes = 'Selected'; alternateNotificationEmails = 'm365-groups-admin@contoso.com' }
        Compare-GroupLifecyclePolicy -Current $cur -Desired (ConvertTo-GroupLifecyclePolicyBody $config) | Should -Be 'groupLifetimeInDays'
    }
    It 'compares emails as a set (order, case, spaces)' {
        $cur = [pscustomobject]@{ groupLifetimeInDays = 180; managedGroupTypes = 'Selected'; alternateNotificationEmails = ' B@contoso.com ; a@contoso.com' }
        $d = [ordered]@{ groupLifetimeInDays = 180; managedGroupTypes = 'Selected'; alternateNotificationEmails = 'a@contoso.com;b@contoso.com' }
        Compare-GroupLifecyclePolicy -Current $cur -Desired $d | Should -BeNullOrEmpty
    }
}

Describe 'Rollout impact (first time expiration is set)' {
    It 'gives groups older than the lifetime 35 days' {
        $r = @(Get-ExpirationRolloutImpact -Groups @($inventory.groups) -LifetimeDays 180 -Now $now)
        $r.Group | Should -Be @('TEAM_Sales_Partner Portal', 'Contoso Book Club')
        $r[0].Outcome | Should -Be 'SetTo35Days'
        $r[0].ExpiresAround | Should -Be '2026-12-25'
    }
    It 'skips groups that already have an expiration date' {
        (Get-ExpirationRolloutImpact -Groups @($inventory.groups) -LifetimeDays 180 -Now $now).GroupId | Should -Not -Contain '00000000-0000-0000-0000-000000000202'
    }
    It 'limits the preview to the selected groups' {
        @(Get-ExpirationRolloutImpact -Groups @($inventory.groups) -LifetimeDays 180 -Now $now -OnlyGroupIds $config.expiration.selectedGroupIds).Group | Should -Be 'TEAM_Sales_Partner Portal'
    }
    It 'does not invent a date for groups younger than the lifetime' {
        $young = [pscustomobject]@{ id = 'x'; displayName = 'New'; createdDateTime = '2026-10-01T00:00:00Z'; expirationDateTime = $null }
        $r = Get-ExpirationRolloutImpact -Groups @($young) -LifetimeDays 180 -Now $now
        $r.Outcome | Should -Be 'WithinLifetime'
        $r.ExpiresAround | Should -BeNullOrEmpty
    }
}

Describe 'Lifecycle findings' {
    BeforeAll { $script:findings = @(Get-GroupsLifecycleFinding -Inventory $inventory -Config $config -Now $now) }
    It 'finds 7 issues on the fictional tenant (2 High, 3 Medium, 1 Low, 1 Info)' {
        $findings.Count | Should -Be 7
        @($findings | Where-Object Severity -EQ 'High').Count | Should -Be 2
        @($findings | Where-Object Severity -EQ 'Medium').Count | Should -Be 3
    }
    It 'flags <Rule> on <Target> as <Severity>' -ForEach @(
        @{ Rule = 'OwnerlessExpiring'; Target = 'Old Offsite 2024'; Severity = 'High' }
        @{ Rule = 'PurgeSoon'; Target = 'Marketing Events 2025'; Severity = 'High' }
        @{ Rule = 'ExpiringSoon'; Target = 'Project Falcon'; Severity = 'Medium' }
        @{ Rule = 'NotCoveredByPolicy'; Target = 'TEAM_Sales_Partner Portal'; Severity = 'Medium' }
        @{ Rule = 'PolicyDrift'; Target = 'Tenant'; Severity = 'Medium' }
        @{ Rule = 'SingleOwner'; Target = 'Project Falcon'; Severity = 'Low' }
        @{ Rule = 'Restorable'; Target = 'Temp Project Kickoff'; Severity = 'Info' }
    ) { (Find $Rule $Target).Severity | Should -Be $Severity }
    It 'says nobody gets the renewal mail when there is no owner and no alternate email' {
        (Find 'OwnerlessExpiring' 'Old Offsite 2024').Detail | Should -BeLike '*to nobody*cannot be archived*'
    }
    It 'names the alternate address once one is configured' {
        $inv = $inventory | ConvertTo-Json -Depth 5 | ConvertFrom-Json
        $inv.policy.alternateNotificationEmails = 'm365-groups-admin@contoso.com'
        $f = @(Get-GroupsLifecycleFinding -Inventory $inv -Config $config -Now $now)
        ($f | Where-Object Rule -EQ 'OwnerlessExpiring').Detail | Should -BeLike '*only to m365-groups-admin@contoso.com*'
        $f.Rule | Should -Not -Contain 'PolicyDrift'
    }
    It 'computes the permanent deletion date as deleted + 30 days' {
        (Get-GroupPurgeDate '2026-10-24T12:00:00Z').ToString('o') | Should -Be '2026-11-23T12:00:00.0000000+00:00'
        (Find 'PurgeSoon' 'Marketing Events 2025').Detail | Should -BeLike '*2026-11-23 (3 days left)*'
    }
    It 'ignores groups outside a Selected rollout, and flags them under All' {
        (Find 'NotCoveredByPolicy' 'Contoso Book Club').Count | Should -Be 0
        $inv = $inventory | ConvertTo-Json -Depth 5 | ConvertFrom-Json
        $inv.policy.managedGroupTypes = 'All'
        @(Get-GroupsLifecycleFinding -Inventory $inv -Config $config -Now $now | Where-Object { $_.Rule -eq 'NotCoveredByPolicy' }).Target | Should -Contain 'Contoso Book Club'
    }
    It 'reports a missing tenant policy as High' {
        $inv = $inventory | ConvertTo-Json -Depth 5 | ConvertFrom-Json
        $inv.policy = $null
        (Get-GroupsLifecycleFinding -Inventory $inv -Config $config -Now $now | Where-Object Rule -EQ 'NoExpirationPolicy').Severity | Should -Be 'High'
    }
    It 'treats a past expiration date as Expired' {
        $inv = $inventory | ConvertTo-Json -Depth 5 | ConvertFrom-Json
        $inv.groups[1].expirationDateTime = '2026-11-19T10:00:00Z'
        (Get-GroupsLifecycleFinding -Inventory $inv -Config $config -Now $now | Where-Object { $_.Target -eq 'Project Falcon' }).Rule | Should -Contain 'Expired'
    }
    It 'skips deleted security groups and groups already past the 30 days' {
        $inv = $inventory | ConvertTo-Json -Depth 5 | ConvertFrom-Json
        $inv.deletedGroups = @(
            [pscustomobject]@{ id = 'a'; displayName = 'Sec group'; deletedDateTime = '2026-11-19T00:00:00Z'; groupTypes = @() }
            [pscustomobject]@{ id = 'b'; displayName = 'Long gone'; deletedDateTime = '2026-09-01T00:00:00Z'; groupTypes = @('Unified') }
        )
        @(Get-GroupsLifecycleFinding -Inventory $inv -Config $config -Now $now | Where-Object { $_.Target -in 'Sec group', 'Long gone' }).Count | Should -Be 0
    }
    It 'renders a Markdown report with every finding and every group' {
        $md = ConvertTo-GroupsLifecycleMarkdown -Inventory $inventory -Findings $findings -Now $now
        ($md | Where-Object { $_ -like '| High |*' }).Count | Should -Be 2
        $md | Should -Contain '| Old Offsite 2024 | yes | 0 | 2026-12-24 | 2026-06-27 |'
    }
}

Describe 'Inventory (mocked Graph)' {
    BeforeAll {
        Mock Invoke-MgGraphRequest -ModuleName GroupsLifecycle -ParameterFilter { $Uri -eq '/v1.0/groupLifecyclePolicies' } {
            [pscustomobject]@{ value = @([pscustomobject]@{ id = '00000000-0000-0000-0000-000000000401'; groupLifetimeInDays = 180; managedGroupTypes = 'Selected'; alternateNotificationEmails = '' }) }
        }
        Mock Invoke-MgGraphRequest -ModuleName GroupsLifecycle -ParameterFilter { $Uri -like '/v1.0/groups?*' } {
            [pscustomobject]@{ value = @([pscustomobject]@{ id = 'g1'; displayName = 'Project Falcon'; createdDateTime = '2026-03-01T09:00:00Z'; expirationDateTime = '2026-12-05T10:00:00Z'; renewedDateTime = $null; resourceProvisioningOptions = @('Team') })
                '@odata.nextLink' = 'https://graph.microsoft.com/v1.0/groups?$skiptoken=page2' }
        }
        Mock Invoke-MgGraphRequest -ModuleName GroupsLifecycle -ParameterFilter { $Uri -like '*skiptoken=page2' } {
            [pscustomobject]@{ value = @([pscustomobject]@{ id = 'g2'; displayName = 'Contoso Book Club'; createdDateTime = '2023-02-01T08:00:00Z'; expirationDateTime = $null; renewedDateTime = $null; resourceProvisioningOptions = @() }) }
        }
        Mock Invoke-MgGraphRequest -ModuleName GroupsLifecycle -ParameterFilter { $Uri -eq '/v1.0/groups/g1/owners' } { [pscustomobject]@{ value = @([pscustomobject]@{ id = 'u1' }) } }
        Mock Invoke-MgGraphRequest -ModuleName GroupsLifecycle -ParameterFilter { $Uri -eq '/v1.0/groups/g2/owners' } { [pscustomobject]@{ value = @() } }
        Mock Invoke-MgGraphRequest -ModuleName GroupsLifecycle -ParameterFilter { $Uri -like '/v1.0/directory/deletedItems/microsoft.graph.group*' } {
            [pscustomobject]@{ value = @(
                    [pscustomobject]@{ id = 'd1'; displayName = 'Marketing Events 2025'; deletedDateTime = '2026-10-24T12:00:00Z'; groupTypes = @('Unified') }
                    [pscustomobject]@{ id = 'd2'; displayName = 'Old security group'; deletedDateTime = '2026-11-01T12:00:00Z'; groupTypes = @() }) }
        }
        $script:inv = Get-GroupsLifecycleInventory
    }
    It 'reads the tenant policy' { $inv.policy.managedGroupTypes | Should -Be 'Selected' }
    It 'reads every page of Microsoft 365 groups' { $inv.groups.displayName | Should -Be @('Project Falcon', 'Contoso Book Club') }
    It 'filters on Unified and selects the lifecycle properties' {
        Should -Invoke Invoke-MgGraphRequest -ModuleName GroupsLifecycle -Times 1 -Exactly -Scope Describe -ParameterFilter {
            $Uri -like "*groupTypes/any(c:c+eq+'Unified')*" -and $Uri -like '*expirationDateTime,renewedDateTime*'
        }
    }
    It 'counts owners and detects teams' {
        $inv.groups[0].ownerCount | Should -Be 1
        $inv.groups[0].isTeam | Should -BeTrue
        $inv.groups[1].ownerCount | Should -Be 0
    }
    It 'keeps only deleted Microsoft 365 groups' { $inv.deletedGroups.displayName | Should -Be 'Marketing Events 2025' }
}

Describe 'Set-GroupsExpirationPolicy (mocked Graph)' {
    It 'creates the policy when none exists, then adds each selected group' {
        Mock Invoke-MgGraphRequest -ModuleName GroupsLifecycle -ParameterFilter { $Method -eq 'GET' } { [pscustomobject]@{ value = @() } }
        Mock Invoke-MgGraphRequest -ModuleName GroupsLifecycle -ParameterFilter { $Method -eq 'POST' -and $Uri -eq '/v1.0/groupLifecyclePolicies' } {
            $script:created = $Body | ConvertFrom-Json; [pscustomobject]@{ id = 'p1' }
        }
        Mock Invoke-MgGraphRequest -ModuleName GroupsLifecycle -ParameterFilter { $Uri -like '*/addGroup' } { [pscustomobject]@{ value = $true } }
        $r = @(Set-GroupsExpirationPolicy -Config $config -Confirm:$false)
        $created.groupLifetimeInDays | Should -Be 180
        $created.alternateNotificationEmails | Should -Be 'm365-groups-admin@contoso.com'
        ($r | Where-Object Step -EQ 'AddGroup').Result | Should -Be @('Added', 'Added', 'Added', 'Added')
        Should -Invoke Invoke-MgGraphRequest -ModuleName GroupsLifecycle -Times 4 -Exactly -ParameterFilter { $Uri -eq '/v1.0/groupLifecyclePolicies/p1/addGroup' }
    }
    It 'PATCHes only the properties that differ' {
        Mock Invoke-MgGraphRequest -ModuleName GroupsLifecycle -ParameterFilter { $Method -eq 'GET' } {
            [pscustomobject]@{ value = @([pscustomobject]@{ id = 'p1'; groupLifetimeInDays = 180; managedGroupTypes = 'Selected'; alternateNotificationEmails = '' }) }
        }
        Mock Invoke-MgGraphRequest -ModuleName GroupsLifecycle -ParameterFilter { $Method -eq 'PATCH' } { $script:patched = $Body | ConvertFrom-Json -AsHashtable }
        Mock Invoke-MgGraphRequest -ModuleName GroupsLifecycle -ParameterFilter { $Uri -like '*/addGroup' } { [pscustomobject]@{ value = $false } }
        $r = @(Set-GroupsExpirationPolicy -Config $config -Confirm:$false)
        @($patched.Keys) | Should -Be @('alternateNotificationEmails')
        $r[0].Result | Should -Be 'Updated: alternateNotificationEmails'
        $r[1].Result | Should -Be 'NotAdded (false)'
    }
    It 'changes nothing with -WhatIf' {
        Mock Invoke-MgGraphRequest -ModuleName GroupsLifecycle -ParameterFilter { $Method -eq 'GET' } { [pscustomobject]@{ value = @() } }
        Mock Invoke-MgGraphRequest -ModuleName GroupsLifecycle -ParameterFilter { $Method -ne 'GET' } { throw 'should not be called' }
        $r = @(Set-GroupsExpirationPolicy -Config $config -WhatIf)
        $r[0].Result | Should -Be 'WhatIf: create'
        Should -Invoke Invoke-MgGraphRequest -ModuleName GroupsLifecycle -Times 0 -ParameterFilter { $Method -ne 'GET' }
    }
    It 'refuses to guess when the tenant returns more than one policy' {
        Mock Invoke-MgGraphRequest -ModuleName GroupsLifecycle -ParameterFilter { $Method -eq 'GET' } { [pscustomobject]@{ value = @([pscustomobject]@{ id = 'a' }, [pscustomobject]@{ id = 'b' }) } }
        { Set-GroupsExpirationPolicy -Config $config -Confirm:$false } | Should -Throw '*at most one*'
    }
}

Describe 'Renew, restore, archive (mocked Graph)' {
    It 'renews with POST /groups/{id}/renew and reads back the new dates' {
        Mock Invoke-MgGraphRequest -ModuleName GroupsLifecycle -ParameterFilter { $Method -eq 'POST' } { }
        Mock Invoke-MgGraphRequest -ModuleName GroupsLifecycle -ParameterFilter { $Method -eq 'GET' } {
            [pscustomobject]@{ id = 'g1'; displayName = 'Project Falcon'; renewedDateTime = '2026-11-20T09:31:00Z'; expirationDateTime = '2027-05-19T09:31:00Z' }
        }
        $r = Invoke-GroupRenewal -GroupId 'g1' -Confirm:$false
        $r.ExpirationDateTime | Should -Not -BeNullOrEmpty
        Should -Invoke Invoke-MgGraphRequest -ModuleName GroupsLifecycle -Times 1 -Exactly -ParameterFilter { $Method -eq 'POST' -and $Uri -eq '/v1.0/groups/g1/renew' -and $null -eq $Body }
    }
    It 'does not renew on -WhatIf' {
        Mock Invoke-MgGraphRequest -ModuleName GroupsLifecycle { throw 'should not be called' }
        Invoke-GroupRenewal -GroupId 'g1' -WhatIf
        Should -Invoke Invoke-MgGraphRequest -ModuleName GroupsLifecycle -Times 0
    }
    It 'restores a deleted Microsoft 365 group inside the 30 days' {
        Mock Invoke-MgGraphRequest -ModuleName GroupsLifecycle -ParameterFilter { $Method -eq 'GET' } {
            [pscustomobject]@{ '@odata.type' = '#microsoft.graph.group'; id = 'd1'; displayName = 'Marketing Events 2025'; deletedDateTime = '2026-10-24T12:00:00Z'; groupTypes = @('Unified') }
        }
        Mock Invoke-MgGraphRequest -ModuleName GroupsLifecycle -ParameterFilter { $Method -eq 'POST' } { [pscustomobject]@{ id = 'd1'; displayName = 'Marketing Events 2025' } }
        (Restore-DeletedM365Group -GroupId 'd1' -Now $now -Confirm:$false).Status | Should -Be 'Restored'
        Should -Invoke Invoke-MgGraphRequest -ModuleName GroupsLifecycle -Times 1 -Exactly -ParameterFilter { $Uri -eq '/v1.0/directory/deletedItems/d1/restore' }
    }
    It 'refuses to restore after the 30 days, or a non-Microsoft 365 group' {
        Mock Invoke-MgGraphRequest -ModuleName GroupsLifecycle -ParameterFilter { $Uri -eq '/v1.0/directory/deletedItems/old' } {
            [pscustomobject]@{ '@odata.type' = '#microsoft.graph.group'; id = 'old'; displayName = 'Old'; deletedDateTime = '2026-10-01T00:00:00Z'; groupTypes = @('Unified') }
        }
        Mock Invoke-MgGraphRequest -ModuleName GroupsLifecycle -ParameterFilter { $Uri -eq '/v1.0/directory/deletedItems/sec' } {
            [pscustomobject]@{ '@odata.type' = '#microsoft.graph.group'; id = 'sec'; displayName = 'Sec'; deletedDateTime = '2026-11-19T00:00:00Z'; groupTypes = @() }
        }
        Mock Invoke-MgGraphRequest -ModuleName GroupsLifecycle -ParameterFilter { $Method -eq 'POST' } { throw 'should not be called' }
        { Restore-DeletedM365Group -GroupId 'old' -Now $now -Confirm:$false } | Should -Throw '*more than 30 days*'
        { Restore-DeletedM365Group -GroupId 'sec' -Now $now -Confirm:$false } | Should -Throw '*not a Microsoft 365 group*'
    }
    It 'refuses to archive a team without an owner' {
        Mock Invoke-MgGraphRequest -ModuleName GroupsLifecycle -ParameterFilter { $Uri -eq '/v1.0/groups/t1/owners' } { [pscustomobject]@{ value = @() } }
        Mock Invoke-MgGraphRequest -ModuleName GroupsLifecycle -ParameterFilter { $Method -eq 'POST' } { throw 'should not be called' }
        { Invoke-TeamArchive -TeamId 't1' -Confirm:$false } | Should -Throw '*has no owner*'
    }
    It 'archives, sends the SharePoint read-only flag and follows the Location header' {
        Mock Invoke-MgGraphRequest -ModuleName GroupsLifecycle -ParameterFilter { $Uri -eq '/v1.0/groups/t2/owners' } { [pscustomobject]@{ value = @([pscustomobject]@{ id = 'u1' }) } }
        Mock Invoke-MgGraphRequest -ModuleName GroupsLifecycle -ParameterFilter { $Method -eq 'POST' } {
            $script:archiveBody = $Body | ConvertFrom-Json
            $r = [System.Net.Http.HttpResponseMessage]::new([System.Net.HttpStatusCode]::Accepted)
            $r.Headers.Location = [uri]::new('/teams(t2)/operations(op1)', [UriKind]::Relative); $r
        }
        $script:polls = 0
        Mock Invoke-MgGraphRequest -ModuleName GroupsLifecycle -ParameterFilter { $Uri -eq '/v1.0/teams(t2)/operations(op1)' } {
            $script:polls++; if ($script:polls -lt 2) { [pscustomobject]@{ status = 'inProgress' } } else { [pscustomobject]@{ status = 'succeeded' } }
        }
        Mock Start-Sleep -ModuleName GroupsLifecycle { }
        (Invoke-TeamArchive -TeamId 't2' -SetSpoSiteReadOnlyForMembers -Confirm:$false).Status | Should -Be 'Archived'
        $archiveBody.shouldSetSpoSiteReadOnlyForMembers | Should -BeTrue
        $script:polls | Should -Be 2
    }
}

Describe 'Real Microsoft Graph PowerShell parameters' -Skip:(-not (Get-Module -ListAvailable Microsoft.Graph.Authentication)) {
    It 'Invoke-MgGraphRequest has every parameter and output type the module uses' {
        $cmd = Get-Command Invoke-MgGraphRequest
        foreach ($name in 'Method', 'Uri', 'Body', 'ContentType', 'OutputType') { $cmd.Parameters.Keys | Should -Contain $name }
        [enum]::GetNames($cmd.Parameters['OutputType'].ParameterType) | Should -Contain 'HttpResponseMessage'
        [enum]::GetNames($cmd.Parameters['Method'].ParameterType) | Should -Contain 'PATCH'
    }
    It 'Get-MgContext exists (used to skip a second sign-in)' { Get-Command Get-MgContext | Should -Not -BeNullOrEmpty }
}
