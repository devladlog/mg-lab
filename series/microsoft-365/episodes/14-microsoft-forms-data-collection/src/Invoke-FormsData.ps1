#Requires -Version 7.2
<#
.SYNOPSIS
    Runner for DEVLADLOG Microsoft 365 #14 (Microsoft Forms data collection).
.EXAMPLE
    ./Invoke-FormsData.ps1 -Validate                                  # offline: check form.json
    ./Invoke-FormsData.ps1 -FlowMap                                   # offline: question -> column -> flow value
    ./Invoke-FormsData.ps1 -ListBody                                  # offline: the Graph body that creates the list
    ./Invoke-FormsData.ps1 -Provision -WhatIf                         # Graph: Sites.Read.All + Sites.Manage.All
    ./Invoke-FormsData.ps1 -Analyze [-ItemsFile saved.json]           # Graph: Sites.Read.All
#>
[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSAvoidUsingWriteHost', '', Justification = 'Console runner')]
[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSReviewUnusedParameter', 'OutFile', Justification = 'Used by Write-Out')]
[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$SpecFile = (Join-Path $PSScriptRoot 'form.json'),
    [switch]$Validate,
    [switch]$FlowMap,
    [switch]$ListBody,
    [switch]$Provision,
    [switch]$Analyze,
    [string]$ItemsFile,
    [string]$OutFile,
    [datetimeoffset]$Now = [datetimeoffset]::UtcNow
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'FormsData/FormsData.psd1') -Force

function Write-Out([string]$Text) { if ($OutFile) { Set-Content -Path $OutFile -Value $Text -Encoding utf8; Write-Host "Wrote $OutFile" } else { $Text } }

$spec = Get-FDSpec -Path $SpecFile
if ($Validate) { Write-Host "OK: $SpecFile ($(@($spec.questions).Count) questions, list '$($spec.list.displayName)')." }
elseif ($FlowMap) { Get-FDFlowMap -Spec $spec | Format-Table -AutoSize -Wrap | Out-String -Width 200 | Write-Host }
elseif ($ListBody) { Write-Out ((ConvertTo-FDListBody -Spec $spec) | ConvertTo-Json -Depth 10) }
elseif ($Provision) { Set-FDList -Spec $spec | Format-List | Out-String -Width 200 | Write-Host }
elseif ($Analyze) {
    $items = if ($ItemsFile) { @(Get-FDResponse -Path $ItemsFile) } else { @(Get-FDResponse -SiteUrl $spec.site.url -ListName $spec.list.displayName) }
    $summary = Get-FDSummary -Items $items -Spec $spec
    $findings = @(Get-FDResponseFinding -Items $items -Spec $spec)
    Write-Out (ConvertTo-FDMarkdown -Title "Forms responses: $($spec.form.title)" -Summary $summary -Findings $findings -Asof $Now.ToString('u'))
}
else { Get-Help $PSCommandPath -Examples | Out-String | Write-Host }
