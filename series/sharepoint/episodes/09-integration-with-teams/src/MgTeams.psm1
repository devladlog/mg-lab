#Requires -Version 7.2
<#
.SYNOPSIS
    Teams and SharePoint together, as code, for Contoso: a team plan (team, channels of three types, tabs, hub) that
    is linted against what Learn documents, provisioned with PnP PowerShell, and read back to show where every
    channel's files really live.

    Pure functions (no tenant needed): Import-MgJson, ConvertTo-MgUpn, Test-MgChannelName, Test-MgTeamPlan,
    Get-MgChannelStorage, Get-MgSiteKey, Test-MgTeamLive.
    Tenant functions (PnP.PowerShell, after Connect-PnPOnline): Invoke-MgTeam, Get-MgTeamState.
#>

Set-StrictMode -Version Latest

# ---- What Learn documents (see README "References") -------------------------------------------------------------
#   Limits and specifications for Teams: 1,000 channels per team (standard + private + shared, deleted ones count for
#   30 days), up to 100 owners per team.
$script:MaxChannelsPerTeam = 1000
$script:MaxTeamOwners = 100
#   Microsoft Graph, create channel: displayName is at most 50 characters.
$script:MaxChannelNameLength = 50
#   Limits and specifications for Teams, "Channel names": characters and words that are not allowed.
$script:BadNameChars = [char[]]'~#%&*{}+/\:<>?|''",'
$script:BadNameWords = @('forms', 'CON', 'CONIN$', 'CONOUT$', 'PRN', 'AUX', 'NUL', 'desktop.ini') + (1..9 | ForEach-Object { "COM$_"; "LPT$_" })
#   Channel types (PnP: TeamsChannelType) and the Graph membershipType they map to.
$script:ChannelTypes = @('Standard', 'Private', 'Shared')
#   Private channels: no Stream, Planner (Tasks by Planner and To Do) or Forms tabs; shared channels: the same minus To Do.
$script:NoTabsInPrivateOrShared = @('MicrosoftStream', 'Planner', 'MicrosoftForms')
#   PnP: TeamTabType (3.x)
$script:TabTypes = @('WebSite', 'DocumentLibrary', 'Wiki', 'Planner', 'MicrosoftStream', 'MicrosoftForms', 'Word', 'Excel',
    'PowerPoint', 'PDF', 'OneNote', 'PowerBI', 'SharePointPageAndList', 'Custom')
$script:TeamVisibilities = @('Public', 'Private')

function Import-MgJson {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Path)
    Get-Content -LiteralPath $Path -Raw -Encoding utf8 | ConvertFrom-Json -Depth 30
}

function Get-MgProp($Object, [string]$Name, $Default = $null) {
    if ($null -eq $Object) { return $Default }
    if ($Object -is [System.Collections.IDictionary]) { if ($Object.Contains($Name)) { return $Object[$Name] } else { return $Default } }
    if ($Object.PSObject.Properties[$Name]) { $Object.$Name } else { $Default }
}

function New-MgFinding([string]$Rule, [string]$Severity, [string]$Target, [string]$Message) {
    [pscustomobject]@{ Rule = $Rule; Severity = $Severity; Target = $Target; Message = $Message }
}

function New-MgStep([string]$Action, [string]$Target, [string]$Detail = '') {
    [pscustomobject]@{ Action = $Action; Target = $Target; Detail = $Detail }
}

function ConvertTo-MgUpn {
    <# .SYNOPSIS  'alex.demo' + 'contoso.com' -> 'alex.demo@contoso.com'; a name that already has an @ is left alone. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Name, [string]$Suffix)
    if ($Name.Contains('@')) { return $Name }
    if (-not $Suffix) { return $Name }
    "$Name@$($Suffix.TrimStart('@'))"
}

function Get-MgUserKey([string]$Name) {
    # Compare people by the part before the @, so 'alex.demo' and 'Alex.Demo@contoso.com' are the same person.
    if (-not $Name) { return '' }
    ($Name.Split('@')[0]).ToLowerInvariant()
}

function ConvertTo-MgAbsUrl([string]$Url, [string]$TenantUrl) {
    if ($Url -match '^https?://') { return $Url }
    $TenantUrl.TrimEnd('/') + '/' + $Url.TrimStart('/')
}

