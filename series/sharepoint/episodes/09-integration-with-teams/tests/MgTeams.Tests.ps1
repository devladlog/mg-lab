#Requires -Modules @{ ModuleName = 'Pester'; ModuleVersion = '5.5.0' }
# Invoke-Pester ./tests -Output Detailed
# The tenant tests mock the real PnP.PowerShell cmdlets (Pester copies their parameter metadata, so a wrong
# parameter name or type fails the test). They are skipped when PnP.PowerShell isn't installed.

BeforeDiscovery {
    $script:hasPnP = [bool](Get-Module -ListAvailable PnP.PowerShell)
}

BeforeAll {
    $script:src = Join-Path $PSScriptRoot '..' 'src'
    Import-Module (Join-Path $src 'MgTeams.psm1') -Force
    $script:plan = Import-MgJson -Path (Join-Path $src 'teams' 'purchasing.team.json')
    $script:bad = Import-MgJson -Path (Join-Path $src 'bad' 'bad.team.json')
    $script:tenant = 'https://contoso.sharepoint.com'
    $script:gid = '00000000-0000-0000-0000-0000000000a1'
    $script:teamSite = "$tenant/sites/contoso-purchasing-team"

    function Chan-Id([string]$Name) { "19:$($Name -replace ' ', '')@thread.tacv2" }   # real ids look like this; PnP treats other strings as names
    function Rules($f) { @($f | Where-Object { $null -ne $_ } | ForEach-Object Rule) }
    function Copy-Json($o) { $o | ConvertTo-Json -Depth 30 | ConvertFrom-Json -Depth 30 }
    function Good-State {
        # What the tenant looks like after a successful -Provision, shaped like what Get-MgTeamState returns.
        $channels = @([pscustomobject]@{ Id = (Chan-Id 'General'); Name = 'General'; Type = 'standard'; FilesWebUrl = "$teamSite/Shared%20Documents/General"; Tabs = @([pscustomobject]@{ Name = 'How to buy'; Url = "$tenant/sites/Purchasing/SitePages/how-to-buy.aspx" }); Members = @() })
        foreach ($c in $plan.channels) {
            $type = $c.type.ToLower()
            $url = if ($type -eq 'standard') { "$teamSite/Shared%20Documents/$($c.name -replace ' ', '%20')" } else { "$tenant/sites/contoso-purchasing-team-$($c.name -replace ' ', '')/Shared%20Documents" }
            $members = @(@(if ($c.PSObject.Properties['owner']) { $c.owner }) + @(if ($c.PSObject.Properties['members']) { $c.members }) | ForEach-Object { [pscustomobject]@{ Email = "$_@contoso.com"; Roles = @() } })
            $tabs = @($plan.tabs | Where-Object channel -eq $c.name | ForEach-Object { [pscustomobject]@{ Name = $_.name; Url = "$tenant$($_.url)" } })
            $channels += [pscustomobject]@{ Id = (Chan-Id $c.name); Name = $c.name; Type = $type; FilesWebUrl = $url; Tabs = $tabs; Members = $(if ($type -eq 'standard') { @() } else { $members }) }
        }
        [pscustomobject]@{
            Team = [pscustomobject]@{ DisplayName = $plan.team.displayName; GroupId = $gid }
            Channels = $channels
            TeamSite = [pscustomobject]@{ Url = '/sites/contoso-purchasing-team'; HubSiteId = '00000000-0000-0000-0000-0000000000b1' }
            Hub = [pscustomobject]@{ Id = '00000000-0000-0000-0000-0000000000b1' }
        }
    }
}

Describe 'Helpers' {
    It 'appends the domain to a user name, but not to an address' {
        ConvertTo-MgUpn -Name 'alex.demo' -Suffix 'contoso.com' | Should -Be 'alex.demo@contoso.com'
        ConvertTo-MgUpn -Name 'alex.demo' -Suffix '@contoso.com' | Should -Be 'alex.demo@contoso.com'
        ConvertTo-MgUpn -Name 'alex.demo@fabrikam.com' -Suffix 'contoso.com' | Should -Be 'alex.demo@fabrikam.com'
    }

    It 'finds the site collection of a URL, escaped or not, and of a channel site' {
        Get-MgSiteKey 'https://contoso.sharepoint.com/sites/Contoso-Team/Shared%20Documents/General' | Should -Be '/sites/contoso-team'
        Get-MgSiteKey 'https://contoso.sharepoint.com/teams/Old/Shared Documents' | Should -Be '/teams/old'
        Get-MgSiteKey 'https://contoso.sharepoint.com/' | Should -Be ''
    }
}

