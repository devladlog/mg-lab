BeforeAll {
    if (-not (Get-Command Invoke-MgGraphRequest -ErrorAction SilentlyContinue)) {
        function global:Invoke-MgGraphRequest { param($Method, $Uri, $Body, $Headers, $OutputType, $ContentType, $ResponseHeadersVariable, $ErrorAction) throw 'stub' }
    }
    Import-Module "$PSScriptRoot/../src/VivaEngage/VivaEngage.psd1" -Force
    $script:cfgPath = "$PSScriptRoot/../src/communities.json"
    $script:config = Get-VivaCommunityConfig -Path $cfgPath
    $script:inventory = Get-Content "$PSScriptRoot/fixtures/inventory.json" -Raw | ConvertFrom-Json
    function script:New-Config([scriptblock]$Change) {
        $c = Get-Content $cfgPath -Raw | ConvertFrom-Json
        & $Change $c
        $p = Join-Path $TestDrive ("cfg-{0}.json" -f [guid]::NewGuid()); $c | ConvertTo-Json -Depth 8 | Set-Content $p; $p
    }
}

Describe 'Config file' {
    It 'loads the sample config' {
        @($config.communities).Count | Should -Be 3
        $config.settings.minOwners | Should -Be 2
    }
    It 'lower-cases user names and removes owners from the member list' {
        $c = Get-VivaCommunityConfig -Path (New-Config { param($c) $c.communities[0].owners[0] = 'ALEX.Demo@contoso.com'; $c.communities[0].members += 'alex.demo@contoso.com' })
        $c.communities[0].owners[0] | Should -Be 'alex.demo@contoso.com'
        $c.communities[0].members | Should -Not -Contain 'alex.demo@contoso.com'
    }
    It 'rejects a display name over 255 characters' {
        { Get-VivaCommunityConfig -Path (New-Config { param($c) $c.communities[0].displayName = 'x' * 256 }) } | Should -Throw '*255*'
    }
    It 'rejects a description over 1024 characters' {
        { Get-VivaCommunityConfig -Path (New-Config { param($c) $c.communities[0].description = 'x' * 1025 }) } | Should -Throw '*1024*'
    }
    It 'rejects a privacy value other than public or private' {
        { Get-VivaCommunityConfig -Path (New-Config { param($c) $c.communities[0].privacy = 'secret' }) } | Should -Throw "*'public' or 'private'*"
    }
    It 'rejects duplicate names, ignoring case' {
        { Get-VivaCommunityConfig -Path (New-Config { param($c) $c.communities[1].displayName = 'PROJECT FALCON - LAUNCH' }) } | Should -Throw '*duplicate displayName*'
    }
    It 'rejects fewer owners than settings.minOwners' {
        { Get-VivaCommunityConfig -Path (New-Config { param($c) $c.communities[0].owners = @('alex.demo@contoso.com') }) } | Should -Throw '*minOwners*'
    }
    It 'rejects more than 100 owners' {
        $p = New-Config { param($c) $c.communities[0].owners = @(1..101 | ForEach-Object { "user$_@contoso.com" }) }
        { Get-VivaCommunityConfig -Path $p } | Should -Throw '*limited to 100*'
    }
    It 'rejects something that is not a user principal name' {
        { Get-VivaCommunityConfig -Path (New-Config { param($c) $c.communities[0].members = @('not-a-upn') }) } | Should -Throw '*not a user principal name*'
    }
    It 'reports every problem at once' {
        $p = New-Config { param($c) $c.communities[0].privacy = 'x'; $c.communities[1].privacy = 'y' }
        { Get-VivaCommunityConfig -Path $p } | Should -Throw '*x*y*'
    }
    It 'defaults privacy to private' {
        $c = Get-VivaCommunityConfig -Path (New-Config { param($c) $c.communities[0].PSObject.Properties.Remove('privacy') })
        $c.communities[0].privacy | Should -Be 'private'
    }
}

