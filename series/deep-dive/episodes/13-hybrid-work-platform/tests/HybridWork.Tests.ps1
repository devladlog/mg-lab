BeforeAll {
    $script:Root = Split-Path $PSScriptRoot -Parent
    Import-Module (Join-Path $script:Root 'scripts' 'HybridWork.psm1') -Force
    $script:Contract = Get-HybridContract
}

Describe 'contract' {
    It 'is valid JSON with the sections the code needs' {
        $Contract.meeting.lobbyBypassScope | Should -Be 'organizer'
        $Contract.invite.codeBytes | Should -Be 32
        $Contract.token.scopes | Should -Be @('voip')
    }
    It 'only uses Graph enum values documented on Learn (lobbyBypassScope, allowedPresenters, meetingChatMode)' {
        $Contract.meeting.lobbyBypassScope | Should -BeIn @('organizer', 'organization', 'organizationAndFederated', 'everyone', 'invited', 'organizationExcludingGuests')
        $Contract.meeting.allowedPresenters | Should -BeIn @('everyone', 'organization', 'roleIsPresenter', 'organizer')
        $Contract.meeting.allowMeetingChat | Should -BeIn @('enabled', 'disabled', 'limited')
    }
    It 'keeps the lobby closed to guests by default' {
        $Contract.meeting.lobbyBypassScope | Should -Not -Be 'everyone'
    }
}

Describe 'New-OnlineMeetingBody' {
    It 'builds the Graph body from the contract with UTC timestamps' {
        $b = New-OnlineMeetingBody -Subject 'Partner sync' -Start ([datetime]'2026-12-02T09:00:00Z') -DurationMinutes 30
        $b.subject | Should -Be 'Partner sync'
        $b.startDateTime | Should -Be '2026-12-02T09:00:00Z'
        $b.endDateTime | Should -Be '2026-12-02T09:30:00Z'
        $b.lobbyBypassSettings.scope | Should -Be 'organizer'
        $b.lobbyBypassSettings.isDialInBypassEnabled | Should -BeFalse
        $b.allowedPresenters | Should -Be 'organizer'
        $b.allowMeetingChat | Should -Be 'limited'
    }
    It 'converts a local offset time to UTC' {
        $b = New-OnlineMeetingBody -Start ([datetimeoffset]'2026-12-02T10:00:00+01:00').DateTime.AddHours(0) -DurationMinutes 10
        $b.startDateTime | Should -Match '^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$'
    }
    It 'uses the default subject and duration when none are given' {
        $b = New-OnlineMeetingBody -Start ([datetime]'2026-12-02T09:00:00Z')
        $b.subject | Should -Be $Contract.meeting.defaultSubject
        $b.endDateTime | Should -Be '2026-12-02T09:45:00Z'
    }
    It 'refuses meetings longer than a day' {
        { New-OnlineMeetingBody -DurationMinutes 1441 } | Should -Throw '*1440*'
    }
    It 'serialises to JSON that Graph accepts (nested lobbyBypassSettings, booleans not strings)' {
        $json = New-OnlineMeetingBody -Start ([datetime]'2026-12-02T09:00:00Z') | ConvertTo-Json -Depth 5 -Compress
        $json | Should -Match '"lobbyBypassSettings":\{"scope":"organizer","isDialInBypassEnabled":false\}'
        $json | Should -Match '"isEntryExitAnnounced":true'
    }
}