Describe 'Channel names (Learn: Limits and specifications for Teams)' {
    It 'accepts ordinary names, including spaces and an accent' {
        foreach ($n in 'Supplier Reviews', 'Compras 2026', 'Negociação') { @(Test-MgChannelName $n) | Should -HaveCount 0 -Because $n }
        @(Test-MgChannelName ('x' * 50)) | Should -HaveCount 0
    }

    It 'rejects the characters, the words, the edges and the length Learn lists' {
        @(Test-MgChannelName ('x' * 51)) | Should -Match '51 characters'
        foreach ($n in 'a/b', 'a#b', 'a:b', 'a?b', "it's", 'a"b', 'a..b') { @(Test-MgChannelName $n).Count | Should -BeGreaterThan 0 -Because $n }
        foreach ($n in 'CON', 'com3', 'Forms', 'desktop.ini') { @(Test-MgChannelName $n) | Should -Match 'reserved word' -Because $n }
        @(Test-MgChannelName '_hidden') | Should -Match 'starts with'
        @(Test-MgChannelName 'ends.') | Should -Match 'ends with'
        @(Test-MgChannelName 'a_vti_b') | Should -Match '_vti_'
        @(Test-MgChannelName '') | Should -Match 'empty'
    }
}

Describe 'Test-MgTeamPlan' {
    It 'the Purchasing team plan is clean' {
        @(Test-MgTeamPlan -Plan $plan) | Should -HaveCount 0
    }

    It 'finds every mistake in the bad plan: 16 errors, 2 warnings' {
        $f = @(Test-MgTeamPlan -Plan $bad)
        @($f | Where-Object Severity -eq 'Error') | Should -HaveCount 16
        @($f | Where-Object Severity -eq 'Warning') | Should -HaveCount 2
        (Rules $f | Sort-Object -Unique) -join ',' | Should -Be 'TP002,TP003,TP004,TP005,TP006,TP007,TP008,TP010,TP011,TP012,TP013'
    }

    It 'TP001 no display name and no owner; more than 100 owners' {
        $p = Copy-Json $plan; $p.team.displayName = ''; $p.team.owners = @()
        Rules (Test-MgTeamPlan -Plan $p) | Where-Object { $_ -eq 'TP001' } | Should -Be @('TP001', 'TP001')
        $p.team.displayName = 'x'; $p.team.owners = @(1..101 | ForEach-Object { "user$_" })
        Rules (Test-MgTeamPlan -Plan $p) | Where-Object { $_ -eq 'TP001' } | Should -Be @('TP001')
    }

    It 'TP009 more than 1,000 channels, counting General' {
        $p = Copy-Json $plan; $p.tabs = @()
        $p.channels = @(1..1000 | ForEach-Object { [pscustomobject]@{ name = "Channel $_"; type = 'Standard' } })
        Rules (Test-MgTeamPlan -Plan $p) | Should -Be @('TP009')
        $p.channels = @(1..999 | ForEach-Object { [pscustomobject]@{ name = "Channel $_"; type = 'Standard' } })
        @(Test-MgTeamPlan -Plan $p) | Should -HaveCount 0
    }

    It 'TP008 applies to private channels only: a shared channel can have people outside the team' {
        $p = Copy-Json $plan
        $p.channels[2].members = @('someone.else')
        @(Test-MgTeamPlan -Plan $p) | Should -HaveCount 0
        $p.channels[1].members = @('someone.else')
        Rules (Test-MgTeamPlan -Plan $p) | Should -Be @('TP008')
    }

    It 'TP010 Stream, Planner and Forms tabs are refused in private and shared channels, fine in standard ones' {
        $p = Copy-Json $plan
        $p.tabs = @(
            [pscustomobject]@{ channel = 'Supplier Reviews'; name = 'Plan'; type = 'Planner'; url = '/sites/Purchasing' }
            [pscustomobject]@{ channel = 'Contract Negotiation'; name = 'Form'; type = 'MicrosoftForms'; url = '/sites/Purchasing' }
            [pscustomobject]@{ channel = 'Contract Negotiation'; name = 'Page'; type = 'WebSite'; url = 'https://contoso.com' }
        )
        Rules (Test-MgTeamPlan -Plan $p) | Should -Be @('TP010')
    }
}

