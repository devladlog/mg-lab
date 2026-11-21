#requires -Version 7.2
<#
.SYNOPSIS
    Run ON THE GATEWAY MACHINE before (and after) installing the gateway: can it reach what the gateway needs?
.DESCRIPTION
    Opens outbound TCP connections to the fixed-name endpoints of Learn's "Adjust communication settings for the on-premises data
    gateway" and to the data sources the gateway will read. The *.servicebus.windows.net ports (5671-5672, 443, 9350-9354) have no
    fixed host name: Learn says to run Diagnostics > Network ports test in the gateway app for those, and this script reminds you.
    Exit code 1 when anything is unreachable. Nothing is changed on the machine.
.EXAMPLE
    ./Test-GatewayHost.ps1 -DataSource 10.50.0.30:1433
#>
[CmdletBinding()]
param(
    [string[]] $DataSource = @('10.50.0.30:1433'),
    [int] $TimeoutMs = 3000
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'GatewayOps' 'GatewayOps.psd1')

Write-Host "Machine: $env:COMPUTERNAME"
$results = @(Test-GatewayNetwork -DataSource $DataSource -TimeoutMs $TimeoutMs)
$results | Format-Table Kind, Host, Port, Reachable, Ms, Error -AutoSize | Out-String -Width 160 | Write-Host

$bad = @($results | Where-Object { -not $_.Reachable })
Write-Host ('{0} endpoint(s) tested, {1} unreachable.' -f $results.Count, $bad.Count)
Write-Host 'Not testable by name: *.servicebus.windows.net (5671-5672, 443, 9350-9354). In the gateway app: Diagnostics > Network ports test > Start new test.'
if ($bad.Count) { exit 1 }
