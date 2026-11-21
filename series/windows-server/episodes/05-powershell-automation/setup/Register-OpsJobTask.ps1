#Requires -Version 5.1
<#
.SYNOPSIS
Installs the runbook on the job host (CON-SRV02) and registers a scheduled task that runs it as the gMSA.
Run on CON-SRV02, elevated, in Windows PowerShell 5.1, from the episode's src folder.

.DESCRIPTION
1. RSAT AD PowerShell (for Install-/Test-ADServiceAccount), Install-ADServiceAccount, Test-ADServiceAccount must be True
2. Copies OpsLab, Invoke-OpsMaintenance.ps1 and ops-job.json to C:\OpsJob; the gMSA can only write to C:\OpsJob\logs
3. Registers "\Contoso\OpsJob": every 15 minutes, powershell.exe -File ..., principal = gMSA with LogonType Password
   (no password is stored: Windows retrieves the managed password), one instance at a time, 10-minute limit

.EXAMPLE
.\Register-OpsJobTask.ps1 -WhatIf
.\Register-OpsJobTask.ps1
.\Register-OpsJobTask.ps1 -Remove
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [string] $GmsaName = 'gmsa-opsjob',
    [string] $Domain = 'CONTOSO',
    [string] $SourcePath = (Join-Path $PSScriptRoot '..\src'),
    [string] $InstallPath = 'C:\OpsJob',
    [string] $TaskPath = '\Contoso\',
    [string] $TaskName = 'OpsJob',
    [int] $EveryMinutes = 15,
    [switch] $Remove
)
$ErrorActionPreference = 'Stop'
$principalName = "$Domain\$GmsaName`$"

if ($Remove) {
    if ((Get-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -ErrorAction SilentlyContinue) -and $PSCmdlet.ShouldProcess("$TaskPath$TaskName", 'Unregister task')) {
        Unregister-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -Confirm:$false
    }
    if ((Test-Path $InstallPath) -and $PSCmdlet.ShouldProcess($InstallPath, 'Remove folder')) { Remove-Item $InstallPath -Recurse -Force }
    if ((Get-Command Uninstall-ADServiceAccount -ErrorAction SilentlyContinue) -and $PSCmdlet.ShouldProcess($GmsaName, 'Uninstall-ADServiceAccount')) {
        Uninstall-ADServiceAccount -Identity $GmsaName
    }
    return
}

# 1. gMSA on this host
if (-not (Get-Command Install-ADServiceAccount -ErrorAction SilentlyContinue)) {
    if ($PSCmdlet.ShouldProcess($env:COMPUTERNAME, 'Install-WindowsFeature RSAT-AD-PowerShell')) {
        Install-WindowsFeature RSAT-AD-PowerShell | Out-Null
    }
}
if ($PSCmdlet.ShouldProcess($GmsaName, 'Install-ADServiceAccount')) {
    Install-ADServiceAccount -Identity $GmsaName
    if (-not (Test-ADServiceAccount -Identity $GmsaName)) {
        throw "Test-ADServiceAccount $GmsaName returned False: is $env:COMPUTERNAME in PrincipalsAllowedToRetrieveManagedPassword?"
    }
}

# 2. Files: admins write the code, the gMSA writes only logs
if ($PSCmdlet.ShouldProcess($InstallPath, 'Copy runbook')) {
    New-Item -ItemType Directory -Path (Join-Path $InstallPath 'logs') -Force | Out-Null
    Copy-Item -Path (Join-Path $SourcePath 'OpsLab') -Destination $InstallPath -Recurse -Force
    Copy-Item -Path (Join-Path $SourcePath 'Invoke-OpsMaintenance.ps1'), (Join-Path $SourcePath 'ops-job.json') -Destination $InstallPath -Force
    & icacls.exe (Join-Path $InstallPath 'logs') /grant "${principalName}:(OI)(CI)M" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "icacls failed (exit $LASTEXITCODE)." }
}

# 3. The task
$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument ('-NoProfile -NonInteractive -File "{0}"' -f (Join-Path $InstallPath 'Invoke-OpsMaintenance.ps1')) `
    -WorkingDirectory $InstallPath
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes $EveryMinutes)
$principal = New-ScheduledTaskPrincipal -UserId $principalName -LogonType Password -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -StartWhenAvailable

if ($PSCmdlet.ShouldProcess("$TaskPath$TaskName", "Register-ScheduledTask as $principalName")) {
    Register-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal `
        -Settings $settings -Description 'DEVLADLOG Windows Server #5: app server runbook via JEA (Contoso.AppOps)' -Force |
        Select-Object TaskPath, TaskName, State, @{ n = 'RunAs'; e = { $_.Principal.UserId } }
}
