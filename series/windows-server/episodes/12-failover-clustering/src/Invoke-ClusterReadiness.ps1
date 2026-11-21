<#
.SYNOPSIS
Failover cluster readiness check: collects facts from the nodes (live, read-only, over WinRM) or reads saved ones, then checks them against cluster-lab.json.
.EXAMPLE
./Invoke-ClusterReadiness.ps1 -FactsFile ./facts-before.json -OutFile ./ready-before.md -PlanOnly     # live, saves the facts, prints the build plan
.EXAMPLE
./Invoke-ClusterReadiness.ps1 -FromFacts ../tests/fixtures/facts-bad.json -OutFile ../sample/ready-bad.md
#>
[CmdletBinding()]
param(
    [string] $ConfigPath = (Join-Path $PSScriptRoot 'cluster-lab.json'),
    [string] $FromFacts,
    [string] $FactsFile,
    [string] $OutFile,
    [pscredential] $Credential,
    [switch] $PlanOnly,
    [switch] $FailOnHigh
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'ClusterLab/ClusterLab.psd1') -Force
$config = Read-ClfLabConfig -Path $ConfigPath

if ($FromFacts) { $facts = Get-Content -Raw -LiteralPath $FromFacts | ConvertFrom-Json }
else {
    $facts = Get-ClfFacts -Config $config -Credential $Credential
    if ($FactsFile) { ConvertTo-Json -InputObject $facts -Depth 8 | Set-Content -LiteralPath $FactsFile -Encoding UTF8 }
}
$findings = @(Test-ClfReadiness -Facts $facts -Config $config)
$findings | Format-Table Severity, Target, Check, Message -Wrap | Out-String -Width 200 | Write-Output
if ($OutFile) { ConvertTo-ClfMarkdown -Facts $facts -Findings $findings | Set-Content -LiteralPath $OutFile -Encoding UTF8 }
if ($PlanOnly) {
    $plan = @(Get-ClfBuildPlan -Config $config -Facts $facts)
    $plan | Format-Table Order, Id, Cmdlet, LocalOnly, CreatesAdObjects, Why -Wrap | Out-String -Width 220 | Write-Output
}
$high = @($findings | Where-Object Severity -eq 'High').Count
Write-Output ('{0} node(s), {1} finding(s), {2} high.' -f @($facts.Nodes).Count, $findings.Count, $high)
if ($FailOnHigh -and $high -gt 0) { exit 1 }
