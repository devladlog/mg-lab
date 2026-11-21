<#
.SYNOPSIS
Audit of a Hyper-V host: collects facts (live, read-only) or reads saved ones, then checks them against hv-lab.json.
.EXAMPLE
./Invoke-HvAudit.ps1 -FactsFile ./host-facts.json -OutFile ./audit.md                 # live, on the Hyper-V host, saves the facts
.EXAMPLE
./Invoke-HvAudit.ps1 -FromFacts ../tests/fixtures/host-facts-lab.json -Now 2026-11-20T09:00:00Z -OutFile ../sample/audit-lab.md
#>
[CmdletBinding()]
param(
    [string] $ConfigPath = (Join-Path $PSScriptRoot 'hv-lab.json'),
    [string] $FromFacts,
    [string] $FactsFile,
    [string] $OutFile,
    [string] $ComputerName,
    [pscredential] $Credential,
    [datetime] $Now = (Get-Date),
    [switch] $FailOnHigh
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'HvLab/HvLab.psd1') -Force
$config = Read-HvLabConfig -Path $ConfigPath

if ($FromFacts) { $facts = Get-Content -Raw -LiteralPath $FromFacts | ConvertFrom-Json }
else {
    $facts = Get-HvHostFacts -ComputerName $ComputerName -Credential $Credential
    if ($FactsFile) { $facts | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $FactsFile -Encoding UTF8 }
}
$findings = @(Test-HvHost -Facts $facts -Config $config -Now $Now)
$findings | Format-Table Severity, Target, Check, Message -Wrap | Out-String -Width 200 | Write-Output
if ($OutFile) { ConvertTo-HvMarkdown -Facts $facts -Findings $findings | Set-Content -LiteralPath $OutFile -Encoding UTF8 }
$high = @($findings | Where-Object Severity -eq 'High').Count
Write-Output ('{0}: {1} VM(s), {2} finding(s), {3} high.' -f $facts.Host.ComputerName, @($facts.Vms).Count, $findings.Count, $high)
if ($FailOnHigh -and $high -gt 0) { exit 1 }