Describe 'Request bodies and headers' {
    It 'community body has displayName, description, privacy and nothing else (delegated)' {
        $b = ConvertTo-VivaCommunityBody -Community $config.communities[0]
        @($b.Keys) | Should -Be 'displayName', 'description', 'privacy'
        $b.privacy | Should -Be 'private'
    }
    It 'application permissions need an owner and send owners@odata.bind' {
        { ConvertTo-VivaCommunityBody -Community $config.communities[0] -AsApplication } | Should -Throw '*owner*'
        $b = ConvertTo-VivaCommunityBody -Community $config.communities[0] -AsApplication -OwnerIds 'u-1'
        $b['owners@odata.bind'] | Should -Be 'https://graph.microsoft.com/v1.0/users/u-1'
    }
    It 'group reference body points at the directory object' {
        (ConvertTo-VivaGroupRefBody -UserId 'u-9')['@odata.id'] | Should -Be 'https://graph.microsoft.com/v1.0/directoryObjects/u-9'
    }
    It 'reads Operation-Location, or Location, in any case; the text and the example in Learn disagree' {
        Get-VivaHeaderValue -Headers @{ 'operation-location' = @('https://g/op/1') } -Name 'Operation-Location', 'Location' | Should -Be 'https://g/op/1'
        Get-VivaHeaderValue -Headers @{ Location = 'https://g/op/2' } -Name 'Operation-Location', 'Location' | Should -Be 'https://g/op/2'
        Get-VivaHeaderValue -Headers @{ ETag = 'x' } -Name 'Operation-Location', 'Location' | Should -BeNullOrEmpty
        Get-VivaHeaderValue -Headers $null -Name 'Location' | Should -BeNullOrEmpty
    }
}

Describe 'Diff' {
    BeforeAll { $script:diff = @(Get-VivaCommunityDiff -Config $config -Inventory $inventory) }
    It 'creates the community that is missing' {
        @($diff | Where-Object { $_.Action -eq 'Create' }).Community | Should -Be 'Falcon Customer Stories'
    }
    It 'adds the missing owner, and the owner as member too' {
        $diff | Where-Object { $_.Action -eq 'AddOwner' -and $_.Community -eq 'Project Falcon - Launch' } | ForEach-Object { $_.Detail } | Should -Be 'sam.demo@contoso.com'
        $diff | Where-Object { $_.Action -eq 'AddMember' -and $_.Community -eq 'Project Falcon - Launch' } | ForEach-Object { $_.Detail } | Should -Be 'sam.demo@contoso.com'
    }
    It 'reports privacy drift as an Update, with the field name' {
        $u = @($diff | Where-Object { $_.Action -eq 'Update' })
        $u.Count | Should -Be 1
        $u[0].Field | Should -Be 'privacy'
    }
    It 'lists communities that are not in the config as Unmanaged, and never proposes a delete' {
        @($diff | Where-Object { $_.Action -eq 'Unmanaged' }).Community | Sort-Object | Should -Be 'Falcon Hackathon', 'Lunch Club'
        @($diff.Action | Sort-Object -Unique) | Should -Not -Contain 'Delete'
    }
    It 'matches names ignoring case' {
        $inv = Get-Content "$PSScriptRoot/fixtures/inventory.json" -Raw | ConvertFrom-Json
        $inv.communities[0].displayName = 'PROJECT FALCON - LAUNCH'
        @(Get-VivaCommunityDiff -Config $config -Inventory $inv | Where-Object { $_.Action -eq 'Create' }).Count | Should -Be 1
    }
    It 'says InSync when nothing differs' {
        $inv = [pscustomobject]@{ communities = @(foreach ($c in $config.communities) {
                    [pscustomobject]@{ displayName = $c.displayName; description = $c.description; privacy = $c.privacy; owners = $c.owners; members = @($c.owners + $c.members) } }) }
        @(Get-VivaCommunityDiff -Config $config -Inventory $inv).Action | Sort-Object -Unique | Should -Be 'InSync'
    }
    It 'works against an empty tenant' {
        $rows = @(Get-VivaCommunityDiff -Config $config -Inventory ([pscustomobject]@{ communities = @() }))
        @($rows | Where-Object Action -eq 'Create').Count | Should -Be 3
    }
}

