#Requires -Version 7.2
<#
.SYNOPSIS
    Lint a team plan (and show where each channel's files will live); then, against the lab tenant: create the team,
    its channels, members, tabs and the hub association, and read everything back.

.EXAMPLE
    ./Invoke-TeamsIntegration.ps1 -PlanPath ./bad/bad.team.json                       # lint only
.EXAMPLE
    $t = @{ TenantUrl = 'https://contoso.sharepoint.com'; AdminUrl = 'https://contoso-admin.sharepoint.com'
            ClientId = '00000000-0000-0000-0000-000000000000'; UpnSuffix = 'contoso.com' }
    ./Invoke-TeamsIntegration.ps1 -PlanPath ./teams/purchasing.team.json @t -Provision -WhatIf
    ./Invoke-TeamsIntegration.ps1 -PlanPath ./teams/purchasing.team.json @t -Provision
    ./Invoke-TeamsIntegration.ps1 -PlanPath ./teams/purchasing.team.json @t -Check
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][string]$PlanPath,
    [string]$TenantUrl,
    [string]$AdminUrl,
    [string]$ClientId,
    [string]$UpnSuffix,
    [switch]$Provision,
    [switch]$Check
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'MgTeams.psm1') -Force

function Show-Findings($Findings) {
    if (-not $Findings) { Write-Host 'No findings.' -ForegroundColor Green; return }
    foreach ($f in $Findings | Sort-Object Severity, Rule) {
        $color = if ($f.Severity -eq 'Error') { 'Red' } else { 'Yellow' }
        Write-Host ('{0,-7} {1}  {2}' -f $f.Severity.ToUpper(), $f.Rule, $f.Target) -ForegroundColor $color
        Write-Host "              $($f.Message)"
    }
}

function Show-Count($Findings) {
    $e = @($Findings | Where-Object Severity -eq 'Error').Count
    $w = @($Findings | Where-Object Severity -eq 'Warning').Count
    Write-Host "$e error(s), $w warning(s)" -ForegroundColor $(if ($e) { 'Red' } elseif ($w) { 'Yellow' } else { 'Green' })
}

function Show-Steps { process { Write-Host ('{0,-11} {1,-28} {2}' -f $_.Action, $_.Target, $_.Detail) } }

# 1. Lint and storage map: no tenant needed
$plan = Import-MgJson -Path $PlanPath
Write-Host "Team plan: $PlanPath" -ForegroundColor Cyan
$all = @(Test-MgTeamPlan -Plan $plan)
Show-Findings $all
Show-Count $all
$hasErrors = @($all | Where-Object Severity -eq 'Error').Count -gt 0
if (-not $hasErrors) {
    $storage = @(Get-MgChannelStorage -Plan $plan)
    Write-Host 'Where the files will live:' -ForegroundColor Cyan
    $storage | ForEach-Object { Write-Host ('  {0,-22} {1,-9} {2}' -f $_.Channel, $_.Type, $_.Files) }
    $sites = @($storage | Select-Object -ExpandProperty Site -Unique).Count
    Write-Host "  -> $sites SharePoint site(s): the team site plus one per private or shared channel."
}
if (-not $TenantUrl) { return }
if ($hasErrors) { throw 'Fix the errors before touching the tenant.' }

# 2. Tenant: one delegated connection to the admin center covers the Graph calls (Teams) and the hub step
if (-not ($AdminUrl -and $ClientId)) { throw 'Provide -AdminUrl and -ClientId (your own Entra app for PnP, delegated permissions).' }
if (-not $UpnSuffix) { throw 'Provide -UpnSuffix (the domain of the lab users, for example contoso.com).' }
Import-Module PnP.PowerShell -ErrorAction Stop
$conn = Connect-PnPOnline -Url $AdminUrl -ClientId $ClientId -DeviceLogin -ReturnConnection

if ($Provision) {
    Write-Host 'Teams:' -ForegroundColor Cyan
    Invoke-MgTeam -Plan $plan -UpnSuffix $UpnSuffix -TenantUrl $TenantUrl -Connection $conn -WhatIf:$WhatIfPreference | Show-Steps
}
if ($Check) {
    Write-Host 'Tenant vs plan:' -ForegroundColor Cyan
    $state = Get-MgTeamState -Plan $plan -TenantUrl $TenantUrl -Connection $conn
    if ($state.Team) {
        Write-Host ("  team: {0}   channels: {1}   team site: {2}" -f $state.Team.DisplayName, @($state.Channels).Count, $(if ($state.TeamSite) { $state.TeamSite.Url } else { '?' }))
        foreach ($ch in $state.Channels) { Write-Host ('  {0,-22} {1,-9} {2}' -f $ch.Name, $ch.Type, (Get-MgSiteKey $ch.FilesWebUrl)) }
    }
    $f = @(Test-MgTeamLive -Plan $plan -State $state)
    Show-Findings $f; Show-Count $f
}
