<#
.SYNOPSIS
    The whole gate in one command: PSScriptAnalyzer first, then the Pester tests. Exit code 1 if anything fails.
.EXAMPLE
    pwsh -NoProfile -File ./build.ps1
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$InformationPreference = 'Continue'

Write-Information '== PSScriptAnalyzer (Warning and Error fail the build)'
$settings = Join-Path $PSScriptRoot 'PSScriptAnalyzerSettings.psd1'
$findings = @(Invoke-ScriptAnalyzer -Path (Join-Path $PSScriptRoot 'src') -Recurse -Settings $settings) +
@(Invoke-ScriptAnalyzer -Path (Join-Path $PSScriptRoot 'build.ps1') -Settings $settings)
Write-Information "   findings: $($findings.Count)"
if ($findings.Count -gt 0) {
    $findings | Format-Table RuleName, Severity, ScriptName, Line -AutoSize | Out-String -Width 160 | Write-Information
    exit 1
}

Write-Information '== Pester'
$configuration = New-PesterConfiguration
$configuration.Run.Path = Join-Path $PSScriptRoot 'tests'
$configuration.Run.PassThru = $true
$configuration.Output.Verbosity = 'Normal'
$result = Invoke-Pester -Configuration $configuration
if ($result.FailedCount -gt 0) { exit 1 }
