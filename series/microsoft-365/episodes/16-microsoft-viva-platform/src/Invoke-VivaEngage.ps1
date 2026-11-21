#Requires -Version 7.2
<#
.SYNOPSIS
    Viva Engage communities as code: preview, apply, audit (Microsoft Graph v1.0).

.EXAMPLE
    ./Invoke-VivaEngage.ps1 -Audit -InventoryFile ../tests/fixtures/inventory.json -OutFile ../sample/viva-audit.md   # offline
.EXAMPLE
    ./Invoke-VivaEngage.ps1 -Plan -InventoryFile ../tests/fixtures/inventory.json                                    # offline diff
.EXAMPLE
    ./Invoke-VivaEngage.ps1 -Apply -WhatIf
.EXAMPLE
    ./Invoke-VivaEngage.ps1 -Apply
.EXAMPLE
    ./Invoke-VivaEngage.ps1 -Audit -OutFile ./viva-audit.md -SaveInventory ./inventory.json -FailOnHigh
#>
[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSReviewUnusedParameter', 'Plan', Justification = 'Selects the parameter set')]
[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSReviewUnusedParameter', 'Apply', Justification = 'Selects the parameter set')]
[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSReviewUnusedParameter', 'Audit', Justification = 'Selects the parameter set')]
[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSReviewUnusedParameter', 'Now', Justification = 'Used inside Get-Inv')]
[CmdletBinding(SupportsShouldProcess, DefaultParameterSetName = 'Audit')]
param(
    [Parameter(ParameterSetName = 'Plan', Mandatory)][switch]$Plan,
    [Parameter(ParameterSetName = 'Apply', Mandatory)][switch]$Apply,
    [Parameter(ParameterSetName = 'Audit', Mandatory)][switch]$Audit,

    [Parameter(ParameterSetName = 'Plan')]
    [Parameter(ParameterSetName = 'Audit')][string]$InventoryFile,
    [Parameter(ParameterSetName = 'Audit')][string]$SaveInventory,
    [Parameter(ParameterSetName = 'Audit')][string]$OutFile,
    [Parameter(ParameterSetName = 'Audit')][switch]$FailOnHigh,
    [Parameter(ParameterSetName = 'Apply')][switch]$FixDrift,

    [string]$ConfigFile = (Join-Path $PSScriptRoot 'communities.json'),
    [datetimeoffset]$Now = [datetimeoffset]::UtcNow
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'VivaEngage/VivaEngage.psd1') -Force
$config = Get-VivaCommunityConfig -Path $ConfigFile

function Connect-VivaGraph([string[]]$Scopes) {
    Import-Module Microsoft.Graph.Authentication
    if (-not (Get-MgContext)) { Connect-MgGraph -Scopes $Scopes -NoWelcome }
}

function Get-Inv {
    if ($InventoryFile) { return (Get-Content -LiteralPath $InventoryFile -Raw | ConvertFrom-Json) }
    Connect-VivaGraph 'Community.Read.All', 'EngagementRole.Read.All', 'Group.Read.All', 'User.ReadBasic.All'
    Get-VivaInventory -Now $Now
}

switch ($PSCmdlet.ParameterSetName) {
    'Plan' {
        Get-VivaCommunityDiff -Config $config -Inventory (Get-Inv) | Format-Table Action, Community, Detail -AutoSize | Out-String -Width 200 | Write-Output
    }
    'Apply' {
        Connect-VivaGraph 'Community.ReadWrite.All', 'Group.ReadWrite.All', 'User.ReadBasic.All'
        Set-VivaCommunity -Config $config -FixDrift:$FixDrift -WhatIf:$WhatIfPreference | Format-Table -AutoSize | Out-String -Width 200 | Write-Output
    }
    'Audit' {
        $inventory = Get-Inv
        if ($SaveInventory -and -not $InventoryFile) { $inventory | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $SaveInventory -Encoding utf8 }
        $findings = @(Get-VivaFinding -Inventory $inventory -Config $config)
        $findings | Format-Table Severity, Subject, Rule, Detail -AutoSize | Out-String -Width 220 | Write-Output
        if ($OutFile) { ConvertTo-VivaMarkdown -Finding $findings -Inventory $inventory | Set-Content -LiteralPath $OutFile -Encoding utf8; Write-Output "Report: $OutFile" }
        if ($FailOnHigh -and @($findings | Where-Object Severity -eq 'High').Count) { exit 2 }
    }
}
