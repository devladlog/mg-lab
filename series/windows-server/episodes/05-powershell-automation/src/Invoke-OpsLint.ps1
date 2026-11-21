<#
.SYNOPSIS
Lints a JEA definition before it is registered: per role, per group after merging roles, and the session.
.EXAMPLE
./Invoke-OpsLint.ps1 -DefinitionPath ./jea-definition.json -OutFile ./lint.md -FailOnHigh
#>
[CmdletBinding()]
param(
    [string] $DefinitionPath = (Join-Path $PSScriptRoot 'jea-definition.json'),
    [string] $FunctionsModulePath = (Join-Path $PSScriptRoot 'ContosoOps/ContosoOps.psm1'),
    [string] $OutFile,
    [switch] $FailOnHigh
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'OpsLab/OpsLab.psd1') -Force

$def = Read-OpsEndpointDefinition -Path $DefinitionPath
$findings = @(Test-OpsEndpointDefinition -Definition $def -ModulePath $FunctionsModulePath)
$findings | Format-Table Severity, Scope, Check, Message -Wrap | Out-String -Width 200 | Write-Output
if ($OutFile) { ConvertTo-OpsLintMarkdown -Definition $def -Findings $findings | Set-Content -LiteralPath $OutFile -Encoding UTF8 }

$high = @($findings | Where-Object Severity -eq 'High').Count
Write-Output ("{0}: {1} finding(s), {2} high." -f $def.EndpointName, $findings.Count, $high)
if ($FailOnHigh -and $high -gt 0) { exit 1 }
