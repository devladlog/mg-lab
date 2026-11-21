<#
.SYNOPSIS
Server Core check for the lab: Core or Desktop Experience on each server, footprint, remote management, the App Compatibility FOD. Optionally checks Dockerfiles that use the Nano Server base image. Read-only.
.EXAMPLE
./Invoke-CoreCheck.ps1 -FactsFile ./facts-before.json -OutFile ./check-before.md -PlanOnly      # live, from CON-SRV02, saves the facts
.EXAMPLE
./Invoke-CoreCheck.ps1 -FromFacts ../tests/fixtures/facts-bad.json -OutFile ../sample/check-bad.md
.EXAMPLE
./Invoke-CoreCheck.ps1 -FromFacts ../tests/fixtures/facts-after.json -Dockerfile ../tests/fixtures/Dockerfile.nano-bad
#>
[CmdletBinding()]
param(
    [string] $ConfigPath = (Join-Path $PSScriptRoot 'core-lab.json'),
    [string] $FromFacts,
    [string] $FactsFile,
    [string] $OutFile,
    [string[]] $ComputerName,
    [pscredential] $Credential,
    [string[]] $Dockerfile,
    [switch] $PlanOnly,
    [switch] $FailOnHigh
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'CoreLab/CoreLab.psd1') -Force
$config = Read-CoreLabConfig -Path $ConfigPath

if ($FromFacts) { $facts = Get-Content -Raw -LiteralPath $FromFacts | ConvertFrom-Json }
else {
    if (-not $ComputerName) { $ComputerName = @($config.Targets | ForEach-Object { [string]$_.Name }) }
    $facts = [pscustomobject]@{ Hosts = @(Get-CoreFacts -ComputerName $ComputerName -Credential $Credential) }
    if ($FactsFile) { ConvertTo-Json -InputObject $facts -Depth 10 | Set-Content -LiteralPath $FactsFile -Encoding UTF8 }
}
$hosts = @($facts.Hosts)
$findings = @()
foreach ($h in $hosts) { $findings += @(Test-CoreHost -Facts $h -Config $config) }
foreach ($d in @($Dockerfile)) {
    if ($d) { $findings += @(Test-NanoDockerfile -Content (Get-Content -Raw -LiteralPath $d) -Name (Split-Path -Leaf $d) -Config $config) }
}
$findings = @($findings | Sort-Object @{ Expression = { @{ High = 0; Medium = 1; Low = 2; Info = 3 }[$_.Severity] } }, Target, Check)
$findings | Format-Table Severity, Target, Check, Message -Wrap | Out-String -Width 200 | Write-Output
if ($OutFile) { ConvertTo-CoreMarkdown -Hosts $hosts -Findings $findings | Set-Content -LiteralPath $OutFile -Encoding UTF8 }
if ($PlanOnly) {
    $plan = @(Get-CoreSetupPlan -Hosts $hosts -Config $config)
    if ($plan.Count) { $plan | Format-Table Target, Id, Kind, NeedsSwitch, Description -Wrap | Out-String -Width 200 | Write-Output }
    else { Write-Output 'Setup plan: nothing to do.' }
}
$high = @($findings | Where-Object Severity -eq 'High').Count
Write-Output ('{0} server(s), {1} finding(s), {2} high.' -f $hosts.Count, $findings.Count, $high)
if ($FailOnHigh -and $high -gt 0) { exit 1 }