Describe 'New-HybridMeeting' {
    BeforeAll {
        # Invoke-MgGraphRequest comes from Microsoft.Graph.Authentication, which is not installed here: define a stand-in to mock.
        function global:Invoke-MgGraphRequest { param($Method, $Uri, $Body, $ContentType) }
    }
    AfterAll { Remove-Item function:global:Invoke-MgGraphRequest -ErrorAction SilentlyContinue }

    It 'POSTs to /me/onlineMeetings and returns the join link' {
        Mock -ModuleName HybridWork Invoke-MgGraphRequest {
            # Invoke-MgGraphRequest returns a Hashtable by default, so the mocks do too.
            @{ id = 'MSo0000'; subject = 'Partner sync'; joinWebUrl = 'https://teams.microsoft.com/meet/1234567890123?p=AbCdEfGhIjK'
                startDateTime = '2026-12-02T09:00:00Z'; endDateTime = '2026-12-02T09:45:00Z'; lobbyBypassSettings = @{ scope = 'organizer' } }
        }
        $m = New-HybridMeeting -Subject 'Partner sync' -Start ([datetime]'2026-12-02T09:00:00Z')
        $m.JoinWebUrl | Should -Be 'https://teams.microsoft.com/meet/1234567890123?p=AbCdEfGhIjK'
        $m.LobbyScope | Should -Be 'organizer'
        Should -Invoke -ModuleName HybridWork Invoke-MgGraphRequest -Times 1 -ParameterFilter {
            $Method -eq 'POST' -and $Uri -eq 'https://graph.microsoft.com/v1.0/me/onlineMeetings' -and $Body -like '*"scope":"organizer"*'
        }
    }
    It 'warns when Teams applied a different lobby scope than requested' {
        Mock -ModuleName HybridWork Invoke-MgGraphRequest {
            @{ id = 'x'; joinWebUrl = 'https://teams.microsoft.com/meet/1'; lobbyBypassSettings = @{ scope = 'organization' } }
        }
        $null = New-HybridMeeting -Subject 's' -WarningVariable w -WarningAction SilentlyContinue
        "$w" | Should -BeLike "*requested 'organizer' but Teams applied 'organization'*"
    }
    It 'throws if Graph returns no join link' {
        Mock -ModuleName HybridWork Invoke-MgGraphRequest { @{ id = 'x' } }
        { New-HybridMeeting -Subject 's' } | Should -Throw '*joinWebUrl*'
    }
    It 'sends nothing with -WhatIf' {
        Mock -ModuleName HybridWork Invoke-MgGraphRequest { throw 'must not be called' }
        New-HybridMeeting -Subject 's' -WhatIf | Should -BeNullOrEmpty
        Should -Invoke -ModuleName HybridWork Invoke-MgGraphRequest -Times 0
    }
}

Describe 'New-GuestInvite' {
    BeforeAll { $script:Key = ConvertTo-SecureString 'not-a-real-key' -AsPlainText -Force }

    It 'posts the meeting link with the function key header and returns the invite' {
        Mock -ModuleName HybridWork Invoke-RestMethod {
            [pscustomobject]@{ inviteUrl = 'https://func-hyb-abc.azurewebsites.net/join#i=' + ('A' * 43); expiresOn = '2026-12-02T10:00:00.000Z'; maxUses = 3 }
        }
        $i = New-GuestInvite -ApiBaseUrl 'https://func-hyb-abc.azurewebsites.net' -FunctionKey $Key -MeetingLink 'https://teams.microsoft.com/meet/1?p=x' -ValidMinutes 30 -MaxUses 2
        $i.InviteUrl | Should -Match '/join#i=A{43}$'
        $i.MaxUses | Should -Be 3
        Should -Invoke -ModuleName HybridWork Invoke-RestMethod -Times 1 -ParameterFilter {
            $Uri -eq 'https://func-hyb-abc.azurewebsites.net/api/invites' -and $Headers['x-functions-key'] -eq 'not-a-real-key' -and
            $Body -like '*"validMinutes":30*' -and $Body -like '*"maxUses":2*'
        }
    }
    It 'omits limits that were not given so the server defaults apply' {
        Mock -ModuleName HybridWork Invoke-RestMethod { [pscustomobject]@{ inviteUrl = 'u'; expiresOn = '2026-12-02T10:00:00Z'; maxUses = 3 } }
        $null = New-GuestInvite -ApiBaseUrl 'https://f.azurewebsites.net' -FunctionKey $Key -MeetingLink 'https://teams.microsoft.com/meet/1?p=x'
        Should -Invoke -ModuleName HybridWork Invoke-RestMethod -ParameterFilter { $Body -notlike '*validMinutes*' -and $Body -notlike '*maxUses*' }
    }
    It 'refuses http and out-of-range limits' {
        { New-GuestInvite -ApiBaseUrl 'http://f.azurewebsites.net' -FunctionKey $Key -MeetingLink 'x' } | Should -Throw '*https*'
        { New-GuestInvite -ApiBaseUrl 'https://f.azurewebsites.net' -FunctionKey $Key -MeetingLink 'x' -MaxUses 26 } | Should -Throw
        { New-GuestInvite -ApiBaseUrl 'https://f.azurewebsites.net' -FunctionKey $Key -MeetingLink 'x' -ValidMinutes 481 } | Should -Throw
    }
    It 'never writes the key to the output or the verbose stream' {
        Mock -ModuleName HybridWork Invoke-RestMethod { [pscustomobject]@{ inviteUrl = 'u'; expiresOn = '2026-12-02T10:00:00Z'; maxUses = 1 } }
        $out = New-GuestInvite -ApiBaseUrl 'https://f.azurewebsites.net' -FunctionKey $Key -MeetingLink 'x' -Verbose 4>&1 *>&1 | Out-String
        $out | Should -Not -Match 'not-a-real-key'
    }
    It 'sends nothing with -WhatIf' {
        Mock -ModuleName HybridWork Invoke-RestMethod { throw 'must not be called' }
        New-GuestInvite -ApiBaseUrl 'https://f.azurewebsites.net' -FunctionKey $Key -MeetingLink 'x' -WhatIf | Should -BeNullOrEmpty
    }
}

