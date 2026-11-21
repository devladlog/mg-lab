BeforeAll {
    if (-not (Get-Command Invoke-MgGraphRequest -ErrorAction SilentlyContinue)) {
        function global:Invoke-MgGraphRequest { param($Method, $Uri, $Body, $Headers, $OutputFilePath, $OutputType, $ContentType, $ErrorAction) throw 'stub' }
    }
    Import-Module "$PSScriptRoot/../src/TeamsGovernance/TeamsGovernance.psd1" -Force
    $script:fx = "$PSScriptRoot/fixtures"
    $script:policy = Get-TeamsGovernancePolicy -Path "$PSScriptRoot/../src/governance.json"
    $script:finance = @{ Department = 'Finance' }
}

Describe 'Policy file' {
    It 'loads the sample policy' { $policy.owners.minimum | Should -Be 2 }
    It 'rejects a convention without [GroupName]' {
        $bad = Join-Path $TestDrive 'bad.json'
        '{"naming":{"prefixSuffix":"TEAM_[Department]","blockedWords":[]},"owners":{"minimum":2},"visibility":{"default":"private"}}' | Set-Content $bad
        { Get-TeamsGovernancePolicy -Path $bad } | Should -Throw '*exactly once*'
    }
}

Describe 'Naming' {
    It 'applies prefix and user attribute' {
        $r = Resolve-TeamName -RequestedName 'Budget 2027' -Creator $finance -Policy $policy
        $r.DisplayName | Should -Be 'TEAM_Finance_Budget 2027'
        $r.Errors | Should -BeNullOrEmpty
    }
    It 'derives an alias without spaces' {
        (Resolve-TeamName -RequestedName 'Budget 2027' -Creator $finance -Policy $policy).MailNickname | Should -Be 'TEAM_Finance_Budget2027'
    }
    It 'flags a blocked word, case-insensitive' {
        (Resolve-TeamName -RequestedName 'payroll review' -Creator $finance -Policy $policy).Errors | Should -Contain 'BlockedWord:Payroll'
    }
    It 'does not do substring matches (<Name>)' -ForEach @(
        @{ Name = 'HRIS rollout' }, @{ Name = 'Chrome extensions' }, @{ Name = 'CEOs summit' }
    ) { Test-TeamsBlockedWord -Name $Name -BlockedWords $policy.naming.blockedWords | Should -BeNullOrEmpty }
    It 'matches whole words next to punctuation' {
        Test-TeamsBlockedWord -Name 'Ask-the-CEO (Q&A)' -BlockedWords $policy.naming.blockedWords | Should -Be 'CEO'
    }
    It 'rejects names over 63 characters including prefix and suffix' {
        $r = Resolve-TeamName -RequestedName ('x' * 51) -Creator $finance -Policy $policy
        $r.DisplayName.Length | Should -Be 64
        $r.Errors | Should -Contain 'TooLong:64'
    }
    It 'accepts exactly 63 characters' {
        (Resolve-TeamName -RequestedName ('x' * 50) -Creator $finance -Policy $policy).Errors | Should -BeNullOrEmpty
    }
    It 'reports a missing creator attribute' {
        (Resolve-TeamName -RequestedName 'Ops' -Creator @{ Department = '' } -Policy $policy).Errors | Should -Contain 'MissingAttribute:Department'
    }
    It 'keeps unsupported attributes as fixed text, like the service' {
        $p = $policy | ConvertTo-Json -Depth 5 | ConvertFrom-Json
        $p.naming.prefixSuffix = 'GRP_[GroupName]_[postalCode]'
        (Resolve-TeamName -RequestedName 'Ops' -Creator $finance -Policy $p).DisplayName | Should -Be 'GRP_Ops_[postalCode]'
    }
    It 'recognises compliant existing names' {
        Test-TeamNameCompliance -Name 'TEAM_IT_Service Desk' -Policy $policy | Should -BeTrue
        Test-TeamNameCompliance -Name 'Project Falcon' -Policy $policy | Should -BeFalse
    }
}