function Get-MgSiteKey {
    <# .SYNOPSIS  The site collection of a URL: '/sites/Name' or '/teams/Name' (lower case), '' for the root site. #>
    [CmdletBinding()]
    param([string]$Url)
    if (-not $Url) { return '' }
    $u = [uri]::UnescapeDataString($Url)
    if ($u -match '^(?:https?://[^/]+)?(/(?:sites|teams)/[^/]+)') { return $Matches[1].ToLowerInvariant() }
    ''
}

function Test-MgChannelName {
    <# .SYNOPSIS  Returns the reasons a channel name is not allowed (empty array = fine). Learn: Limits and specifications for Teams. #>
    [CmdletBinding()]
    param([AllowEmptyString()][string]$Name)
    $why = @()
    if ([string]::IsNullOrWhiteSpace($Name)) { return @('the name is empty') }
    if ($Name.Length -gt $script:MaxChannelNameLength) { $why += "$($Name.Length) characters: the limit is $script:MaxChannelNameLength" }
    $bad = @($Name.ToCharArray() | Where-Object { $script:BadNameChars -contains $_ } | Select-Object -Unique)
    if ($bad) { $why += "contains $(($bad | ForEach-Object { "'$_'" }) -join ' ')" }
    if ($Name.Contains('..')) { $why += "contains '..'" }
    if ($Name -match '[\u0000-\u001F\u0080-\u009F]') { $why += 'contains a control character' }
    if ($Name -match '^[_.]') { $why += 'starts with an underscore or a period' }
    if ($Name.EndsWith('.')) { $why += 'ends with a period' }
    if ($script:BadNameWords -contains $Name) { $why += "'$Name' is a reserved word" }
    if ($Name -like '*_vti_*') { $why += "contains the reserved word '_vti_'" }
    $why
}

function Test-MgTeamPlan {
    <#
    .SYNOPSIS  Lints a team plan before anything exists. Rules TP001-TP013 (see README).
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Plan)
    $f = [System.Collections.Generic.List[object]]::new()
    $team = Get-MgProp $Plan 'team'
    $owners = @(Get-MgProp $team 'owners' @())
    $members = @(Get-MgProp $team 'members' @())
    $teamPeople = @(($owners + $members) | ForEach-Object { Get-MgUserKey $_ })

    if (-not (Get-MgProp $team 'displayName' '')) { $f.Add((New-MgFinding 'TP001' 'Error' 'team.displayName' 'The team has no display name.')) }
    if ($owners.Count -eq 0) { $f.Add((New-MgFinding 'TP001' 'Error' 'team.owners' 'A team needs at least one owner.')) }
    elseif ($owners.Count -gt $script:MaxTeamOwners) { $f.Add((New-MgFinding 'TP001' 'Error' 'team.owners' "$($owners.Count) owners: Learn allows $script:MaxTeamOwners per team.")) }
    elseif ($owners.Count -eq 1) { $f.Add((New-MgFinding 'TP013' 'Warning' 'team.owners' 'One owner only: if that person leaves, nobody can manage the team (convention: two owners).')) }
    $vis = Get-MgProp $team 'visibility' 'Private'
    if ($vis -notin $script:TeamVisibilities) { $f.Add((New-MgFinding 'TP002' 'Error' 'team.visibility' "'$vis': the visibility is Public or Private.")) }

    $channels = @(Get-MgProp $Plan 'channels' @())
    $names = @{}
    foreach ($c in $channels) {
        $n = "$(Get-MgProp $c 'name' '')"
        $t = "$(Get-MgProp $c 'type' 'Standard')"
        $target = "channel '$n'"
        foreach ($why in (Test-MgChannelName $n)) { $f.Add((New-MgFinding 'TP003' 'Error' $target "Not a valid channel name: $why.")) }
        if ($n -ieq 'General') { $f.Add((New-MgFinding 'TP005' 'Warning' $target 'Every team already has a General channel; the plan does not need to create it.')) }
        elseif ($names.ContainsKey($n.ToLowerInvariant())) { $f.Add((New-MgFinding 'TP004' 'Error' $target 'The plan finds channels by name: names must be unique (case does not count).')) }
        $names[$n.ToLowerInvariant()] = $true
        if ($t -notin $script:ChannelTypes) { $f.Add((New-MgFinding 'TP006' 'Error' $target "Type '$t': Standard, Private or Shared.")); continue }
        if ($t -ne 'Standard') {
            $owner = Get-MgProp $c 'owner' ''
            if (-not $owner) { $f.Add((New-MgFinding 'TP007' 'Error' $target "A $t channel needs an owner (Add-PnPTeamsChannel -OwnerUPN).")) }
        }
        if ($t -eq 'Private') {
            foreach ($p in @(@(Get-MgProp $c 'owner' '') + @(Get-MgProp $c 'members' @()) | Where-Object { $_ })) {
                if ((Get-MgUserKey $p) -notin $teamPeople) {
                    $f.Add((New-MgFinding 'TP008' 'Error' $target "$p is not in the team: only existing team members can be added to a private channel."))
                }
            }
        }
    }
    if ($channels.Count + 1 -gt $script:MaxChannelsPerTeam) {
        $f.Add((New-MgFinding 'TP009' 'Error' 'channels' "$($channels.Count + 1) channels with General: Learn allows $script:MaxChannelsPerTeam per team."))
    }

    $byName = @{ 'general' = 'Standard' }
    foreach ($c in $channels) { $byName["$(Get-MgProp $c 'name' '')".ToLowerInvariant()] = "$(Get-MgProp $c 'type' 'Standard')" }
    foreach ($tab in @(Get-MgProp $Plan 'tabs' @())) {
        $target = "tab '$(Get-MgProp $tab 'name' '')' in '$(Get-MgProp $tab 'channel' '')'"
        $ty = "$(Get-MgProp $tab 'type' '')"
        $ch = "$(Get-MgProp $tab 'channel' '')".ToLowerInvariant()
        $url = "$(Get-MgProp $tab 'url' '')"
        if ($ty -notin $script:TabTypes) { $f.Add((New-MgFinding 'TP010' 'Error' $target "Tab type '$ty' is not one of PnP's TeamTabType values.")) }
        if (-not $byName.ContainsKey($ch)) { $f.Add((New-MgFinding 'TP010' 'Error' $target 'The channel is not in the plan (and is not General).')) }
        elseif ($byName[$ch] -in @('Private', 'Shared') -and $ty -in $script:NoTabsInPrivateOrShared) {
            $f.Add((New-MgFinding 'TP010' 'Error' $target "$($byName[$ch]) channels do not support $ty tabs."))
        }
        if (-not $url) { $f.Add((New-MgFinding 'TP011' 'Error' $target 'The tab has no URL.')) }
        elseif ($url -notmatch '^(/|https://)') { $f.Add((New-MgFinding 'TP011' 'Error' $target "'$url': use https:// or a server-relative path.")) }
    }

    $hub = Get-MgProp $Plan 'hub'
    if ($hub -and (Get-MgProp $hub 'url' '') -notmatch '^(/|https://)') { $f.Add((New-MgFinding 'TP012' 'Error' 'hub.url' "'$(Get-MgProp $hub 'url' '')': use https:// or a server-relative path.")) }
    $f.ToArray()
}

