<#
.SYNOPSIS
Security baseline check of the lab servers: collects facts (live, read-only, over WinRM) or reads saved ones, then checks them against sec-lab.json.
.EXAMPLE
./Invoke-SecCheck.ps1 -FactsFile ./facts-before.json -OutFile ./check-before.md                 # live, from the lab host or CON-SRV02, saves the facts
.EXAMPLE
./Invoke-SecCheck.ps1 -FromFacts ../tests/fixtures/facts-bad.json -OutFile ../sample/check-bad.md
.EXAMPLE
./Invoke-SecCheck.ps1 -FromFacts ./facts-before.json -PlanOnly      # also prints the remediation plan, applies nothing
#>
[CmdletBinding()]
param(
    [string] $ConfigPath = (Join-Path $PSScriptRoot 'sec-lab.json'),
    [string] $FromFacts,
    [string] $FactsFile,
    [string] $OutFile,
    [string[]] $ComputerName,
    [pscredential] $Credential,
    [switch] $PlanOnly,
    [switch] $FailOnHigh
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'SecLab/SecLab.psd1') -Force
$config = Read-SecLabConfig -Path $ConfigPath

if ($FromFacts) { $facts = @(Get-Content -Raw -LiteralPath $FromFacts | ConvertFrom-Json) }
else {
    if (-not $ComputerName) { $ComputerName = @($config.Targets | Where-Object { -not $_.Optional } | ForEach-Object { [string]$_.Name }) }
    $facts = @(Get-SecFacts -ComputerName $ComputerName -Credential $Credential)
    if ($FactsFile) { ConvertTo-Json -InputObject $facts -Depth 8 | Set-Content -LiteralPath $FactsFile -Encoding UTF8 }
}
$findings = @($facts | ForEach-Object { Test-SecHost -Facts $_ -Config $config })
$findings | Format-Table Severity, Target, Check, Message -Wrap | Out-String -Width 200 | Write-Output
if ($OutFile) { ConvertTo-SecMarkdown -Facts $facts -Findings $findings | Set-Content -LiteralPath $OutFile -Encoding UTF8 }
if ($PlanOnly) {
    $plan = @(Get-SecRemediationPlan -Findings $findings -Config $config -Facts $facts)
    $plan | Format-Table Target, Fix, Kind, Before, Value, Why -Wrap | Out-String -Width 200 | Write-Output
}
$high = @($findings | Where-Object Severity -eq 'High').Count
Write-Output ('{0} server(s), {1} finding(s), {2} high.' -f $facts.Count, $findings.Count, $high)
if ($FailOnHigh -and $high -gt 0) { exit 1 }
