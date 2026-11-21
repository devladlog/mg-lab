<#
.SYNOPSIS
Remote Desktop Services check: collects facts (live, read-only, over WinRM) or reads saved ones, then checks them against rds-lab.json.
.EXAMPLE
./Invoke-RdsCheck.ps1 -FactsFile ./facts-before.json -OutFile ./check-before.md -PlanOnly     # live, saves the facts, prints the plan
.EXAMPLE
./Invoke-RdsCheck.ps1 -FromFacts ../tests/fixtures/facts-bad.json -OutFile ../sample/check-bad.md
#>
[CmdletBinding()]
param(
    [string] $ConfigPath = (Join-Path $PSScriptRoot 'rds-lab.json'),
    [string] $FromFacts,
    [string] $FactsFile,
    [string] $OutFile,
    [pscredential] $Credential,
    [switch] $PlanOnly,
    [switch] $FailOnHigh,
    [datetime] $Now = (Get-Date).ToUniversalTime()
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'RdsLab/RdsLab.psd1') -Force
$config = Read-RdsLabConfig -Path $ConfigPath

if ($FromFacts) { $facts = Get-Content -Raw -LiteralPath $FromFacts | ConvertFrom-Json }
else {
    $facts = Get-RdsFacts -Config $config -Credential $Credential
    if ($FactsFile) { ConvertTo-Json -InputObject $facts -Depth 8 | Set-Content -LiteralPath $FactsFile -Encoding UTF8 }
}
$findings = @(Test-RdsDeployment -Facts $facts -Config $config -Now $Now)
$findings | Format-Table Severity, Target, Check, Message -Wrap | Out-String -Width 200 | Write-Output
if ($OutFile) { ConvertTo-RdsMarkdown -Facts $facts -Findings $findings | Set-Content -LiteralPath $OutFile -Encoding UTF8 }
if ($PlanOnly) {
    $plan = @(Get-RdsDeploymentPlan -Config $config -Facts $facts)
    $plan | Format-Table Order, Id, Cmdlet, Disruptive, Why -Wrap | Out-String -Width 200 | Write-Output
}
$sessions = @(Get-RdsSessionSummary -Sessions @($facts.Sessions))
if ($sessions.Count) { $sessions | Format-Table HostServer, Total, Active, Disconnected, Users | Out-String -Width 200 | Write-Output }
$high = @($findings | Where-Object Severity -eq 'High').Count
Write-Output ('{0} finding(s), {1} high.' -f $findings.Count, $high)
if ($FailOnHigh -and $high -gt 0) { exit 1 }