function Get-MgChannelStorage {
    <#
    .SYNOPSIS  Where each channel's files live, from the plan alone: the team site (one folder per standard channel)
               or a channel site of its own (private, shared). Learn: Teams-connected sites.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Plan)
    $rows = @([pscustomobject]@{ Channel = 'General'; Type = 'Standard'; Files = 'team site, folder General'; Site = 'team site' })
    foreach ($c in @(Get-MgProp $Plan 'channels' @())) {
        $t = "$(Get-MgProp $c 'type' 'Standard')"
        if ("$(Get-MgProp $c 'name' '')" -ieq 'General') { continue }
        $rows += [pscustomobject]@{
            Channel = $c.name; Type = $t
            Files = $(if ($t -eq 'Standard') { "team site, folder $($c.name)" } else { 'a channel site of its own' })
            Site = $(if ($t -eq 'Standard') { 'team site' } else { "channel site: $($c.name)" })
        }
    }
    $rows
}

function Test-MgTeamLive {
    <#
    .SYNOPSIS  Compares the plan with the state read from the tenant (Get-MgTeamState). Rules TL001-TL007.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Plan, [Parameter(Mandatory)]$State)
    $f = [System.Collections.Generic.List[object]]::new()
    $name = $Plan.team.displayName
    if (-not $State.Team) { return @(New-MgFinding 'TL001' 'Error' $name 'The team does not exist.') }
    $live = @{}
    foreach ($c in @($State.Channels)) { $live[$c.Name.ToLowerInvariant()] = $c }
    $general = $live['general']

    foreach ($c in @(Get-MgProp $Plan 'channels' @())) {
        $target = "channel '$($c.name)'"
        $l = $live[$c.name.ToLowerInvariant()]
        if (-not $l) { $f.Add((New-MgFinding 'TL002' 'Error' $target 'The channel does not exist.')); continue }
        $want = "$(Get-MgProp $c 'type' 'Standard')"
        if ($l.Type -ine $want) {
            $f.Add((New-MgFinding 'TL003' 'Error' $target "It is $($l.Type), the plan says $want. A channel's type can't be changed: delete it and create it again."))
            continue
        }
        if ($want -ne 'Standard') {
            $have = @($l.Members | ForEach-Object { Get-MgUserKey $_.Email })
            foreach ($p in @(@(Get-MgProp $c 'owner' '') + @(Get-MgProp $c 'members' @()) | Where-Object { $_ })) {
                if ((Get-MgUserKey $p) -notin $have) { $f.Add((New-MgFinding 'TL004' 'Error' $target "$p is not a member of the channel.")) }
            }
        }
    }

    foreach ($tab in @(Get-MgProp $Plan 'tabs' @())) {
        $target = "tab '$($tab.name)' in '$($tab.channel)'"
        $l = $live[$tab.channel.ToLowerInvariant()]
        if (-not $l) { continue }
        $t = @($l.Tabs | Where-Object { $_.Name -ieq $tab.name }) | Select-Object -First 1
        if (-not $t) { $f.Add((New-MgFinding 'TL005' 'Error' $target 'The tab does not exist.')); continue }
        $path = [uri]::UnescapeDataString(($tab.url -replace '^https://[^/]+', ''))
        if ([uri]::UnescapeDataString("$($t.Url)") -notlike "*$path*") {
            $f.Add((New-MgFinding 'TL005' 'Error' $target "Points to '$($t.Url)', the plan says '$($tab.url)'."))
        }
    }

    # Storage: standard channels share the team site; each private or shared channel has its own site (Learn).
    $teamSite = if ($general) { Get-MgSiteKey $general.FilesWebUrl } else { '' }
    foreach ($l in @($State.Channels)) {
        if (-not $l.FilesWebUrl) { continue }
        $k = Get-MgSiteKey $l.FilesWebUrl
        if ($l.Type -ieq 'Standard' -and $teamSite -and $k -ne $teamSite) {
            $f.Add((New-MgFinding 'TL006' 'Warning' "channel '$($l.Name)'" "Standard channel files are on $k, not on the team site $teamSite."))
        }
        elseif ($l.Type -ine 'Standard' -and $teamSite -and $k -eq $teamSite) {
            $f.Add((New-MgFinding 'TL006' 'Warning' "channel '$($l.Name)'" "A $($l.Type) channel should have a site of its own, but its files folder is on the team site."))
        }
    }

    $hub = Get-MgProp $Plan 'hub'
    if ($hub) {
        if (-not $State.TeamSite -or -not $State.TeamSite.HubSiteId -or "$($State.TeamSite.HubSiteId)" -eq [guid]::Empty.ToString()) {
            $f.Add((New-MgFinding 'TL007' 'Error' 'hub' "The team site is not in a hub (the plan: $($hub.url))."))
        }
        elseif ("$($State.TeamSite.HubSiteId)" -ne "$($State.Hub.Id)") {
            $f.Add((New-MgFinding 'TL007' 'Error' 'hub' "The team site is in another hub ($($State.TeamSite.HubSiteId)), the plan says $($hub.url)."))
        }
    }
    $f.ToArray()
}