Describe 'Audit findings' {
    BeforeAll { $script:findings = @(Get-VivaFinding -Inventory $inventory -Config $config) }
    It 'finds a community without owner as High' {
        $findings | Where-Object { $_.Rule -eq 'NoOwner' } | ForEach-Object { "$($_.Subject)/$($_.Severity)" } | Should -Be 'Falcon Hackathon/High'
    }
    It 'finds too few owners' {
        $findings | Where-Object { $_.Rule -eq 'FewOwners' } | ForEach-Object { $_.Subject } | Should -Be 'Project Falcon - Launch'
    }
    It 'does not report FewOwners on a community that already has no owner (NoOwner covers it)' {
        @($findings | Where-Object { $_.Rule -eq 'FewOwners' -and $_.Subject -eq 'Falcon Hackathon' }).Count | Should -Be 0
    }
    It 'finds privacy drift' {
        $findings | Where-Object { $_.Rule -eq 'PrivacyDrift' } | ForEach-Object { $_.Subject } | Should -Be 'Contoso Ask Anything'
    }
    It 'finds a community in the config that is not in the tenant' {
        $findings | Where-Object { $_.Rule -eq 'MissingCommunity' } | ForEach-Object { $_.Subject } | Should -Be 'Falcon Customer Stories'
    }
    It 'finds communities where only owners are members' {
        $findings | Where-Object { $_.Rule -eq 'NoMembers' } | ForEach-Object { $_.Subject } | Should -Be 'Lunch Club'
    }
    It 'marks communities outside the config as Info' {
        @($findings | Where-Object { $_.Rule -eq 'NotInConfig' }).Count | Should -Be 2
        @($findings | Where-Object { $_.Rule -eq 'NotInConfig' }).Severity | Sort-Object -Unique | Should -Be 'Info'
    }
    It 'counts Network Administrators against maxNetworkAdmins' {
        $findings | Where-Object { $_.Rule -eq 'TooManyNetworkAdmins' } | ForEach-Object { $_.Detail } | Should -Be '4 Network Administrators, policy allows 3.'
    }
    It 'flags Network Administrators outside the allow list as High' {
        @($findings | Where-Object { $_.Rule -eq 'UnexpectedNetworkAdmin' }).Subject | Sort-Object | Should -Be 'jordan.demo@contoso.com', 'sam.demo@contoso.com'
    }
    It 'does not count Verified Administrators as Network Administrators' {
        @($findings | Where-Object { $_.Subject -eq 'labadmin@contoso.com' }).Count | Should -Be 0
    }
    It 'flags duplicate names' {
        $inv = Get-Content "$PSScriptRoot/fixtures/inventory.json" -Raw | ConvertFrom-Json
        $inv.communities[3].displayName = 'lunch club'; $inv.communities += $inv.communities[3]
        @(Get-VivaFinding -Inventory $inv -Config $config | Where-Object Rule -eq 'DuplicateName').Count | Should -Be 1
    }
    It 'sorts High first' {
        $findings[0].Severity | Should -Be 'High'
        $findings[-1].Severity | Should -Be 'Info'
    }
    It 'returns no findings for a clean tenant' {
        $inv = [pscustomobject]@{ communities = @(foreach ($c in $config.communities) {
                    [pscustomobject]@{ displayName = $c.displayName; description = ''; privacy = $c.privacy; owners = $c.owners; members = @($c.owners + 'someone@contoso.com') } }); roles = @() }
        @(Get-VivaFinding -Inventory $inv -Config $config).Count | Should -Be 0
    }
    It 'writes Markdown with one table row per finding' {
        $md = ConvertTo-VivaMarkdown -Finding $findings -Inventory $inventory
        $md | Should -Match 'High 3 \| Medium 4 \| Low 1 \| Info 2'
        @($md -split "`n" | Where-Object { $_ -match '^\| (High|Medium|Low|Info) \|' }).Count | Should -Be $findings.Count
    }
    It 'writes a report for zero findings' {
        ConvertTo-VivaMarkdown -Finding @() -Inventory ([pscustomobject]@{ communities = @() }) | Should -Match 'No findings'
    }
}

