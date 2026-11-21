#Requires -Version 7.2
<#
.SYNOPSIS
    DEVLADLOG Microsoft 365 #6 - Microsoft Defender for Office 365 as code, from defender.json.

.EXAMPLE
    # Offline (no tenant)
    ./Invoke-DefenderForOffice.ps1 -Audit -InventoryFile ../tests/fixtures/inventory.json -OutFile ../sample/defender-audit.md
    ./Invoke-DefenderForOffice.ps1 -Hunt -ShowQuery -Recipient sam.demo@contoso.onmicrosoft.com
    ./Invoke-DefenderForOffice.ps1 -SimulationReport -ReportFile ../tests/fixtures/simulation-report.json

.EXAMPLE
    # Lab tenant: Exchange Online for presets and audit, Microsoft Graph for hunting and simulations
    ./Invoke-DefenderForOffice.ps1 -PolicyFile ./defender.lab.json -Audit -SaveInventory ./inventory.lab.json
    ./Invoke-DefenderForOffice.ps1 -PolicyFile ./defender.lab.json -ApplyPresets -WhatIf
    ./Invoke-DefenderForOffice.ps1 -PolicyFile ./defender.lab.json -ApplyPresets
    ./Invoke-DefenderForOffice.ps1 -Hunt                                      # threat summary, last 7 days
    ./Invoke-DefenderForOffice.ps1 -Hunt -Recipient sam.demo@<lab domain> -Days 1
    ./Invoke-DefenderForOffice.ps1 -SimulationReport                          # most recent simulation
#>
[CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High', DefaultParameterSetName = 'Audit')]
param(
    [Parameter(ParameterSetName = 'Audit')][switch]$Audit,
    [Parameter(ParameterSetName = 'Apply')][switch]$ApplyPresets,
    [Parameter(ParameterSetName = 'Hunt')][switch]$Hunt,
    [Parameter(ParameterSetName = 'Sim')][switch]$SimulationReport,

    [string]$PolicyFile = (Join-Path $PSScriptRoot 'defender.json'),
    [string]$UserPrincipalName,
    [Parameter(ParameterSetName = 'Audit')][string]$InventoryFile,
    [Parameter(ParameterSetName = 'Audit')][string]$SaveInventory,
    [Parameter(ParameterSetName = 'Audit')][string]$OutFile,
    [Parameter(ParameterSetName = 'Hunt')][string]$Recipient,
    [Parameter(ParameterSetName = 'Hunt')][ValidateRange(1, 30)][int]$Days,
    [Parameter(ParameterSetName = 'Hunt')][switch]$ShowQuery,
    [Parameter(ParameterSetName = 'Sim')][string]$SimulationId,
    [Parameter(ParameterSetName = 'Sim')][string]$ReportFile
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'DefenderForOffice/DefenderForOffice.psd1') -Force
$confirmArg = @{}
if ($ConfirmPreference -eq 'None') { $confirmArg.Confirm = $false }
$config = Get-DefenderConfig -Path $PolicyFile

function Connect-ExoIfNeeded([string]$Upn) {
    if (Get-Command Get-EOPProtectionPolicyRule -ErrorAction SilentlyContinue) { return }
    if (-not (Get-Command Connect-ExchangeOnline -ErrorAction SilentlyContinue)) { throw 'Install-Module ExchangeOnlineManagement -Scope CurrentUser, then run again.' }
    if ($Upn) { Connect-ExchangeOnline -UserPrincipalName $Upn -ShowBanner:$false } else { Connect-ExchangeOnline -ShowBanner:$false }
}
function Connect-GraphIfNeeded([string[]]$Scopes) {
    if (-not (Get-Command Connect-MgGraph -ErrorAction SilentlyContinue)) { throw 'Install-Module Microsoft.Graph.Authentication -Scope CurrentUser, then run again.' }
    $ctx = Get-MgContext
    if (-not $ctx -or @($Scopes | Where-Object { $_ -notin $ctx.Scopes }).Count) { Connect-MgGraph -Scopes $Scopes -NoWelcome }
}

switch ($PSCmdlet.ParameterSetName) {
    'Audit' {
        if ($InventoryFile) { $inventory = Get-Content -LiteralPath $InventoryFile -Raw | ConvertFrom-Json }
        else { Connect-ExoIfNeeded $UserPrincipalName; $inventory = Get-DefenderInventory }
        if ($SaveInventory) { $inventory | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $SaveInventory -Encoding utf8 }
        Get-DOProtectionCoverage -Inventory $inventory | Format-Table -AutoSize
        $findings = @(Get-DefenderFinding -Inventory $inventory -Config $config)
        $findings | Sort-Object @{ e = { @{ High = 0; Medium = 1; Low = 2; Info = 3 }[$_.Severity] } }, Target |
            Format-Table Severity, Target, Rule, Detail -AutoSize -Wrap
        if ($OutFile) { ConvertTo-DefenderMarkdown -Inventory $inventory -Findings $findings | Set-Content -LiteralPath $OutFile -Encoding utf8 }
    }
    'Apply' {
        Connect-ExoIfNeeded $UserPrincipalName
        Set-DefenderPresetPolicy -Config $config -WhatIf:$WhatIfPreference @confirmArg | Format-Table -AutoSize -Wrap
    }
    'Hunt' {
        if (-not $PSBoundParameters.ContainsKey('Days')) { $Days = [int]$config.hunting.lookbackDays }
        $query = if ($Recipient) { New-DOHuntingQuery -Kind Recipient -Recipient $Recipient -Days $Days } else { New-DOHuntingQuery -Kind ThreatSummary -Days $Days }
        if ($ShowQuery) { $query; return }
        Connect-GraphIfNeeded @('ThreatHunting.Read.All')
        Invoke-DOHuntingQuery -Query $query -Days $Days | Format-Table -AutoSize -Wrap
    }
    'Sim' {
        if ($ReportFile) { $report = Get-Content -LiteralPath $ReportFile -Raw | ConvertFrom-Json }
        else { Connect-GraphIfNeeded @('AttackSimulation.Read.All'); $report = Get-DOAttackSimulationReport -SimulationId $SimulationId }
        $s = Get-DOSimulationSummary -Report $report -Config $config
        $s | Format-List Simulation, Status, Targeted, Compromised, CompromisedPct, Reported, ReportedPct
        $s.Users | Format-Table -AutoSize
        if ($s.Findings.Count) { $s.Findings | Format-Table Severity, Target, Rule, Detail -AutoSize -Wrap }
    }
}