Describe 'Get-MgChannelStorage' {
    It 'standard channels are folders of the team site; private and shared channels get a site each' {
        $rows = @(Get-MgChannelStorage -Plan $plan)
        $rows | Should -HaveCount 4
        ($rows | Where-Object Type -eq 'Standard').Site | Should -Be @('team site', 'team site')
        @($rows | Select-Object -ExpandProperty Site -Unique) | Should -HaveCount 3
        ($rows | Where-Object Channel -eq 'Contract Negotiation').Files | Should -Be 'a channel site of its own'
    }
}

Describe 'Test-MgTeamLive' {
    It 'a tenant that matches the plan has no findings' {
        @(Test-MgTeamLive -Plan $plan -State (Good-State)) | Should -HaveCount 0
    }

    It 'TL001 no team' {
        $s = Good-State; $s.Team = $null
        Rules (Test-MgTeamLive -Plan $plan -State $s) | Should -Be @('TL001')
    }

    It 'TL002 a missing channel; TL003 a channel of another type (types cannot be converted)' {
        $s = Good-State
        $s.Channels = @($s.Channels | Where-Object Name -ne 'Supplier Reviews')
        ($s.Channels | Where-Object Name -eq 'Contract Negotiation').Type = 'standard'
        $f = @(Test-MgTeamLive -Plan $plan -State $s)
        Rules $f | Should -Be @('TL002', 'TL003', 'TL006')
        ($f | Where-Object Rule -eq 'TL003').Message | Should -BeLike "*can't be changed*"
    }

    It 'TL004 a person missing from a private channel' {
        $s = Good-State
        ($s.Channels | Where-Object Name -eq 'Contract Negotiation').Members = @([pscustomobject]@{ Email = 'JORDAN.demo@contoso.com'; Roles = @('owner') })
        $f = @(Test-MgTeamLive -Plan $plan -State $s)
        Rules $f | Should -Be @('TL004')
        $f[0].Message | Should -BeLike 'alex.demo*'
    }

    It 'TL005 a missing tab and a tab that points somewhere else' {
        $s = Good-State
        ($s.Channels | Where-Object Name -eq 'General').Tabs = @()
        ($s.Channels | Where-Object Name -eq 'Supplier Reviews').Tabs[0].Url = "$tenant/sites/Elsewhere/SitePages/Home.aspx"
        Rules (Test-MgTeamLive -Plan $plan -State $s) | Should -Be @('TL005', 'TL005')
    }

    It 'TL006 a private channel whose files folder is on the team site, and a standard one that is not' {
        $s = Good-State
        ($s.Channels | Where-Object Name -eq 'Contract Negotiation').FilesWebUrl = "$teamSite/Shared%20Documents/Contract%20Negotiation"
        ($s.Channels | Where-Object Name -eq 'Supplier Reviews').FilesWebUrl = "$tenant/sites/other/Shared%20Documents/x"
        $f = @(Test-MgTeamLive -Plan $plan -State $s)
        Rules $f | Should -Be @('TL006', 'TL006')
        $f.Severity | Should -Not -Contain 'Error'
    }

    It 'TL007 a team site outside the hub, or in another hub' {
        $s = Good-State; $s.TeamSite.HubSiteId = ''
        Rules (Test-MgTeamLive -Plan $plan -State $s) | Should -Be @('TL007')
        $s.TeamSite.HubSiteId = '00000000-0000-0000-0000-0000000000c9'
        (Test-MgTeamLive -Plan $plan -State $s)[0].Message | Should -BeLike '*another hub*'
    }
}