Describe 'Create request' {
    It 'is private by default, because the API default is public' {
        (New-TeamsCreateRequest -DisplayName 'TEAM_Finance_X' -OwnerIds 'a', 'b' -Policy $policy).visibility | Should -Be 'private'
    }
    It 'binds the standard template and every owner' {
        $b = New-TeamsCreateRequest -DisplayName 'TEAM_Finance_X' -OwnerIds '00000000-0000-0000-0000-000000000101', '00000000-0000-0000-0000-000000000102' -Policy $policy
        $b.'template@odata.bind' | Should -Be "https://graph.microsoft.com/v1.0/teamsTemplates('standard')"
        $b.members.Count | Should -Be 2
        $b.members[0].roles | Should -Be 'owner'
        $b.members[1].'user@odata.bind' | Should -Be "https://graph.microsoft.com/v1.0/users('00000000-0000-0000-0000-000000000102')"
    }
    It 'refuses fewer owners than the policy minimum (duplicates count once)' {
        { New-TeamsCreateRequest -DisplayName 'X' -OwnerIds 'a', 'a' -Policy $policy } | Should -Throw '*at least 2 owners*'
    }
    It 'turns the relative Location header into a callable URI' {
        Resolve-TeamsOperationUri "/teams('00000000-0000-0000-0000-000000000201')/operations('00000000-0000-0000-0000-000000000301')" |
            Should -Be "/v1.0/teams('00000000-0000-0000-0000-000000000201')/operations('00000000-0000-0000-0000-000000000301')"
    }
}

Describe 'New-GovernedTeam (mocked Graph)' {
    BeforeAll {
        $script:owners = '00000000-0000-0000-0000-000000000101', '00000000-0000-0000-0000-000000000102'
    }
    It 'does nothing with -WhatIf and returns the body it would send' {
        Mock Invoke-MgGraphRequest -ModuleName TeamsGovernance { throw 'should not be called' }
        $r = New-GovernedTeam -RequestedName 'Budget 2027' -Creator $finance -OwnerIds $owners -Policy $policy -WhatIf
        $r.Status | Should -Be 'WhatIf'
        $r.DisplayName | Should -Be 'TEAM_Finance_Budget 2027'
        Should -Invoke Invoke-MgGraphRequest -ModuleName TeamsGovernance -Times 0
    }
    It 'stops before Graph when the name breaks the policy' {
        Mock Invoke-MgGraphRequest -ModuleName TeamsGovernance { throw 'should not be called' }
        { New-GovernedTeam -RequestedName 'CEO office' -Creator $finance -OwnerIds $owners -Policy $policy -Confirm:$false } | Should -Throw '*BlockedWord:CEO*'
    }
    It 'posts, follows the Location header and returns the new team id' {
        Mock Invoke-MgGraphRequest -ModuleName TeamsGovernance -ParameterFilter { $Method -eq 'POST' } {
            $script:sentBody = $Body | ConvertFrom-Json
            $r = [System.Net.Http.HttpResponseMessage]::new([System.Net.HttpStatusCode]::Accepted)
            $r.Headers.Location = [uri]::new("/teams('00000000-0000-0000-0000-000000000207')/operations('00000000-0000-0000-0000-000000000307')", [UriKind]::Relative)
            $r
        }
        $script:polls = 0
        Mock Invoke-MgGraphRequest -ModuleName TeamsGovernance -ParameterFilter { $Method -eq 'GET' -and $Uri -like '/v1.0/teams(*)/operations(*)' } {
            $script:polls++
            if ($script:polls -lt 2) { [pscustomobject]@{ status = 'inProgress' } }
            else { [pscustomobject]@{ status = 'succeeded'; targetResourceId = '00000000-0000-0000-0000-000000000207' } }
        }
        Mock Start-Sleep -ModuleName TeamsGovernance { }
        $r = New-GovernedTeam -RequestedName 'Budget 2027' -Creator $finance -OwnerIds $owners -Policy $policy -Confirm:$false
        $r.Status | Should -Be 'Created'
        $r.TeamId | Should -Be '00000000-0000-0000-0000-000000000207'
        $sentBody.visibility | Should -Be 'private'
        $sentBody.displayName | Should -Be 'TEAM_Finance_Budget 2027'
        $script:polls | Should -Be 2
    }
    It 'surfaces a failed async operation' {
        Mock Invoke-MgGraphRequest -ModuleName TeamsGovernance -ParameterFilter { $Method -eq 'POST' } {
            $r = [System.Net.Http.HttpResponseMessage]::new([System.Net.HttpStatusCode]::Accepted)
            $r.Headers.Location = [uri]::new("/teams('x')/operations('y')", [UriKind]::Relative); $r
        }
        Mock Invoke-MgGraphRequest -ModuleName TeamsGovernance -ParameterFilter { $Method -eq 'GET' } {
            [pscustomobject]@{ status = 'failed'; error = [pscustomobject]@{ code = 'Conflict'; message = 'duplicate' } }
        }
        { New-GovernedTeam -RequestedName 'Budget 2027' -Creator $finance -OwnerIds $owners -Policy $policy -Confirm:$false } | Should -Throw '*Conflict*'
    }
}