# ---- Tenant functions (PnP.PowerShell) -----------------------------------------------------------------------------

function Find-MgTeam {
    param([Parameter(Mandatory)][string]$DisplayName, $Connection)
    $c = @{}; if ($Connection) { $c.Connection = $Connection }
    $hits = @(Get-PnPTeamsTeam -Filter "displayName eq '$($DisplayName.Replace("'", "''"))'" @c)
    if ($hits.Count -gt 1) { throw "$($hits.Count) teams are called '$DisplayName'. The plan finds the team by name: rename one." }
    $hits | Select-Object -First 1
}

function Wait-MgFilesFolder {
    <# .SYNOPSIS  The team site and the channel sites can take a while to provision; Graph's filesFolder call triggers and waits for it. #>
    param([Parameter(Mandatory)]$GroupId, [Parameter(Mandatory)]$ChannelId, [int]$Tries = 10, [int]$DelaySeconds = 15, $Connection)
    $c = @{}; if ($Connection) { $c.Connection = $Connection }
    for ($i = 1; $i -le $Tries; $i++) {
        try { return Get-PnPTeamsChannelFilesFolder -Team $GroupId -Channel $ChannelId @c } catch {
            if ($i -eq $Tries) { throw }
            Start-Sleep -Seconds $DelaySeconds
        }
    }
}

function Invoke-MgTeam {
    <#
    .SYNOPSIS  Creates what the plan describes and is missing: the team, channels (with owners for private and shared
               ones), channel members, tabs, and the team site's hub association. Idempotent; -WhatIf shows the steps.
               -Connection: one PnP connection with the Graph permissions in the README (a tenant admin URL works for
               the hub step too).
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)]$Plan, [string]$UpnSuffix, [string]$TenantUrl, $Connection, [int]$WaitSeconds = 15)
    $c = @{}; if ($Connection) { $c.Connection = $Connection }
    $t = $Plan.team
    $upn = { param($n) ConvertTo-MgUpn -Name $n -Suffix $UpnSuffix }

    $team = Find-MgTeam -DisplayName $t.displayName -Connection $Connection
    if (-not $team) {
        $p = @{
            DisplayName = $t.displayName; Visibility = Get-MgProp $t 'visibility' 'Private'
            Owners = @($t.owners | ForEach-Object { & $upn $_ })
        }
        if (Get-MgProp $t 'mailNickname' '') { $p.MailNickName = $t.mailNickname }
        if (Get-MgProp $t 'description' '') { $p.Description = $t.description }
        if (@(Get-MgProp $t 'members' @()).Count) { $p.Members = @($t.members | ForEach-Object { & $upn $_ }) }
        if ($PSCmdlet.ShouldProcess($t.displayName, 'Create team')) { $team = New-PnPTeamsTeam @p @c }
        New-MgStep 'CreateTeam' $t.displayName "owners: $(@($t.owners).Count), members: $(@(Get-MgProp $t 'members' @()).Count)"
    }
    $gid = if ($team) { "$($team.GroupId)" } else { $null }

    # channels
    $existing = @{}
    if ($gid) { foreach ($ch in @(Get-PnPTeamsChannel -Team $gid @c)) { $existing[$ch.DisplayName.ToLowerInvariant()] = $ch } }
    foreach ($ch in @(Get-MgProp $Plan 'channels' @())) {
        $type = "$(Get-MgProp $ch 'type' 'Standard')"
        $live = $existing[$ch.name.ToLowerInvariant()]
        if (-not $live) {
            $p = @{ Team = $gid; DisplayName = $ch.name }
            if (Get-MgProp $ch 'description' '') { $p.Description = $ch.description }
            if ($type -ne 'Standard') { $p.ChannelType = $type; $p.OwnerUPN = & $upn $ch.owner }
            if ($gid -and $PSCmdlet.ShouldProcess($ch.name, "Create $type channel")) { $live = Add-PnPTeamsChannel @p @c }
            New-MgStep 'AddChannel' $ch.name $(if ($type -eq 'Standard') { 'standard: a folder in the team site' } else { "$type, owner $($ch.owner): its own SharePoint site" })
        }
        if ($type -ne 'Standard' -and $live) {
            $have = @(Get-PnPTeamsChannelUser -Team $gid -Channel $live.Id @c | ForEach-Object { Get-MgUserKey $_.Email })
            foreach ($m in @(Get-MgProp $ch 'members' @())) {
                if ((Get-MgUserKey $m) -in $have) { continue }
                if ($PSCmdlet.ShouldProcess("$($ch.name): $m", 'Add channel member')) { $null = Add-PnPTeamsChannelUser -Team $gid -Channel $live.Id -User (& $upn $m) -Role Member @c }
                New-MgStep 'AddMember' $ch.name $m
            }
        }
        if ($live) { $existing[$ch.name.ToLowerInvariant()] = $live }
    }

    # tabs
    $general = if ($gid) { Get-PnPTeamsChannel -Team $gid -Identity 'General' @c } else { $null }
    if ($general) { $existing['general'] = $general }
    foreach ($tab in @(Get-MgProp $Plan 'tabs' @())) {
        $live = $existing[$tab.channel.ToLowerInvariant()]
        $have = if ($live) { @(Get-PnPTeamsTab -Team $gid -Channel $live.Id @c | ForEach-Object { $_.DisplayName }) } else { @() }
        if ($tab.name -in $have) { continue }
        $p = @{ DisplayName = $tab.name; Type = $tab.type }
        $abs = ConvertTo-MgAbsUrl $tab.url $TenantUrl
        if ($tab.type -eq 'SharePointPageAndList') { $p.WebsiteUrl = $abs } else { $p.ContentUrl = $abs }
        if ($live -and $PSCmdlet.ShouldProcess("$($tab.channel): $($tab.name)", 'Add tab')) { $null = Add-PnPTeamsTab -Team $gid -Channel $live.Id @p @c }
        New-MgStep 'AddTab' $tab.channel "$($tab.name) ($($tab.type))"
    }

    # hub: associate the parent team site; Learn: the channel sites follow it
    $hub = Get-MgProp $Plan 'hub'
    if ($hub -and $general) {
        $folder = Wait-MgFilesFolder -GroupId $gid -ChannelId $general.Id -DelaySeconds $WaitSeconds -Connection $Connection
        $siteUrl = ($folder.webUrl -replace '^(https://[^/]+/(?:sites|teams)/[^/]+).*', '$1')
        $hubUrl = ConvertTo-MgAbsUrl $hub.url $TenantUrl
        $site = Get-PnPTenantSite -Identity $siteUrl @c
        $hubInfo = Get-PnPHubSite -Identity $hubUrl @c
        if ("$(Get-MgProp $site 'HubSiteId' '')" -ne "$(Get-MgProp $hubInfo 'ID' '')") {
            if ($PSCmdlet.ShouldProcess($siteUrl, "Associate with $($hub.url)")) { $null = Add-PnPHubSiteAssociation -Site $siteUrl -HubSite $hubUrl @c }
            New-MgStep 'Associate' (Get-MgSiteKey $siteUrl) $hub.url
        }
    }
    elseif ($hub) { New-MgStep 'Associate' $hub.url 'after the team exists' }
}

