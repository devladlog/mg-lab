#Requires -Version 7.2
<#
.SYNOPSIS
    Lint the intranet blueprint (home site, global navigation, news, brand assets, theme contrast); then, against the
    lab tenant: add and apply the theme, set the home site and the organization news sites, register the brand
    images library, build the global navigation, and read everything back.

.EXAMPLE
    ./Invoke-IntranetDesign.ps1 -BlueprintPath ./bad/bad-intranet.json                                  # lint only
.EXAMPLE
    ./Invoke-IntranetDesign.ps1 -ThemePath ./fixtures/learn-default-themes.json                         # contrast of any theme file
.EXAMPLE
    $t = @{ TenantUrl = 'https://contoso.sharepoint.com'; AdminUrl = 'https://contoso-admin.sharepoint.com'
            ClientId = '00000000-0000-0000-0000-000000000000' }
    ./Invoke-IntranetDesign.ps1 -BlueprintPath ./intranet/contoso-intranet.json @t -Provision -WhatIf
    ./Invoke-IntranetDesign.ps1 -BlueprintPath ./intranet/contoso-intranet.json @t -Provision
    ./Invoke-IntranetDesign.ps1 -BlueprintPath ./intranet/contoso-intranet.json @t -Check
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$BlueprintPath,
    [string]$ThemePath,
    [string]$TenantUrl,
    [string]$AdminUrl,
    [string]$ClientId,
    [switch]$Provision,
    [switch]$Check
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'MgIntranet.psm1') -Force

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

function Show-Steps { process { Write-Host ('{0,-13} {1,-46} {2}' -f $_.Action, $_.Target, $_.Detail) } }

if ($ThemePath) {
    $doc = Import-MgJson -Path $ThemePath
    $themes = if ($doc.PSObject.Properties['themes']) { @($doc.themes) } else { @($doc) }
    $all = @()
    foreach ($th in $themes) {
        $f = @(Test-MgTheme -Theme $th)
        Write-Host ('{0,-4} {1}' -f $(if ($f.Count) { 'x' } else { 'ok' }), $th.name) -ForegroundColor $(if ($f.Count) { 'Red' } else { 'Green' })
        $all += $f
    }
    Show-Findings $all; Show-Count $all
    if (-not $BlueprintPath) { return }
}
if (-not $BlueprintPath) { throw 'Provide -BlueprintPath (or -ThemePath to check a theme file).' }

# 1. Lint: no tenant needed
$bp = Import-MgJson -Path $BlueprintPath
$base = Split-Path -Parent (Resolve-Path $BlueprintPath)
Write-Host "Intranet blueprint: $BlueprintPath" -ForegroundColor Cyan
$theme = if ($bp.PSObject.Properties['theme'] -and $bp.theme) { Import-MgJson -Path (Join-Path $base $bp.theme.path) } else { $null }
if ($theme) {
    $p = $theme.palette
    foreach ($pair in @(@('neutralPrimary', 'white'), @('themePrimary', 'white'), @('white', 'themePrimary'))) {
        Write-Host ('  {0,-15} on {1,-13} {2,6}:1' -f $pair[0], $pair[1], (Get-MgContrastRatio $p.($pair[0]) $p.($pair[1])))
    }
}
$all = @(Test-MgIntranet -Blueprint $bp -BaseDir $base)
Show-Findings $all
Show-Count $all
if (-not $TenantUrl) { return }
if (@($all | Where-Object Severity -eq 'Error').Count) { throw 'Fix the errors before touching the tenant.' }

# 2. Tenant: the admin center for tenant settings, the home site for its navigation and the brand library
if (-not ($AdminUrl -and $ClientId)) { throw 'Provide -AdminUrl and -ClientId (your own Entra app for PnP, delegated permissions).' }
Import-Module PnP.PowerShell -ErrorAction Stop
$homeUrl = $TenantUrl.TrimEnd('/') + $bp.homeSite.url
$admin = Connect-PnPOnline -Url $AdminUrl -ClientId $ClientId -DeviceLogin -ReturnConnection
$site = Connect-PnPOnline -Url $homeUrl -ClientId $ClientId -DeviceLogin -ReturnConnection
$audiences = @{}
foreach ($a in @($bp.audiences.PSObject.Properties)) {
    $audiences[$a.Name] = if ("$($a.Value)" -as [guid]) { [guid]"$($a.Value)" } else { [guid]"$((Get-PnPEntraIDGroup -Identity $a.Name -Connection $site).Id)" }
}

if ($Provision) {
    Write-Host 'Theme:' -ForegroundColor Cyan
    Invoke-MgTenantTheme -Theme $theme -ApplyTo @($bp.theme.applyTo) -TenantUrl $TenantUrl -Connection $admin -WhatIf:$WhatIfPreference | Show-Steps
    Write-Host 'Home site and news:' -ForegroundColor Cyan
    Invoke-MgHomeSite -Blueprint $bp -TenantUrl $TenantUrl -Connection $admin -WhatIf:$WhatIfPreference | Show-Steps
    Invoke-MgOrgNews -Blueprint $bp -TenantUrl $TenantUrl -Connection $admin -WhatIf:$WhatIfPreference | Show-Steps
    Write-Host 'Organization assets:' -ForegroundColor Cyan
    Invoke-MgOrgAssets -Blueprint $bp -BaseDir $base -TenantUrl $TenantUrl -SiteConnection $site -AdminConnection $admin -WhatIf:$WhatIfPreference | Show-Steps
    Write-Host 'Global navigation (home site navigation):' -ForegroundColor Cyan
    Invoke-MgGlobalNavigation -Blueprint $bp -TenantUrl $TenantUrl -AudienceIds $audiences -Connection $site -WhatIf:$WhatIfPreference | Show-Steps
    Write-Host 'Then: home site > Settings > Global navigation > Enable, title, logo, source "Home site navigation".' -ForegroundColor DarkGray
}
if ($Check) {
    Write-Host "Tenant vs blueprint:" -ForegroundColor Cyan
    $state = Get-MgIntranetState -Blueprint $bp -Theme $theme -AdminConnection $admin -SiteConnection $site
    Write-Host ("  home site: {0}  news sites: {1}  asset libraries: {2}  theme: {3}" -f $state.HomeSite, @($state.OrgNewsSites).Count, @($state.OrgAssetLibraries).Count, $(if ($state.Theme) { $theme.name } else { 'missing' }))
    $f = @(Test-MgIntranetLive -Blueprint $bp -State $state -Theme $theme -AudienceIds $audiences)
    Show-Findings $f; Show-Count $f
}