Describe 'Inventory (mocked Graph)' {
    BeforeAll {
        $script:teams = Get-Content "$fx/teams.json" -Raw | ConvertFrom-Json
        $script:members = Get-Content "$fx/members.json" -Raw | ConvertFrom-Json
        Mock Invoke-MgGraphRequest -ModuleName TeamsGovernance -ParameterFilter { $Uri -eq '/v1.0/teams?$select=id,displayName,visibility' } { $teams.page1 }
        Mock Invoke-MgGraphRequest -ModuleName TeamsGovernance -ParameterFilter { $Uri -like '*skiptoken=page2' } { $teams.page2 }
        Mock Invoke-MgGraphRequest -ModuleName TeamsGovernance -ParameterFilter { $Uri -like '/v1.0/teams/*/members' } {
            $id = ($Uri -split '/')[3]; $members.$id
        }
        Mock Invoke-MgGraphRequest -ModuleName TeamsGovernance -ParameterFilter { $Uri -like '*getTeamsTeamActivityDetail*' } {
            Copy-Item "$fx/team-activity.csv" $OutputFilePath
        }
        $script:inv = @(Get-TeamsInventory -Period D180)
    }
    It 'reads every page of teams' { $inv.DisplayName | Should -Be @('TEAM_Finance_Budget 2027', 'TEAM_Sales_Partner Portal', 'Old Offsite 2024') }
    It 'counts owners and guests from conversationMember roles' {
        $sales = $inv | Where-Object DisplayName -eq 'TEAM_Sales_Partner Portal'
        $sales.Owners | Should -Be 2; $sales.Guests | Should -Be 1; $sales.Members | Should -Be 4
        ($inv | Where-Object DisplayName -eq 'Old Offsite 2024').Owners | Should -Be 0
    }
    It 'joins last activity from the usage report' {
        ($inv | Where-Object DisplayName -eq 'TEAM_Finance_Budget 2027').DaysInactive | Should -Be 3
        $old = $inv | Where-Object DisplayName -eq 'Old Offsite 2024'
        $old.ActivityKnown | Should -BeTrue; $old.LastActivity | Should -BeNullOrEmpty
    }
}

Describe 'Governance findings' {
    BeforeAll {
        $script:inv = @(Get-Content "$fx/inventory.json" -Raw | ConvertFrom-Json)
        $script:f = @(Get-TeamsGovernanceFinding -Inventory $inv -Policy $policy)
    }
    It 'flags <Rule> on <Team>' -ForEach @(
        @{ Team = 'Old Offsite 2024'; Rule = 'Ownerless' }
        @{ Team = 'Project Falcon'; Rule = 'TooFewOwners' }
        @{ Team = 'TEAM_Sales_Partner Portal'; Rule = 'GuestsInPublicTeam' }
        @{ Team = 'Project Falcon'; Rule = 'NamingConvention' }
        @{ Team = 'TEAM_Marketing_Launch Q3'; Rule = 'Inactive' }
        @{ Team = 'Old Offsite 2024'; Rule = 'Inactive' }
    ) { ($f | Where-Object { $_.Team -eq $Team -and $_.Rule -eq $Rule }) | Should -Not -BeNullOrEmpty }
    It 'leaves compliant teams alone' {
        $f.Team | Should -Not -Contain 'TEAM_Finance_Budget 2027'
        $f.Team | Should -Not -Contain 'TEAM_IT_Service Desk'
    }
    It 'does not call every team inactive when the activity join fails (concealed report)' {
        $copy = $inv | ConvertTo-Json -Depth 4 | ConvertFrom-Json
        foreach ($t in $copy) { $t.ActivityKnown = $false }
        $c = @(Get-TeamsGovernanceFinding -Inventory $copy -Policy $policy)
        $c.Rule | Should -Contain 'ActivityUnavailable'
        $c.Rule | Should -Not -Contain 'Inactive'
    }
}