function Get-MgTeamState {
    <#
    .SYNOPSIS  Reads the team, its channels (type, where the files folder is, tabs, members of private and shared
               channels) and the hub association of the team site. Input for Test-MgTeamLive.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Plan, [string]$TenantUrl, $Connection)
    $c = @{}; if ($Connection) { $c.Connection = $Connection }
    $team = Find-MgTeam -DisplayName $Plan.team.displayName -Connection $Connection
    if (-not $team) { return [pscustomobject]@{ Team = $null; Channels = @(); TeamSite = $null; Hub = $null } }
    $gid = "$($team.GroupId)"
    $channels = @(foreach ($ch in @(Get-PnPTeamsChannel -Team $gid @c)) {
        $folder = try { Get-PnPTeamsChannelFilesFolder -Team $gid -Channel $ch.Id @c } catch { $null }
        $tabs = @(Get-PnPTeamsTab -Team $gid -Channel $ch.Id @c | ForEach-Object {
            $cfg = Get-MgProp $_ 'Configuration'
            [pscustomobject]@{ Name = $_.DisplayName; Url = "$(Get-MgProp $cfg 'WebsiteUrl' (Get-MgProp $cfg 'ContentUrl' ''))" }
        })
        $members = if ("$($ch.MembershipType)" -ine 'standard') {
            @(Get-PnPTeamsChannelUser -Team $gid -Channel $ch.Id @c | ForEach-Object { [pscustomobject]@{ Email = $_.Email; Roles = @($_.Roles) } })
        } else { @() }
        [pscustomobject]@{
            Id = $ch.Id; Name = $ch.DisplayName; Type = "$($ch.MembershipType)"
            FilesWebUrl = $(if ($folder) { "$($folder.webUrl)" } else { '' }); Tabs = $tabs; Members = $members
        }
    })
    $general = $channels | Where-Object { $_.Name -ieq 'General' } | Select-Object -First 1
    $siteKey = if ($general) { Get-MgSiteKey $general.FilesWebUrl } else { '' }
    $site = $null; $hub = $null
    if ($siteKey) {
        $site = Get-PnPTenantSite -Identity (ConvertTo-MgAbsUrl $siteKey $TenantUrl) @c
        if (Get-MgProp $Plan 'hub') { $hub = Get-PnPHubSite -Identity (ConvertTo-MgAbsUrl $Plan.hub.url $TenantUrl) @c }
    }
    [pscustomobject]@{
        Team = $team; Channels = $channels
        TeamSite = $(if ($site) { [pscustomobject]@{ Url = $siteKey; HubSiteId = "$(Get-MgProp $site 'HubSiteId' '')" } })
        Hub = $(if ($hub) { [pscustomobject]@{ Id = "$(Get-MgProp $hub 'ID' '')" } })
    }
}

Export-ModuleMember -Function Import-MgJson, ConvertTo-MgUpn, Get-MgSiteKey, Test-MgChannelName, Test-MgTeamPlan, Get-MgChannelStorage,
    Test-MgTeamLive, Invoke-MgTeam, Get-MgTeamState