Describe 'Tenant functions (PnP cmdlets mocked)' -Skip:(-not $hasPnP) {
    BeforeAll {
        Import-Module PnP.PowerShell -ErrorAction Stop
        $script:hubId = '00000000-0000-0000-0000-0000000000b1'
        function Mock-Empty-Tenant {
            Mock -ModuleName MgTeams Get-PnPTeamsTeam { @() }
            Mock -ModuleName MgTeams New-PnPTeamsTeam { [pscustomobject]@{ GroupId = $gid; DisplayName = 'Contoso Purchasing Team' } }
            Mock -ModuleName MgTeams Get-PnPTeamsChannel { [pscustomobject]@{ Id = '19:general@thread.tacv2'; DisplayName = 'General'; MembershipType = 'standard' } }
            Mock -ModuleName MgTeams Add-PnPTeamsChannel { [pscustomobject]@{ Id = (Chan-Id $DisplayName); DisplayName = $DisplayName } }
            Mock -ModuleName MgTeams Get-PnPTeamsChannelUser { @([pscustomobject]@{ Email = 'jordan.demo@contoso.com' }) }
            Mock -ModuleName MgTeams Add-PnPTeamsChannelUser { }
            Mock -ModuleName MgTeams Get-PnPTeamsTab { @() }
            Mock -ModuleName MgTeams Add-PnPTeamsTab { }
            Mock -ModuleName MgTeams Get-PnPTeamsChannelFilesFolder { [pscustomobject]@{ webUrl = "$teamSite/Shared Documents/General" } }
            Mock -ModuleName MgTeams Get-PnPTenantSite { [pscustomobject]@{ HubSiteId = [guid]::Empty } }
            Mock -ModuleName MgTeams Get-PnPHubSite { [pscustomobject]@{ ID = [guid]$hubId } }
            Mock -ModuleName MgTeams Add-PnPHubSiteAssociation { }
        }
    }

    It 'creates the team with owners and members as user principal names' {
        Mock-Empty-Tenant
        $steps = @(Invoke-MgTeam -Plan $plan -UpnSuffix 'contoso.com' -TenantUrl $tenant -WaitSeconds 0)
        $steps[0].Action | Should -Be 'CreateTeam'
        Should -Invoke -ModuleName MgTeams New-PnPTeamsTeam -Times 1 -Exactly -ParameterFilter {
            $DisplayName -eq 'Contoso Purchasing Team' -and "$Visibility" -eq 'Private' -and $MailNickName -eq 'contoso-purchasing-team' -and
            @($Owners) -contains 'labadmin@contoso.com' -and @($Owners).Count -eq 2 -and @($Members).Count -eq 4 -and @($Members) -contains 'alex.demo@contoso.com'
        }
    }

    It 'adds a standard channel plainly, a private and a shared channel with type and owner, then the missing members' {
        Mock-Empty-Tenant
        $steps = @(Invoke-MgTeam -Plan $plan -UpnSuffix 'contoso.com' -TenantUrl $tenant -WaitSeconds 0)
        ($steps.Action -join ',') | Should -Be 'CreateTeam,AddChannel,AddChannel,AddMember,AddChannel,AddMember,AddTab,AddTab,Associate'
        Should -Invoke -ModuleName MgTeams Add-PnPTeamsChannel -Times 1 -Exactly -ParameterFilter { $DisplayName -eq 'Supplier Reviews' -and -not $OwnerUPN -and "$ChannelType" -eq '' }
        Should -Invoke -ModuleName MgTeams Add-PnPTeamsChannel -Times 1 -Exactly -ParameterFilter { $DisplayName -eq 'Contract Negotiation' -and "$ChannelType" -eq 'Private' -and $OwnerUPN -eq 'jordan.demo@contoso.com' }
        Should -Invoke -ModuleName MgTeams Add-PnPTeamsChannel -Times 1 -Exactly -ParameterFilter { $DisplayName -eq 'Facilities Handover' -and "$ChannelType" -eq 'Shared' -and $OwnerUPN -eq 'labadmin@contoso.com' }
        # the owner is already in the channel (mock): only the member is added
        Should -Invoke -ModuleName MgTeams Add-PnPTeamsChannelUser -Times 1 -Exactly -ParameterFilter { $User -eq 'alex.demo@contoso.com' -and $Role -eq 'Member' -and $Channel.Id -eq '19:ContractNegotiation@thread.tacv2' }
        Should -Invoke -ModuleName MgTeams Add-PnPTeamsChannelUser -Times 1 -Exactly -ParameterFilter { $User -eq 'sam.demo@contoso.com' }
    }

    It 'adds a SharePoint page or list tab with its page URL, and joins the team site to the hub' {
        Mock-Empty-Tenant
        $null = Invoke-MgTeam -Plan $plan -UpnSuffix 'contoso.com' -TenantUrl $tenant -WaitSeconds 0
        Should -Invoke -ModuleName MgTeams Add-PnPTeamsTab -Times 1 -Exactly -ParameterFilter {
            $DisplayName -eq 'How to buy' -and $Channel.Id -eq '19:general@thread.tacv2' -and "$Type" -eq 'SharePointPageAndList' -and $WebsiteUrl -eq 'https://contoso.sharepoint.com/sites/Purchasing/SitePages/how-to-buy.aspx'
        }
        Should -Invoke -ModuleName MgTeams Get-PnPTenantSite -Times 1 -Exactly -ParameterFilter { $Identity.Url -eq "$tenant/sites/contoso-purchasing-team" }
        Should -Invoke -ModuleName MgTeams Add-PnPHubSiteAssociation -Times 1 -Exactly -ParameterFilter { $Site.Url -eq "$tenant/sites/contoso-purchasing-team" -and $HubSite.Url -eq "$tenant/sites/Operations" }
    }

    It 'does nothing when the tenant already matches the plan (idempotent)' {
        $s = Good-State
        Mock -ModuleName MgTeams Get-PnPTeamsTeam { $s.Team }
        Mock -ModuleName MgTeams New-PnPTeamsTeam { throw 'should not create the team' }
        Mock -ModuleName MgTeams Get-PnPTeamsChannel {
            if ($Identity) { return [pscustomobject]@{ Id = '19:General@thread.tacv2'; DisplayName = 'General' } }
            $s.Channels | ForEach-Object { [pscustomobject]@{ Id = $_.Id; DisplayName = $_.Name; MembershipType = $_.Type } }
        }
        Mock -ModuleName MgTeams Add-PnPTeamsChannel { throw 'should not add a channel' }
        Mock -ModuleName MgTeams Get-PnPTeamsChannelUser { ($s.Channels | Where-Object Id -eq $Channel.Id).Members }
        Mock -ModuleName MgTeams Add-PnPTeamsChannelUser { throw 'should not add a member' }
        Mock -ModuleName MgTeams Get-PnPTeamsTab { ($s.Channels | Where-Object Id -eq $Channel.Id).Tabs | ForEach-Object { [pscustomobject]@{ DisplayName = $_.Name } } }
        Mock -ModuleName MgTeams Add-PnPTeamsTab { throw 'should not add a tab' }
        Mock -ModuleName MgTeams Get-PnPTeamsChannelFilesFolder { [pscustomobject]@{ webUrl = ($s.Channels | Where-Object Id -eq $Channel.Id).FilesWebUrl } }
        Mock -ModuleName MgTeams Get-PnPTenantSite { [pscustomobject]@{ HubSiteId = [guid]$hubId } }
        Mock -ModuleName MgTeams Get-PnPHubSite { [pscustomobject]@{ ID = [guid]$hubId } }
        Mock -ModuleName MgTeams Add-PnPHubSiteAssociation { throw 'should not associate' }
        @(Invoke-MgTeam -Plan $plan -UpnSuffix 'contoso.com' -TenantUrl $tenant -WaitSeconds 0) | Should -HaveCount 0
    }

    It '-WhatIf reports the steps and calls nothing that writes' {
        Mock-Empty-Tenant
        $steps = @(Invoke-MgTeam -Plan $plan -UpnSuffix 'contoso.com' -TenantUrl $tenant -WhatIf)
        $steps[0].Action | Should -Be 'CreateTeam'
        @($steps | Where-Object Action -eq 'AddChannel') | Should -HaveCount 3
        Should -Invoke -ModuleName MgTeams New-PnPTeamsTeam -Times 0 -Exactly
        Should -Invoke -ModuleName MgTeams Add-PnPTeamsChannel -Times 0 -Exactly
        Should -Invoke -ModuleName MgTeams Add-PnPTeamsTab -Times 0 -Exactly
        Should -Invoke -ModuleName MgTeams Add-PnPHubSiteAssociation -Times 0 -Exactly
    }

    It 'two teams with the same name stop the run' {
        Mock -ModuleName MgTeams Get-PnPTeamsTeam { @([pscustomobject]@{ GroupId = 'a' }, [pscustomobject]@{ GroupId = 'b' }) }
        { Invoke-MgTeam -Plan $plan -UpnSuffix 'contoso.com' -TenantUrl $tenant } | Should -Throw '*2 teams are called*'
    }

    It 'a filter with an apostrophe is escaped' {
        Mock -ModuleName MgTeams Get-PnPTeamsTeam { @() }
        $p = Copy-Json $plan; $p.team.displayName = "Contoso's Team"
        $null = Get-MgTeamState -Plan $p -TenantUrl $tenant
        Should -Invoke -ModuleName MgTeams Get-PnPTeamsTeam -Times 1 -Exactly -ParameterFilter { $Filter -eq "displayName eq 'Contoso''s Team'" }
    }

    It 'Get-MgTeamState + Test-MgTeamLive: the read-back of a matching tenant has no findings' {
        $s = Good-State
        Mock -ModuleName MgTeams Get-PnPTeamsTeam { $s.Team }
        Mock -ModuleName MgTeams Get-PnPTeamsChannel { $s.Channels | ForEach-Object { [pscustomobject]@{ Id = $_.Id; DisplayName = $_.Name; MembershipType = $_.Type } } }
        Mock -ModuleName MgTeams Get-PnPTeamsChannelFilesFolder { [pscustomobject]@{ webUrl = ($s.Channels | Where-Object Id -eq $Channel.Id).FilesWebUrl } }
        Mock -ModuleName MgTeams Get-PnPTeamsTab {
            ($s.Channels | Where-Object Id -eq $Channel.Id).Tabs | ForEach-Object {
                [pscustomobject]@{ DisplayName = $_.Name; Configuration = [pscustomobject]@{ WebsiteUrl = $_.Url; ContentUrl = 'https://x/_layouts/15/teamslogon.aspx' } }
            }
        }
        Mock -ModuleName MgTeams Get-PnPTeamsChannelUser { ($s.Channels | Where-Object Id -eq $Channel.Id).Members }
        Mock -ModuleName MgTeams Get-PnPTenantSite { [pscustomobject]@{ HubSiteId = [guid]$hubId } }
        Mock -ModuleName MgTeams Get-PnPHubSite { [pscustomobject]@{ ID = [guid]$hubId } }
        $state = Get-MgTeamState -Plan $plan -TenantUrl $tenant
        Should -Invoke -ModuleName MgTeams Get-PnPTeamsChannelUser -Times 2 -Exactly      # private and shared only
        $state.TeamSite.Url | Should -Be '/sites/contoso-purchasing-team'
        @(Test-MgTeamLive -Plan $plan -State $state) | Should -HaveCount 0
    }

    It 'a channel whose files folder cannot be read yet is reported as having no folder, not as a crash' {
        $s = Good-State
        Mock -ModuleName MgTeams Get-PnPTeamsTeam { $s.Team }
        Mock -ModuleName MgTeams Get-PnPTeamsChannel { [pscustomobject]@{ Id = '19:General@thread.tacv2'; DisplayName = 'General'; MembershipType = 'standard' } }
        Mock -ModuleName MgTeams Get-PnPTeamsChannelFilesFolder { throw 'Graph 404' }
        Mock -ModuleName MgTeams Get-PnPTeamsTab { @() }
        $state = Get-MgTeamState -Plan $plan -TenantUrl $tenant
        $state.Channels[0].FilesWebUrl | Should -Be ''
        $state.TeamSite | Should -BeNullOrEmpty
    }
}

Describe 'Entry script' {
    It 'parses, and its lint-only mode reports the bad plan and the storage map of the good one' {
        $path = Join-Path $src 'Invoke-TeamsIntegration.ps1'
        $errors = $null; $null = [System.Management.Automation.Language.Parser]::ParseFile($path, [ref]$null, [ref]$errors)
        $errors | Should -HaveCount 0
        $out = & pwsh -NoProfile -Command "& '$path' -PlanPath '$(Join-Path $src 'bad' 'bad.team.json')' *>&1 | Out-String"
        ($out -join "`n") | Should -Match '16 error\(s\), 2 warning\(s\)'
        $out = & pwsh -NoProfile -Command "& '$path' -PlanPath '$(Join-Path $src 'teams' 'purchasing.team.json')' *>&1 | Out-String"
        ($out -join "`n") | Should -Match '0 error\(s\), 0 warning\(s\)'
        ($out -join "`n") | Should -Match '3 SharePoint site\(s\)'
    }
}
