<#
.SYNOPSIS
The runbook the scheduled task runs (as the gMSA, in Windows PowerShell 5.1). It can only do what the
Contoso.AppOps JEA endpoint allows: read health, restart W3SVC/WAS, trim old IIS logs.
.EXAMPLE
powershell.exe -NoProfile -NonInteractive -File C:\OpsJob\Invoke-OpsMaintenance.ps1
.EXAMPLE
./Invoke-OpsMaintenance.ps1 -HealthFile ../tests/fixtures/health-con-srv01.json -LogDirectory ./logs   # offline: decide only
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [string] $ConfigPath = (Join-Path $PSScriptRoot 'ops-job.json'),
    [string] $LogDirectory,
    [string] $HealthFile,
    [datetime] $Now = (Get-Date)
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'OpsLab/OpsLab.psd1') -Force

$config = Read-OpsJobConfig -Path $ConfigPath
if ($LogDirectory) { $config.LogDirectory = $LogDirectory }

$run = Invoke-OpsMaintenanceRun -Config $config -Now $Now -HealthFile $HealthFile -WhatIf:$WhatIfPreference
foreach ($r in $run.Results) {
    foreach ($a in $r.Actions) { Write-Output ("{0}  {1,-15} {2,-28} {3}  {4}" -f $r.ComputerName, $a.Action, $a.Target, $a.Outcome, $a.Detail) }
    foreach ($a in $r.Alerts) { Write-Output ("{0}  {1,-15} {2,-28} {3}" -f $r.ComputerName, "ALERT $($a.Severity)", $a.Check, $a.Message) }
}
Write-Output ("Run {0}: exit code {1}" -f $run.RunId, $run.ExitCode)
exit $run.ExitCode
