<#
.SYNOPSIS
Certificate check for the lab: machine certificates on every server, the enterprise CA (service, CA certificate, CRL, distribution points) and the templates it publishes. Read-only.
.EXAMPLE
./Invoke-CertCheck.ps1 -FactsFile ./facts-before.json -OutFile ./check-before.md -PlanOnly     # live, from CON-SRV02, saves the facts
.EXAMPLE
./Invoke-CertCheck.ps1 -FromFacts ../tests/fixtures/facts-bad.json -Now 2026-11-21T09:00:00Z -OutFile ../sample/check-bad.md
#>
[CmdletBinding()]
param(
    [string] $ConfigPath = (Join-Path $PSScriptRoot 'cert-lab.json'),
    [string] $FromFacts,
    [string] $FactsFile,
    [string] $OutFile,
    [string[]] $ComputerName,
    [string] $CaServer,
    [pscredential] $Credential,
    [datetime] $Now = [datetime]::UtcNow,
    [switch] $PlanOnly,
    [switch] $FailOnHigh
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'CertLab/CertLab.psd1') -Force
$config = Read-CertLabConfig -Path $ConfigPath

if ($FromFacts) { $facts = Get-Content -Raw -LiteralPath $FromFacts | ConvertFrom-Json }
else {
    if (-not $ComputerName) { $ComputerName = @($config.Targets | ForEach-Object { [string]$_.Name }) }
    if (-not $CaServer) { $CaServer = [string]$config.Ca.Server }
    $facts = Get-CertFacts -ComputerName $ComputerName -CaServer $CaServer -Credential $Credential
    if ($FactsFile) { ConvertTo-Json -InputObject $facts -Depth 10 | Set-Content -LiteralPath $FactsFile -Encoding UTF8 }
}
$hosts = @($facts.Hosts)
$findings = @()
foreach ($h in $hosts) { $findings += @(Test-CertHost -Facts $h -Config $config -Now $Now) }
if ($facts.Ca) { $findings += @(Test-CaFacts -CaFacts $facts.Ca -Config $config -Now $Now) }
$findings = @($findings | Sort-Object @{ Expression = { @{ High = 0; Medium = 1; Low = 2; Info = 3 }[$_.Severity] } }, Target, Check)
$findings | Format-Table Severity, Target, Check, Message -Wrap | Out-String -Width 200 | Write-Output
if ($OutFile) { ConvertTo-CertMarkdown -Hosts $hosts -Ca $facts.Ca -Findings $findings -Now $Now | Set-Content -LiteralPath $OutFile -Encoding UTF8 }
if ($PlanOnly) {
    $plan = @(Get-CertRenewalPlan -Hosts $hosts -Findings $findings -Now $Now)
    if ($plan.Count) { $plan | Format-Table Target, Kind, DaysLeft, Template, Subject, Why -Wrap | Out-String -Width 200 | Write-Output }
    else { Write-Output 'Renewal plan: nothing expires soon.' }
}
$high = @($findings | Where-Object Severity -eq 'High').Count
Write-Output ('{0} server(s), {1} finding(s), {2} high.' -f $hosts.Count, $findings.Count, $high)
if ($FailOnHigh -and $high -gt 0) { exit 1 }
