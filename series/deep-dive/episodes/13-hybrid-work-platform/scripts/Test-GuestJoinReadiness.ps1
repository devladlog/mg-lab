#Requires -Version 7.2
<# Prints the guest-join readiness checks for the signed-in Teams administrator (Connect-MicrosoftTeams first). Exit code 1 if any check fails. #>
[CmdletBinding()]
param([string]$PolicyIdentity = 'Global')
Import-Module (Join-Path $PSScriptRoot 'HybridWork.psm1') -Force
$r = Get-GuestJoinReadiness -PolicyIdentity $PolicyIdentity
$r | Format-Table Check, Passed, Detail -AutoSize -Wrap
if ($r.Where({ -not $_.Passed }).Count -gt 0) { exit 1 }
