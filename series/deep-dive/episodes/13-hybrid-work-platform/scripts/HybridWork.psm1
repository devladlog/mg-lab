#Requires -Version 7.2
<#
  Contoso hybrid-meeting helpers (DEVLADLOG Deep Dive #13).
  - New-OnlineMeetingBody / New-HybridMeeting : Microsoft Graph POST /me/onlineMeetings (delegated OnlineMeetings.ReadWrite)
  - New-GuestInvite                           : asks the invite broker (Azure Function) for a one-time guest link
  - Test-GuestJoinReadiness / Get-...         : checks the Teams settings an external guest depends on
  Defaults come from ../contract/hybrid.json; nothing here stores or prints a secret.
#>
Set-StrictMode -Version Latest

function Get-HybridContract {
    [CmdletBinding()]
    param([string]$Path = (Join-Path $PSScriptRoot '..' 'contract' 'hybrid.json'))
    Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json -Depth 10
}

function New-OnlineMeetingBody {
    <# Pure: builds the Graph request body. The lobby is closed to everyone except the organizer by default,
       so a guest from outside always waits to be admitted. #>
    [CmdletBinding()]
    param(
        [string]$Subject,
        [datetime]$Start = ([datetime]::UtcNow.AddMinutes(5)),
        [int]$DurationMinutes,
        [pscustomobject]$Contract = (Get-HybridContract)
    )
    $m = $Contract.meeting
    if (-not $Subject) { $Subject = $m.defaultSubject }
    if ($DurationMinutes -le 0) { $DurationMinutes = $m.defaultDurationMinutes }
    if ($DurationMinutes -gt 1440) { throw 'DurationMinutes must be 1440 or less.' }
    $startUtc = $Start.ToUniversalTime()
    [ordered]@{
        subject              = $Subject
        startDateTime        = $startUtc.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'")
        endDateTime          = $startUtc.AddMinutes($DurationMinutes).ToString("yyyy-MM-dd'T'HH:mm:ss'Z'")
        lobbyBypassSettings  = [ordered]@{ scope = $m.lobbyBypassScope; isDialInBypassEnabled = [bool]$m.isDialInBypassEnabled }
        allowedPresenters    = $m.allowedPresenters
        allowMeetingChat     = $m.allowMeetingChat
        isEntryExitAnnounced = [bool]$m.isEntryExitAnnounced
    }
}

function New-HybridMeeting {
    <# Creates the Teams meeting as the signed-in user. Run Connect-MgGraph -Scopes OnlineMeetings.ReadWrite first
       (delegated; the Graph docs list no application permission for POST /me/onlineMeetings). #>
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [string]$Subject,
        [datetime]$Start = ([datetime]::UtcNow.AddMinutes(5)),
        [int]$DurationMinutes,
        [pscustomobject]$Contract = (Get-HybridContract)
    )
    $body = New-OnlineMeetingBody -Subject $Subject -Start $Start -DurationMinutes $DurationMinutes -Contract $Contract
    if (-not $PSCmdlet.ShouldProcess('POST /me/onlineMeetings', "Create meeting '$($body.subject)'")) { return }

    $json = $body | ConvertTo-Json -Depth 5 -Compress
    $r = Invoke-MgGraphRequest -Method POST -Uri 'https://graph.microsoft.com/v1.0/me/onlineMeetings' -Body $json -ContentType 'application/json'
    # Invoke-MgGraphRequest returns a Hashtable; index it so a missing property is $null instead of an error under strict mode.
    if (-not $r['joinWebUrl']) { throw 'Graph returned no joinWebUrl.' }

    # Tenant policy can override what we asked for: report what the service actually applied.
    $lobby = $r['lobbyBypassSettings']
    $applied = if ($lobby) { [string]$lobby['scope'] } else { '' }
    if ($applied -and $applied -ne $body.lobbyBypassSettings.scope) {
        Write-Warning "Lobby scope requested '$($body.lobbyBypassSettings.scope)' but Teams applied '$applied'."
    }
    [pscustomobject]@{
        Id          = $r['id']
        Subject     = $r['subject']
        JoinWebUrl  = [string]$r['joinWebUrl']
        Start       = $r['startDateTime']
        End         = $r['endDateTime']
        LobbyScope  = $applied
    }
}