Describe 'Test-GuestJoinReadiness' {
    It 'passes a tenant where anonymous join is allowed and the lobby is not open to everyone' {
        $r = Test-GuestJoinReadiness -MeetingConfiguration ([pscustomobject]@{ DisableAnonymousJoin = $false }) `
            -MeetingPolicy ([pscustomobject]@{ Identity = 'Global'; AllowAnonymousUsersToJoinMeeting = $true; AutoAdmittedUsers = 'EveryoneInCompany' })
        $r.Count | Should -Be 3
        $r.Where({ -not $_.Passed }).Count | Should -Be 0
    }
    It 'fails when the org-wide switch disables anonymous join' {
        $r = Test-GuestJoinReadiness -MeetingConfiguration ([pscustomobject]@{ DisableAnonymousJoin = $true }) `
            -MeetingPolicy ([pscustomobject]@{ Identity = 'Global'; AllowAnonymousUsersToJoinMeeting = $true; AutoAdmittedUsers = 'EveryoneInCompany' })
        ($r | Where-Object Check -like 'Tenant*').Passed | Should -BeFalse
    }
    It 'fails when the organizer policy forbids anonymous join (the education baseline does this)' {
        $r = Test-GuestJoinReadiness -MeetingConfiguration ([pscustomobject]@{ DisableAnonymousJoin = $false }) `
            -MeetingPolicy ([pscustomobject]@{ Identity = 'Global'; AllowAnonymousUsersToJoinMeeting = $false; AutoAdmittedUsers = 'OrganizerOnly' })
        ($r | Where-Object Check -like '*anonymous join allowed' | Where-Object Check -like 'Organizer*').Passed | Should -BeFalse
    }
    It 'fails when everyone bypasses the lobby' {
        $r = Test-GuestJoinReadiness -MeetingConfiguration ([pscustomobject]@{ DisableAnonymousJoin = $false }) `
            -MeetingPolicy ([pscustomobject]@{ Identity = 'Global'; AllowAnonymousUsersToJoinMeeting = $true; AutoAdmittedUsers = 'Everyone' })
        ($r | Where-Object Check -like '*lobby*').Passed | Should -BeFalse
        ($r | Where-Object Check -like '*lobby*').Detail | Should -BeLike "*'Everyone'*"
    }
}

Describe 'Get-GuestJoinReadiness' {
    It 'explains how to get the Teams module when it is missing' {
        { Get-GuestJoinReadiness } | Should -Throw '*Install-Module MicrosoftTeams*'
    }
    It 'reads both objects and returns the checks when the cmdlets exist' {
        function global:Get-CsTeamsMeetingConfiguration { [pscustomobject]@{ DisableAnonymousJoin = $false } }
        function global:Get-CsTeamsMeetingPolicy { param($Identity) [pscustomobject]@{ Identity = $Identity; AllowAnonymousUsersToJoinMeeting = $true; AutoAdmittedUsers = 'EveryoneInCompany' } }
        try {
            $r = Get-GuestJoinReadiness -PolicyIdentity 'Global'
            $r.Count | Should -Be 3
            $r.Where({ -not $_.Passed }).Count | Should -Be 0
        }
        finally { Remove-Item function:global:Get-CsTeamsMeetingConfiguration, function:global:Get-CsTeamsMeetingPolicy }
    }
}

Describe 'scripts' {
    It 'every script and module parses' {
        foreach ($f in Get-ChildItem (Join-Path $Root 'scripts') -Include *.ps1, *.psm1 -Recurse) {
            $errs = $null
            [void][System.Management.Automation.Language.Parser]::ParseFile($f.FullName, [ref]$null, [ref]$errs)
            $errs | Should -BeNullOrEmpty -Because $f.Name
        }
    }
    It 'contains no hard-coded key, secret or tenant name' {
        $text = Get-ChildItem (Join-Path $Root 'scripts') -Recurse -File | ForEach-Object { Get-Content $_ -Raw } | Out-String
        $text | Should -Not -Match '(?i)accesskey=|connectionstring|devladlog\.(onmicrosoft|sharepoint)'
    }
}
