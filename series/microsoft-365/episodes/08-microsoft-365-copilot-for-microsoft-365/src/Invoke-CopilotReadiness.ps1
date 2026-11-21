#Requires -Version 7.2
<#
.SYNOPSIS
    Runner for DEVLADLOG Microsoft 365 #8 (Microsoft 365 Copilot). Read-only; works without a Copilot licence.
.EXAMPLE
    # offline: analyse a saved snapshot (the fictional fixture)
    ./Invoke-CopilotReadiness.ps1 -Snapshot ../tests/fixtures/snapshot.json -OutFile ../sample/copilot-readiness.md
.EXAMPLE
    # needs tenant: collect from Graph, analyse, and save the snapshot (tenant data: never commit it)
    ./Invoke-CopilotReadiness.ps1 -ConfigFile ./copilot.lab.json -SaveSnapshot ./snapshot.lab.json -OutFile ./readiness.lab.md
.EXAMPLE
    # needs tenant AND a Microsoft 365 Copilot licence: usage report (refuses to run without a Copilot licence)
    ./Invoke-CopilotReadiness.ps1 -Check Usage
#>
[CmdletBinding()]
param(
    [string]$ConfigFile = (Join-Path $PSScriptRoot 'copilot.json'),
    [ValidateSet('Licences', 'Labels', 'Sharing', 'Usage')][string[]]$Check = @('Licences', 'Labels', 'Sharing'),
    [string]$Snapshot,
    [string]$SaveSnapshot,
    [string]$SiteSearch = '*',
    [string]$OutFile,
    [ValidateSet('D7', 'D28', 'D90', 'D180')][string]$UsagePeriod = 'D7'
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'CopilotReadiness/CopilotReadiness.psd1') -Force
$config = Get-CopilotConfig -Path $ConfigFile

function Show-Table($Data, [object[]]$Property) {
    # Out-String -Width: without a console (CI, redirected output) the default width is 0 and Format-Table prints nothing.
    $w = try { [Math]::Max(120, $Host.UI.RawUI.WindowSize.Width) } catch { 160 }
    $a = @{ AutoSize = $true; Wrap = $true }; if ($Property) { $a.Property = $Property }
    ($Data | Format-Table @a | Out-String -Width $w).TrimEnd() | Write-Output
}
function Connect-Graph([string[]]$Scopes) {
    if (-not (Get-Command Connect-MgGraph -ErrorAction SilentlyContinue)) { throw 'Install-Module Microsoft.Graph.Authentication -Scope CurrentUser' }
    $ctx = Get-MgContext
    if (-not $ctx -or ($Scopes | Where-Object { $_ -notin $ctx.Scopes })) { Connect-MgGraph -Scopes $Scopes -NoWelcome | Out-Null }
}

$skus = @(); $users = @(); $labels = @(); $items = @()
if ($Snapshot) {
    $s = Get-Content -LiteralPath $Snapshot -Raw | ConvertFrom-Json
    $skus = @($s.skus); $users = @($s.users); $labels = @($s.labels); $items = @($s.items)
    Write-Output "Snapshot collected $($s.collectedAt) ($($s.note))"
}
else {
    $scopes = @()
    if ('Licences' -in $Check -or 'Usage' -in $Check) { $scopes += 'LicenseAssignment.Read.All' }
    if ('Licences' -in $Check) { $scopes += 'User.Read.All' }
    if ('Labels' -in $Check) { $scopes += 'SensitivityLabel.Read' }
    if ('Sharing' -in $Check) { $scopes += 'Sites.Read.All', 'Files.Read.All' }
    if ('Usage' -in $Check) { $scopes += 'Reports.Read.All' }
    Connect-Graph ($scopes | Select-Object -Unique)
    if ('Licences' -in $Check -or 'Usage' -in $Check) { $skus = @(Get-CopilotSku) }
    if ('Licences' -in $Check) { $users = @(Get-CopilotUserLicence -Top $config.readiness.maxUsers) }
    if ('Labels' -in $Check) { $labels = @(Get-CopilotLabel) }
    if ('Sharing' -in $Check) {
        $items = @(Get-CopilotDrive -Search $SiteSearch | ForEach-Object {
                Get-CopilotSharedItem -DriveId $_.DriveId -Site $_.Site -MaxItems $config.sharing.maxItemsPerDrive -MaxDepth $config.sharing.maxDepth })
    }
    if ($SaveSnapshot) { ConvertTo-CopilotSnapshot -Skus $skus -Users $users -Labels $labels -Items $items -Note 'live' | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $SaveSnapshot }
}

$readiness = Test-CopilotReadiness -Skus $skus -Users $users -Config $config
if ('Licences' -in $Check -or $Snapshot) {
    $t = $readiness.Tenant
    Write-Output ("Copilot licence in tenant: {0}  (SKUs: {1}, seats assigned {2} of {3})" -f $(if ($t.HasCopilotLicence) { 'YES' } else { 'NO' }), $(if ($t.CopilotSkus) { $t.CopilotSkus -join ',' } else { '-' }), $t.SeatsAssigned, $t.SeatsEnabled)
    Show-Table $readiness.Users @('User', 'Status', 'CopilotChat', 'Mailbox', 'OfficeApps', 'Notes')
}
$labelFindings = @(); $sharingFindings = @()
if ('Labels' -in $Check -or ($Snapshot -and $labels.Count)) {
    $labelFindings = @(Get-CopilotLabelFinding -Labels $labels -Config $config)
    Show-Table $labelFindings @('Severity', 'Rule', 'Message')
}
if ('Sharing' -in $Check -or ($Snapshot -and $items.Count)) {
    $sharingFindings = @(Get-CopilotSharingFinding -Items $items -Config $config)
    Show-Table $sharingFindings @('Severity', 'Signal', 'Site', 'Path', 'Role')
    Write-Output ("{0} item(s) scanned, {1} broad-sharing finding(s)" -f $items.Count, $sharingFindings.Count)
}
if ('Usage' -in $Check) {
    if (-not $readiness.Tenant.HasCopilotLicence) {
        Write-Warning 'Usage report skipped: this tenant has no Microsoft 365 Copilot licence, and the Graph report only returns licensed users. Nothing was faked.'
    }
    else { Show-Table (Get-CopilotUsageReport -Period $UsagePeriod) }
}
if ($OutFile) {
    ConvertTo-CopilotMarkdown -Readiness $readiness -LabelFindings $labelFindings -SharingFindings $sharingFindings -LabelCount $labels.Count -ItemsScanned $items.Count -GeneratedOn (Get-Date -Format 'yyyy-MM-dd') | Set-Content -LiteralPath $OutFile
}