Describe 'Tenant directory policy' {
    BeforeAll { $script:gs = Get-Content "$fx/groupsettings.json" -Raw | ConvertFrom-Json }
    It 'maps the policy file to Group.Unified values' {
        $v = Get-TeamsDirectoryPolicyValue -Policy $policy
        $v.PrefixSuffixNamingRequirement | Should -Be 'TEAM_[Department]_[GroupName]'
        $v.CustomBlockedWordsList | Should -Be 'Payroll,CEO,HR,Confidential'
        $v.EnableGroupCreation | Should -Be 'false'
        $v.GroupCreationAllowedGroupId | Should -Be '00000000-0000-0000-0000-000000000900'
    }
    It 'merges into existing values without dropping the others' {
        $m = Merge-GroupSettingValue -Current $gs.existing.value[0].values -Desired (Get-TeamsDirectoryPolicyValue -Policy $policy)
        ($m | Where-Object name -eq 'AllowToAddGuests').value | Should -Be 'true'
        ($m | Where-Object name -eq 'EnableGroupCreation').value | Should -Be 'false'
        $m.Count | Should -Be 6
    }
    It 'PATCHes the existing setting (and only with -Confirm:$false, never on -WhatIf)' {
        Mock Invoke-MgGraphRequest -ModuleName TeamsGovernance -ParameterFilter { $Method -eq 'GET' } { $gs.existing }
        Mock Invoke-MgGraphRequest -ModuleName TeamsGovernance -ParameterFilter { $Method -ne 'GET' } { $script:write = @{ Method = $Method; Uri = $Uri; Body = $Body } }
        $null = Set-TeamsDirectoryPolicy -Policy $policy -WhatIf
        Should -Invoke Invoke-MgGraphRequest -ModuleName TeamsGovernance -ParameterFilter { $Method -ne 'GET' } -Times 0
        $null = Set-TeamsDirectoryPolicy -Policy $policy -Confirm:$false
        $write.Method | Should -Be 'PATCH'
        $write.Uri | Should -Be '/v1.0/groupSettings/00000000-0000-0000-0000-000000000801'
        (($write.Body | ConvertFrom-Json).values | Where-Object name -eq 'PrefixSuffixNamingRequirement').value | Should -Be 'TEAM_[Department]_[GroupName]'
    }
    It 'creates the setting from template defaults when none exists' {
        Mock Invoke-MgGraphRequest -ModuleName TeamsGovernance -ParameterFilter { $Uri -eq '/v1.0/groupSettings' -and $Method -eq 'GET' } { [pscustomobject]@{ value = @() } }
        Mock Invoke-MgGraphRequest -ModuleName TeamsGovernance -ParameterFilter { $Uri -like '/v1.0/groupSettingTemplates/*' } { $gs.template }
        Mock Invoke-MgGraphRequest -ModuleName TeamsGovernance -ParameterFilter { $Method -eq 'POST' } { $script:posted = $Body | ConvertFrom-Json }
        $null = Set-TeamsDirectoryPolicy -Policy $policy -Confirm:$false
        $posted.templateId | Should -Be '62375ab9-6b52-47ed-826b-58e47e0e304b'
        ($posted.values | Where-Object name -eq 'EnableMSStandardBlockedWords').value | Should -Be 'false'
        ($posted.values | Where-Object name -eq 'GroupCreationAllowedGroupId').value | Should -Be '00000000-0000-0000-0000-000000000900'
    }
}

Describe 'Real Microsoft Graph PowerShell parameters' -Skip:(-not (Get-Module -ListAvailable Microsoft.Graph.Authentication)) {
    It 'Invoke-MgGraphRequest has every parameter and output type the module uses' {
        $cmd = Get-Command Invoke-MgGraphRequest
        foreach ($name in 'Method', 'Uri', 'Body', 'ContentType', 'OutputType', 'OutputFilePath') { $cmd.Parameters.Keys | Should -Contain $name }
        [enum]::GetNames($cmd.Parameters['OutputType'].ParameterType) | Should -Contain 'HttpResponseMessage'
        [enum]::GetNames($cmd.Parameters['Method'].ParameterType) | Should -Contain 'PATCH'
    }
    It 'Get-MgContext exists (used to skip a second sign-in)' { Get-Command Get-MgContext | Should -Not -BeNullOrEmpty }
}