function New-GuestInvite {
    <# Asks the broker for a one-time guest link. The function key authenticates the HOST, never the guest. #>
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [Parameter(Mandatory)][uri]$ApiBaseUrl,
        [Parameter(Mandatory)][securestring]$FunctionKey,
        [Parameter(Mandatory)][string]$MeetingLink,
        [ValidateRange(1, 480)][int]$ValidMinutes,
        [ValidateRange(1, 25)][int]$MaxUses
    )
    if ($ApiBaseUrl.Scheme -ne 'https') { throw 'ApiBaseUrl must be https.' }
    $payload = @{ meetingLink = $MeetingLink }
    if ($PSBoundParameters.ContainsKey('ValidMinutes')) { $payload.validMinutes = $ValidMinutes }
    if ($PSBoundParameters.ContainsKey('MaxUses')) { $payload.maxUses = $MaxUses }
    $target = ([uri]::new($ApiBaseUrl, '/api/invites')).AbsoluteUri
    if (-not $PSCmdlet.ShouldProcess($target, 'Create guest invite')) { return }

    $key = [System.Net.NetworkCredential]::new('', $FunctionKey).Password
    try {
        $r = Invoke-RestMethod -Method Post -Uri $target -Headers @{ 'x-functions-key' = $key } `
            -ContentType 'application/json' -Body ($payload | ConvertTo-Json -Compress)
    }
    finally { $key = $null }
    [pscustomobject]@{ InviteUrl = [string]$r.inviteUrl; ExpiresOn = [datetimeoffset]$r.expiresOn; MaxUses = [int]$r.maxUses }
}

function Test-GuestJoinReadiness {
    <# Pure: judges the two Teams objects. Returns one result per check; Passed is $false for anything that blocks guests
       or lets them skip the lobby. #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]$MeetingConfiguration,
        [Parameter(Mandatory)]$MeetingPolicy,
        [pscustomobject]$Contract = (Get-HybridContract)
    )
    $results = [System.Collections.Generic.List[object]]::new()
    $add = { param($name, $ok, $detail) $results.Add([pscustomobject]@{ Check = $name; Passed = [bool]$ok; Detail = $detail }) }

    $disabled = [bool]$MeetingConfiguration.DisableAnonymousJoin
    & $add 'Tenant: anonymous join allowed' ((-not $disabled) -or (-not $Contract.readiness.mustAllowAnonymousJoin)) `
        "DisableAnonymousJoin = $disabled (Set-CsTeamsMeetingConfiguration -DisableAnonymousJoin `$false)"

    $allow = [bool]$MeetingPolicy.AllowAnonymousUsersToJoinMeeting
    & $add 'Organizer policy: anonymous join allowed' ($allow -or (-not $Contract.readiness.mustAllowAnonymousJoin)) `
        "AllowAnonymousUsersToJoinMeeting = $allow on policy '$($MeetingPolicy.Identity)'"

    $auto = [string]$MeetingPolicy.AutoAdmittedUsers
    $bad = @($Contract.readiness.lobbyAutoAdmittedUsersMustNotBe) -contains $auto
    & $add 'Organizer policy: lobby not open to everyone' (-not $bad) `
        "AutoAdmittedUsers = '$auto' (guests would skip the lobby if this is Everyone)"

    $results
}

function Get-GuestJoinReadiness {
    <# Reads the live tenant (needs Connect-MicrosoftTeams and a Teams administrator) and runs Test-GuestJoinReadiness. #>
    [CmdletBinding()]
    param([string]$PolicyIdentity = 'Global')
    foreach ($cmd in 'Get-CsTeamsMeetingConfiguration', 'Get-CsTeamsMeetingPolicy') {
        if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
            throw "$cmd not found. Install-Module MicrosoftTeams, then Connect-MicrosoftTeams."
        }
    }
    $cfg = Get-CsTeamsMeetingConfiguration
    $pol = Get-CsTeamsMeetingPolicy -Identity $PolicyIdentity
    Test-GuestJoinReadiness -MeetingConfiguration $cfg -MeetingPolicy $pol
}

Export-ModuleMember -Function Get-HybridContract, New-OnlineMeetingBody, New-HybridMeeting, New-GuestInvite, Test-GuestJoinReadiness, Get-GuestJoinReadiness
