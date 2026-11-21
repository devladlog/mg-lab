#Requires -Version 7.2
<#
.SYNOPSIS
    Lint the hub plan; then, against the lab tenant: register the hub, associate the sites, build the hub
    navigation with audience targeting, and read everything back to compare it with the plan.

.EXAMPLE
    ./Invoke-HubNavigation.ps1 -PlanPath ./bad/bad.hub.json                                            # lint only
.EXAMPLE
    ./Invoke-HubNavigation.ps1 -PlanPath ./hub/operations.hub.json -HubsPath ./fixtures/tenant-hubs.json  # + hierarchy check
.EXAMPLE
    $t = @{ TenantUrl = 'https://contoso.sharepoint.com'; AdminUrl = 'https://contoso-admin.sharepoint.com'
            ClientId = '00000000-0000-0000-0000-000000000000' }
    ./Invoke-HubNavigation.ps1 -PlanPath ./hub/operations.hub.json @t -Provision -WhatIf
    ./Invoke-HubNavigation.ps1 -PlanPath ./hub/operations.hub.json @t -Provision
    ./Invoke-HubNavigation.ps1 -PlanPath ./hub/operations.hub.json @t -Check
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][string]$PlanPath,
    [string]$HubsPath,
    [string]$TenantUrl,
    [string]$AdminUrl,
    [string]$ClientId,
    [switch]$Provision,
    [switch]$Move,
    [switch]$Check
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'MgHubNav.psm1') -Force

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

function Show-Steps { process { Write-Host ('{0,-12} {1,-48} {2}' -f $_.Action, $_.Target, $_.Detail) } }

function Show-Tree($Nodes, [string]$Indent = '  ') {
    foreach ($n in @($Nodes)) {
        $aud = @($n.PSObject.Properties['audiences'] | ForEach-Object { $_.Value }) | Where-Object { $_ }
        $url = if ($n.PSObject.Properties['url'] -and $n.url) { "  -> $($n.url)" } else { '' }
        Write-Host ("$Indent$($n.title)$url" + $(if ($aud) { "  [$(@($aud) -join ', ')]" } else { '' }))
        if ($n.PSObject.Properties['children']) { Show-Tree $n.children "$Indent  " }
    }
}

# 1. Lint: no tenant needed
$plan = Import-MgJson -Path $PlanPath
Write-Host "Hub plan: $PlanPath" -ForegroundColor Cyan
Show-Tree $plan.navigation.nodes
$all = @(Test-MgHubPlan -Plan $plan)
if ($HubsPath) {
    Write-Host "Hub hierarchy (with the planned hub): $HubsPath" -ForegroundColor Cyan
    $all += @(Test-MgHubHierarchy -Hubs @(Import-MgJson -Path $HubsPath) -Plan $plan)
}
Show-Findings $all
Show-Count $all
if (-not $TenantUrl) { return }
if (@($all | Where-Object Severity -eq 'Error').Count) { throw 'Fix the errors before touching the tenant.' }

# 2. Tenant: the admin center for hub registration and association, the hub site for its navigation
if (-not ($AdminUrl -and $ClientId)) { throw 'Provide -AdminUrl and -ClientId (your own Entra app for PnP, delegated permissions).' }
Import-Module PnP.PowerShell -ErrorAction Stop
$hubUrl = ConvertTo-MgAbsoluteUrl $plan.hub.url $TenantUrl
$admin = Connect-PnPOnline -Url $AdminUrl -ClientId $ClientId -DeviceLogin -ReturnConnection
$site = Connect-PnPOnline -Url $hubUrl -ClientId $ClientId -DeviceLogin -ReturnConnection
$audiences = Resolve-MgAudience -Plan $plan -Connection $site

if ($Provision) {
    Write-Host 'Hub:' -ForegroundColor Cyan
    Invoke-MgHubRegistration -Plan $plan -TenantUrl $TenantUrl -Connection $admin -WhatIf:$WhatIfPreference | Show-Steps
    Write-Host 'Associations:' -ForegroundColor Cyan
    Invoke-MgHubAssociation -Plan $plan -TenantUrl $TenantUrl -Move:$Move -Connection $admin -WhatIf:$WhatIfPreference | Show-Steps
    Write-Host 'Hub navigation:' -ForegroundColor Cyan
    Invoke-MgHubNavigation -Plan $plan -TenantUrl $TenantUrl -AudienceIds $audiences -Connection $site -WhatIf:$WhatIfPreference | Show-Steps
}
if ($Check) {
    Write-Host "Tenant vs plan ($($plan.hub.url)):" -ForegroundColor Cyan
    $state = Get-MgHubState -Plan $plan -TenantUrl $TenantUrl -AdminConnection $admin -SiteConnection $site
    Write-Host ("  hub: {0}  associated: {1}  hubs in tenant: {2}" -f $state.Hub.Title, @($state.Children).Count, @($state.AllHubs).Count)
    $f = @(Test-MgHubLive -Plan $plan -State $state -TenantUrl $TenantUrl -AudienceIds $audiences)
    Show-Findings $f; Show-Count $f
}