Describe 'Graph calls (mocked)' {
    BeforeEach {
        $script:calls = [System.Collections.Generic.List[object]]::new()
        Mock -ModuleName VivaEngage Start-VVSleep { $script:sleeps += $Seconds }
        $script:sleeps = @()
    }

    Context 'Invoke-VivaRequest and 429' {
        It 'waits for Retry-After on 429 and tries again' {
            $script:n = 0
            Mock -ModuleName VivaEngage Invoke-MgGraphRequest { $script:n++; if ($script:n -lt 3) { throw 'Response status code does not indicate success: 429 (TooManyRequests).' }; [pscustomobject]@{ ok = $true } }
            (Invoke-VivaRequest -Method GET -Uri '/v1.0/x').ok | Should -BeTrue
            $script:n | Should -Be 3
            $script:sleeps | Should -Be 30, 30
        }
        It 'uses the Retry-After value of the response when there is one' {
            $script:n = 0
            Mock -ModuleName VivaEngage Invoke-MgGraphRequest {
                $script:n++
                if ($script:n -eq 1) {
                    $resp = [System.Net.Http.HttpResponseMessage]::new(429)
                    $resp.Headers.RetryAfter = [System.Net.Http.Headers.RetryConditionHeaderValue]::new([timespan]::FromSeconds(45))
                    $ex = [System.Net.Http.HttpRequestException]::new('Too many requests')
                    $ex | Add-Member -NotePropertyName Response -NotePropertyValue $resp
                    throw $ex
                }
                [pscustomobject]@{ ok = $true }
            }
            (Invoke-VivaRequest -Method GET -Uri '/v1.0/x').ok | Should -BeTrue
            $script:sleeps | Should -Be 45
        }
        It 'gives up after MaxRetries' {
            Mock -ModuleName VivaEngage Invoke-MgGraphRequest { throw '429 TooManyRequests' }
            { Invoke-VivaRequest -Method GET -Uri '/v1.0/x' -MaxRetries 2 } | Should -Throw '*429*'
            Should -Invoke -ModuleName VivaEngage Invoke-MgGraphRequest -Times 3 -Exactly
        }
        It 'does not retry other errors' {
            Mock -ModuleName VivaEngage Invoke-MgGraphRequest { throw '403 Forbidden' }
            { Invoke-VivaRequest -Method GET -Uri '/v1.0/x' } | Should -Throw '*403*'
            Should -Invoke -ModuleName VivaEngage Invoke-MgGraphRequest -Times 1 -Exactly
        }
    }

    Context 'Wait-VivaOperation' {
        It 'polls more than 30 seconds apart until succeeded' {
            $script:n = 0
            Mock -ModuleName VivaEngage Invoke-MgGraphRequest { $script:n++; [pscustomobject]@{ status = $(if ($script:n -lt 3) { 'running' } else { 'succeeded' }); resourceId = 'c-9' } }
            (Wait-VivaOperation -OperationUri 'https://g/op/1').resourceId | Should -Be 'c-9'
            $script:sleeps | Should -Be 31, 31
        }
        It 'refuses an interval of 30 seconds or less' {
            { Wait-VivaOperation -OperationUri 'https://g/op/1' -IntervalSeconds 30 } | Should -Throw
        }
        It 'throws the statusDetail when the operation failed' {
            Mock -ModuleName VivaEngage Invoke-MgGraphRequest { [pscustomobject]@{ status = 'failed'; statusDetail = 'Name already in use' } }
            { Wait-VivaOperation -OperationUri 'https://g/op/1' } | Should -Throw '*Name already in use*'
        }
        It 'stops after MaxChecks' {
            Mock -ModuleName VivaEngage Invoke-MgGraphRequest { [pscustomobject]@{ status = 'running' } }
            { Wait-VivaOperation -OperationUri 'https://g/op/1' -MaxChecks 3 } | Should -Throw '*3 checks*'
        }
    }

    Context 'Set-VivaCommunity against a fake tenant' {
        BeforeEach {
            # fake tenant: Project Falcon exists with one owner, everything else is missing. The signed-in user (alex.demo) becomes owner of what is created.
            $script:created = @(); $script:refs = @(); $script:patches = @()
            # one level above Invoke-MgGraphRequest: a Pester mock cannot fill -ResponseHeadersVariable in the caller's scope
            Mock -ModuleName VivaEngage Invoke-VivaRequest {
                param($Method, $Uri, $Body, $Headers, $WithHeaders, $MaxRetries)
                $u = [uri]::UnescapeDataString($Uri)
                if ($Method -eq 'POST' -and $u -like '*/employeeExperience/communities') {
                    $script:created += $Body.displayName
                    return [pscustomobject]@{ Body = $null; Headers = @{ 'Operation-Location' = @("https://graph.microsoft.com/v1.0/employeeExperience/engagementAsyncOperations/op-$($script:created.Count)") } }
                }
                if ($Method -eq 'GET' -and $u -match 'engagementAsyncOperations/op-(\d)$') { return [pscustomobject]@{ status = 'succeeded'; resourceId = "c-new$($Matches[1])" } }
                if ($Method -eq 'GET' -and $u -match 'communities/c-new(\d)\?') { $n = [int]$Matches[1]; return [pscustomobject]@{ id = "c-new$n"; displayName = $script:created[$n - 1]; privacy = 'public'; groupId = "g-new$n" } }
                if ($Method -eq 'GET' -and $u -match 'employeeExperience/communities\?') {
                    return [pscustomobject]@{ value = @([pscustomobject]@{ id = 'c-1'; displayName = 'Project Falcon - Launch'; description = 'Everything about the Falcon launch: dates, decisions, customer questions.'; privacy = 'private'; groupId = 'g-1' }) }
                }
                if ($Method -eq 'GET' -and $u -like '*groups/g-1/owners*') { return [pscustomobject]@{ value = @([pscustomobject]@{ id = 'u-alex'; userPrincipalName = 'alex.demo@contoso.com' }) } }
                if ($Method -eq 'GET' -and $u -like '*groups/g-1/members*') { return [pscustomobject]@{ value = @([pscustomobject]@{ id = 'u-alex'; userPrincipalName = 'alex.demo@contoso.com' }) } }
                if ($Method -eq 'GET' -and $u -like '*groups/g-new*') { return [pscustomobject]@{ value = @([pscustomobject]@{ id = 'u-alex'; userPrincipalName = 'Alex.Demo@contoso.com' }) } }
                if ($Method -eq 'GET' -and $u -like '*/users/*') { return [pscustomobject]@{ id = 'id-of-' + ($u -replace '^.*/users/([^?]+).*$', '$1') } }
                if ($Method -eq 'POST' -and $u -like '*/groups/*/$ref') { $script:refs += "$($u -replace '^.*/groups/','')|$($Body['@odata.id'] -replace '^.*/','')"; return $null }
                if ($Method -eq 'PATCH') { $script:patches += "$u|$($Body | ConvertTo-Json -Compress)"; return $null }
                throw "unexpected call $Method $u"
            }
        }
        It 'creates the missing communities, follows the operation, and adds owners and members through the group' {
            $r = @(Set-VivaCommunity -Config $config)
            $script:created | Should -Be 'Contoso Ask Anything', 'Falcon Customer Stories'
            ($r | Where-Object Step -eq 'CreateCommunity').Count | Should -Be 2
            $script:refs | Should -Contain 'g-1/owners/$ref|id-of-sam.demo@contoso.com'
            $script:refs | Should -Contain 'g-1/members/$ref|id-of-jordan.demo@contoso.com'
            $script:refs | Should -Contain 'g-new2/owners/$ref|id-of-taylor.demo@contoso.com'
        }
        It 'does not add the creator again as owner (the creator is owner of a new community)' {
            $r = @(Set-VivaCommunity -Config $config)
            $script:refs | Should -Not -Contain 'g-new1/owners/$ref|id-of-alex.demo@contoso.com'
            ($r | Where-Object { $_.Step -eq 'AddOwner' -and $_.Target -like '*alex.demo*' -and $_.Result -like 'Already there*' }).Count | Should -Be 1
        }
        It 'sends nothing with -WhatIf, and still lists every step' {
            $r = @(Set-VivaCommunity -Config $config -WhatIf)
            $script:created.Count | Should -Be 0
            $script:refs.Count | Should -Be 0
            ($r | Where-Object Step -eq 'CreateCommunity').Count | Should -Be 2
            ($r | Where-Object Result -like 'WhatIf*').Count | Should -Be $r.Count
        }
        It 'reports drift but does not patch without -FixDrift' {
            $cfg = Get-VivaCommunityConfig -Path (New-Config { param($c) $c.communities[0].description = 'A new description' })
            $r = @(Set-VivaCommunity -Config $cfg -WhatIf:$false)
            $script:patches.Count | Should -Be 0
            ($r | Where-Object Step -eq 'Drift:description').Result | Should -Match 'report only'
        }
        It 'patches description with -FixDrift' {
            $cfg = Get-VivaCommunityConfig -Path (New-Config { param($c) $c.communities[0].description = 'A new description' })
            $null = Set-VivaCommunity -Config $cfg -FixDrift
            $script:patches | Should -Contain '/v1.0/employeeExperience/communities/c-1|{"description":"A new description"}'
        }
        It 'makes no DELETE call, ever' {
            $null = Set-VivaCommunity -Config $config -FixDrift
            Should -Invoke -ModuleName VivaEngage Invoke-VivaRequest -Times 0 -Exactly -ParameterFilter { $Method -eq 'DELETE' }
        }
    }

    Context 'Get-VivaInventory' {
        It 'reads communities with owners/members and the role members; an empty role is not an item' {
            Mock -ModuleName VivaEngage Invoke-MgGraphRequest {
                param($Method, $Uri, $Body, $Headers, $OutputType, $ContentType, $ResponseHeadersVariable, $ErrorAction)
                $u = [uri]::UnescapeDataString($Uri)
                if ($u -match 'employeeExperience/communities\?') { return [pscustomobject]@{ value = @([pscustomobject]@{ id = 'c-1'; displayName = 'A'; privacy = 'public'; groupId = 'g-1' }) } }
                if ($u -like '*groups/g-1/owners*') { return [pscustomobject]@{ value = @([pscustomobject]@{ userPrincipalName = 'A@contoso.com' }) } }
                if ($u -like '*groups/g-1/members*') { return [pscustomobject]@{ value = @() } }
                if ($u -match 'employeeExperience/roles\?') { return [pscustomobject]@{ value = @([pscustomobject]@{ id = 'r-1'; displayName = 'Network Administrator' }, [pscustomobject]@{ id = 'r-2'; displayName = 'Verified Administrator' }) } }
                if ($u -like '*roles/r-1/members*') { return [pscustomobject]@{ value = @([pscustomobject]@{ userId = 'u-1' }) } }
                if ($u -like '*roles/r-2/members*') { return [pscustomobject]@{ value = @() } }
                if ($u -like '*/users/u-1*') { return [pscustomobject]@{ id = 'u-1'; userPrincipalName = 'Boss@contoso.com' } }
                throw "unexpected $u"
            }
            $inv = Get-VivaInventory
            @($inv.communities).Count | Should -Be 1
            $inv.communities[0].owners | Should -Be 'a@contoso.com'
            @($inv.communities[0].members).Count | Should -Be 0
            @($inv.roles).Count | Should -Be 2
            $inv.roles[0].members[0].upn | Should -Be 'boss@contoso.com'
            @($inv.roles[1].members).Count | Should -Be 0
        }
    }
}

Describe 'Calls checked against the real Microsoft Graph PowerShell SDK' -Skip:(-not (Get-Module -ListAvailable Microsoft.Graph.Authentication)) {
    It 'Invoke-MgGraphRequest has the -ResponseHeadersVariable and -OutputType parameters we use' {
        $p = (Get-Command Invoke-MgGraphRequest -Module Microsoft.Graph.Authentication).Parameters.Keys
        $p | Should -Contain 'ResponseHeadersVariable'
        $p | Should -Contain 'OutputType'
        $p | Should -Contain 'ContentType'
    }
    It 'every parameter splatted by Invoke-VivaRequest exists on Invoke-MgGraphRequest' {
        $p = (Get-Command Invoke-MgGraphRequest -Module Microsoft.Graph.Authentication).Parameters.Keys
        foreach ($n in 'Method', 'Uri', 'Body', 'Headers', 'ContentType', 'OutputType', 'ResponseHeadersVariable', 'ErrorAction') { $p | Should -Contain $n }
    }
}
