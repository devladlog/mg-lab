<#
.SYNOPSIS
Preflight for a Windows Admin Center gateway: collects facts on the gateway (live) or reads saved ones, then checks them.
.EXAMPLE
./Invoke-WacPreflight.ps1 -FactsFile ./gateway-facts.json -OutFile ./preflight.md          # live, saves the facts
.EXAMPLE
./Invoke-WacPreflight.ps1 -FromFacts ../tests/fixtures/facts-con-srv02.json -OutFile ../sample/preflight.md
#>
[CmdletBinding()]
param(
    [string] $ConfigPath = (Join-Path $PSScriptRoot 'wac-lab.json'),
    [string] $FromFacts,
    [string] $FactsFile,
    [string] $OutFile,
    [datetime] $Now = (Get-Date),
    [pscredential] $Credential,
    [switch] $FailOnHigh
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'WacLab/WacLab.psd1') -Force
$config = Read-WacLabConfig -Path $ConfigPath

if ($FromFacts) { $facts = Get-Content -Raw -LiteralPath $FromFacts | ConvertFrom-Json }
else {
    $facts = Get-WacGatewayFacts -Config $config -Credential $Credential
    if ($FactsFile) { $facts | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $FactsFile -Encoding UTF8 }
}
$findings = @(Test-WacGateway -Facts $facts -Config $config -Now $Now)
$findings | Format-Table Severity, Target, Check, Message -Wrap | Out-String -Width 200 | Write-Output
if ($OutFile) { ConvertTo-WacMarkdown -Facts $facts -Config $config -Findings $findings | Set-Content -LiteralPath $OutFile -Encoding UTF8 }
$high = @($findings | Where-Object Severity -eq 'High').Count
Write-Output ('{0}: {1} node(s), {2} finding(s), {3} high.' -f $facts.Gateway.ComputerName, @($config.Nodes).Count, $findings.Count, $high)
if ($FailOnHigh -and $high -gt 0) { exit 1 }
