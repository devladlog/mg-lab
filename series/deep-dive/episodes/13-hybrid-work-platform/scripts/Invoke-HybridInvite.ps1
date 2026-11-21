#Requires -Version 7.2
<#
.SYNOPSIS
  Demo driver: creates a Teams meeting as the signed-in lab user, asks the broker for a guest link, prints both.
.DESCRIPTION
  Needs the lab tenant: Connect-MgGraph -Scopes OnlineMeetings.ReadWrite (as labadmin) and the function key of the
  broker (az functionapp keys list; never written to a file). -WhatIf shows what would be sent.
.EXAMPLE
  $key = Read-Host 'Function key' -AsSecureString
  ./Invoke-HybridInvite.ps1 -ApiBaseUrl https://func-hyb-xxxx.azurewebsites.net -FunctionKey $key -Subject 'Partner sync'
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][uri]$ApiBaseUrl,
    [Parameter(Mandatory)][securestring]$FunctionKey,
    [string]$Subject,
    [int]$ValidMinutes = 60,
    [int]$MaxUses = 3
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'HybridWork.psm1') -Force

$meeting = New-HybridMeeting -Subject $Subject -WhatIf:$WhatIfPreference
if (-not $meeting) { return }
$invite = New-GuestInvite -ApiBaseUrl $ApiBaseUrl -FunctionKey $FunctionKey -MeetingLink $meeting.JoinWebUrl `
    -ValidMinutes $ValidMinutes -MaxUses $MaxUses -WhatIf:$WhatIfPreference

[pscustomobject]@{
    Meeting    = $meeting.Subject
    LobbyScope = $meeting.LobbyScope
    HostJoin   = $meeting.JoinWebUrl
    GuestLink  = $invite.InviteUrl
    ExpiresOn  = $invite.ExpiresOn
    MaxUses    = $invite.MaxUses
}
