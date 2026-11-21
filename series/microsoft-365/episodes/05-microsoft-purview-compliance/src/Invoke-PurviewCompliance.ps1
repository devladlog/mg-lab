#Requires -Version 7.2
<#
.SYNOPSIS
    DEVLADLOG Microsoft 365 #5 - Microsoft Purview as code (labels, DLP, retention) from compliance.json.

.EXAMPLE
    # Offline: plan and audit against a saved inventory (no tenant)
    ./Invoke-PurviewCompliance.ps1 -Plan  -InventoryFile ../tests/fixtures/inventory.json
    ./Invoke-PurviewCompliance.ps1 -Audit -InventoryFile ../tests/fixtures/inventory.json -Now 2026-11-21T10:00:00Z -OutFile ../sample/purview-audit.md

.EXAMPLE
    # Lab tenant (Connect-IPPSSession first, or pass -UserPrincipalName)
    ./Invoke-PurviewCompliance.ps1 -PolicyFile ./compliance.lab.json -Plan
    ./Invoke-PurviewCompliance.ps1 -PolicyFile ./compliance.lab.json -Deploy -WhatIf
    ./Invoke-PurviewCompliance.ps1 -PolicyFile ./compliance.lab.json -Deploy
    ./Invoke-PurviewCompliance.ps1 -PolicyFile ./compliance.lab.json -Audit -OutFile ./purview-audit.md -SaveInventory ./inventory.lab.json
    ./Invoke-PurviewCompliance.ps1 -Promote -PolicyName 'Contoso - Card numbers' -Mode Enable

.EXAMPLE
    # Synthetic DLP test file (Luhn-valid numbers + keyword). Stays on the recording machine and in the lab tenant.
    ./Invoke-PurviewCompliance.ps1 -NewTestFile -TestFilePath ./contoso-dlp-test.txt -Count 12
#>
[CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High', DefaultParameterSetName = 'Plan')]
param(
    [Parameter(ParameterSetName = 'Plan')][switch]$Plan,
    [Parameter(ParameterSetName = 'Deploy')][switch]$Deploy,
    [Parameter(ParameterSetName = 'Audit')][switch]$Audit,
    [Parameter(ParameterSetName = 'Promote')][switch]$Promote,
    [Parameter(ParameterSetName = 'TestFile')][switch]$NewTestFile,

    [string]$PolicyFile = (Join-Path $PSScriptRoot 'compliance.json'),
    [Parameter(ParameterSetName = 'Plan')][Parameter(ParameterSetName = 'Audit')][string]$InventoryFile,
    [string]$UserPrincipalName,
    [Parameter(ParameterSetName = 'Audit')][string]$OutFile,
    [Parameter(ParameterSetName = 'Audit')][string]$SaveInventory,
    [Parameter(ParameterSetName = 'Audit')][datetimeoffset]$Now = [datetimeoffset]::UtcNow,
    [Parameter(ParameterSetName = 'Promote', Mandatory)][string]$PolicyName,
    [Parameter(ParameterSetName = 'Promote')][ValidateSet('Enable', 'Disable', 'TestWithNotifications', 'TestWithoutNotifications')][string]$Mode = 'Enable',
    [Parameter(ParameterSetName = 'TestFile')][string]$TestFilePath = './contoso-dlp-test.txt',
    [Parameter(ParameterSetName = 'TestFile')][int]$Count = 12
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'PurviewCompliance/PurviewCompliance.psd1') -Force
# -WhatIf / -Confirm:$false given to this script are passed on explicitly (preferences don't cross into the module).
$confirmArg = @{}
if ($ConfirmPreference -eq 'None') { $confirmArg.Confirm = $false }

function Connect-PurviewIfNeeded([string]$Upn) {
    if (Get-Command Get-DlpCompliancePolicy -ErrorAction SilentlyContinue) { return }
    if (-not (Get-Command Connect-IPPSSession -ErrorAction SilentlyContinue)) {
        throw 'Security & Compliance PowerShell is not connected and ExchangeOnlineManagement is not installed (Install-Module ExchangeOnlineManagement -Scope CurrentUser).'
    }
    if ($Upn) { Connect-IPPSSession -UserPrincipalName $Upn -ShowBanner:$false } else { Connect-IPPSSession -ShowBanner:$false }
}

if ($NewTestFile) {
    $lines = New-DlpTestContent -Count $Count
    Set-Content -LiteralPath $TestFilePath -Value $lines -Encoding utf8
    Write-Information -InformationAction Continue "Wrote $Count synthetic card numbers to $TestFilePath (lab tenant only; delete after the demo)."
    return
}

if ($Promote) {
    Connect-PurviewIfNeeded $UserPrincipalName
    Set-PurviewDlpMode -Name $PolicyName -Mode $Mode -WhatIf:$WhatIfPreference @confirmArg
    return
}

$config = Get-PurviewConfig -Path $PolicyFile
if ($InventoryFile) { $inventory = Get-Content -LiteralPath $InventoryFile -Raw | ConvertFrom-Json }
else { Connect-PurviewIfNeeded $UserPrincipalName; $inventory = Get-PurviewInventory }

if ($Plan -or $PSCmdlet.ParameterSetName -eq 'Plan') {
    Get-PurviewPlan -Config $config -Inventory $inventory | Format-Table Kind, Name, Action, Cmdlet, Detail -AutoSize -Wrap
    return
}

if ($Deploy) {
    $steps = @(Get-PurviewPlan -Config $config -Inventory $inventory)
    Invoke-PurviewPlan -Plan $steps -WhatIf:$WhatIfPreference @confirmArg | Format-Table Kind, Name, Result, Detail -AutoSize -Wrap
    if (-not $WhatIfPreference) { Write-Information -InformationAction Continue 'Labels and label policies: allow up to 24 hours. DLP: about an hour. Retention labels: up to 7 days.' }
    return
}

if ($Audit) {
    if ($SaveInventory) { $inventory | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $SaveInventory -Encoding utf8 }
    $findings = @(Get-PurviewFinding -Inventory $inventory -Config $config -Now $Now)
    $findings | Sort-Object @{ e = { @{ High = 0; Medium = 1; Low = 2; Info = 3 }[$_.Severity] } }, Target |
        Format-Table Severity, Target, Rule, Detail -AutoSize -Wrap
    if ($OutFile) { ConvertTo-PurviewMarkdown -Inventory $inventory -Findings $findings -Now $Now | Set-Content -LiteralPath $OutFile -Encoding utf8 }
}
