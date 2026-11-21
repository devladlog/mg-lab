#Requires -Version 7.2
<#
.SYNOPSIS
    Lint a site template + pages, then (optionally) register the template, create or reuse a communication site,
    apply the template asynchronously, provision the pages and print what the template run did.

.EXAMPLE
    ./Invoke-ModernSite.ps1 -TemplatePath ./bad/template.json                     # lint only, no tenant
.EXAMPLE
    ./Invoke-ModernSite.ps1 -TemplatePath ./purchasing/template.json -SchemaPath ../tests/.schema-cache/site-script.schema.json
.EXAMPLE
    ./Invoke-ModernSite.ps1 -TemplatePath ./purchasing/template.json `
        -AdminUrl https://contoso-admin.sharepoint.com -SiteUrl https://contoso.sharepoint.com/sites/Purchasing `
        -ClientId 00000000-0000-0000-0000-000000000000 -CreateSite -WhatIf
.EXAMPLE
    ./Invoke-ModernSite.ps1 -RunReport -SiteUrl ... -AdminUrl ... -ClientId ...     # what did the last run do?
.EXAMPLE
    ./Invoke-ModernSite.ps1 -ExportFrom https://contoso.sharepoint.com/sites/HandBuilt -ClientId ...   # extract + lint
#>
[CmdletBinding(SupportsShouldProcess, DefaultParameterSetName = 'Template')]
param(
    [Parameter(ParameterSetName = 'Template', Mandatory)][string]$TemplatePath,
    [Parameter(ParameterSetName = 'Report', Mandatory)][switch]$RunReport,
    [Parameter(ParameterSetName = 'Export', Mandatory)][string]$ExportFrom,
    [Parameter(ParameterSetName = 'Export')][string[]]$Lists = @(),
    [string]$SchemaPath,
    [string]$SiteUrl,
    [string]$AdminUrl,
    [string]$ClientId,
    [Parameter(ParameterSetName = 'Template')][switch]$CreateSite,
    [Parameter(ParameterSetName = 'Template')][switch]$Force,
    [Parameter(ParameterSetName = 'Template')][int]$WaitSeconds = 180
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'MgSitePages.psm1') -Force

function Show-Findings($Findings) {
    if (-not $Findings) { Write-Host 'No findings.' -ForegroundColor Green; return }
    foreach ($f in $Findings | Sort-Object Severity, Rule) {
        $color = if ($f.Severity -eq 'Error') { 'Red' } else { 'Yellow' }
        $src = if ($f.PSObject.Properties['Source']) { "[$($f.Source)] " } else { '' }
        Write-Host ('{0,-7} {1}  {2}{3}' -f $f.Severity.ToUpper(), $f.Rule, $src, $f.Target) -ForegroundColor $color
        Write-Host "               $($f.Message)"
    }
    $e = @($Findings | Where-Object Severity -eq 'Error').Count
    $w = @($Findings | Where-Object Severity -eq 'Warning').Count
    Write-Host "$e error(s), $w warning(s)" -ForegroundColor $(if ($e) { 'Red' } else { 'Yellow' })
}

function Show-Steps { process { Write-Host ('{0,-15} {1,-40} {2}' -f $_.Action, $_.Target, $_.Detail) } }

function Connect-Lab([string]$Url) {
    if (-not $Url -or -not $ClientId) { throw 'Provide the URL and -ClientId (your own Entra app for PnP, delegated permissions).' }
    Import-Module PnP.PowerShell -ErrorAction Stop
    Connect-PnPOnline -Url $Url -ClientId $ClientId -DeviceLogin -ReturnConnection
}

if ($PSCmdlet.ParameterSetName -eq 'Export') {
    $conn = Connect-Lab $ExportFrom
    $json = Export-MgSiteScript -Url $ExportFrom -Lists $Lists -Connection $conn
    $out = Join-Path (Get-Location) 'exported.site-script.json'
    Set-Content -LiteralPath $out -Value $json -Encoding utf8
    Write-Host "Exported to $out" -ForegroundColor Cyan
    Show-Findings @(Test-MgSiteScript -Script ($json | ConvertFrom-Json -Depth 30) -Raw $json -WebTemplate 68 -SchemaPath $SchemaPath)
    return
}

if ($PSCmdlet.ParameterSetName -eq 'Report') {
    $admin = Connect-Lab $AdminUrl
    Get-MgSiteTemplateRunReport -WebUrl $SiteUrl -Connection $admin | ForEach-Object {
        $color = if ($_.Outcome -eq 'Success') { 'Green' } else { 'Red' }
        Write-Host ('{0,-9} {1}  {2}' -f $_.Outcome, $_.Action, $_.Detail) -ForegroundColor $color
    }
    return
}

# 1. Lint: no tenant needed
$findings = @(Test-MgSiteTemplate -ManifestPath $TemplatePath -SchemaPath $SchemaPath)
Write-Host "Lint: $TemplatePath" -ForegroundColor Cyan
Show-Findings $findings
if (-not $SiteUrl) { return }
if (@($findings | Where-Object Severity -eq 'Error').Count) { throw 'The template has errors. Fix them before provisioning.' }

# 2. Register the site scripts and the site template (SharePoint admin)
$admin = Connect-Lab $AdminUrl
$steps = @(Invoke-MgSiteTemplateRegistration -ManifestPath $TemplatePath -Connection $admin)
$steps | Where-Object Action -ne 'Result' | Show-Steps
$designId = ($steps | Where-Object Action -eq 'Result').SiteDesignId

# 3. Create the communication site if asked (site URL from -SiteUrl), then apply the template asynchronously
$m = Import-MgJson -Path $TemplatePath
if ($CreateSite -and $PSCmdlet.ShouldProcess($SiteUrl, 'Create communication site')) {
    $exists = $null
    try { $exists = Get-PnPTenantSite -Identity $SiteUrl -Connection $admin -ErrorAction Stop } catch { $exists = $null }
    if ($exists) { Write-Host "Site exists: reusing it" -ForegroundColor DarkGray }
    else {
        $null = New-PnPSite -Type CommunicationSite -Title $m.site.title -Url $SiteUrl -Wait -Connection $admin
        Write-Host ('{0,-15} {1}' -f 'CreateSite', $m.site.title)
    }
}
$task = Invoke-MgSiteTemplateApply -SiteDesignId $designId -WebUrl $SiteUrl -Connection $admin
if ($task) { Write-Host ('{0,-15} {1,-40} {2}' -f 'QueueTemplate', $m.title, "task $($task.Id)") }

# 4. Wait for the run, then show what each action did
if (-not $WhatIfPreference) {
    $deadline = (Get-Date).AddSeconds($WaitSeconds)
    do {
        Start-Sleep -Seconds 10
        $pending = @(Get-PnPSiteDesignTask -WebUrl $SiteUrl -Connection $admin)
    } while ($pending.Count -and (Get-Date) -lt $deadline)
    Write-Host 'Template run:' -ForegroundColor Cyan
    Get-MgSiteTemplateRunReport -WebUrl $SiteUrl -SiteDesignId $designId -Connection $admin | ForEach-Object {
        Write-Host ('{0,-9} {1}  {2}' -f $_.Outcome, $_.Action, $_.Detail) -ForegroundColor $(if ($_.Outcome -eq 'Success') { 'Green' } else { 'Red' })
    }
}

# 5. Pages (site owner on the new site)
$site = Connect-Lab $SiteUrl
Invoke-MgPageProvisioning -ManifestPath $TemplatePath -Force:$Force -Connection $site | Show-Steps
