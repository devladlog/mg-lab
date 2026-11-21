<#
.SYNOPSIS
Read-only health check for one Windows Server: disk space, automatic services, pending reboot, uptime, last hotfix.
.DESCRIPTION
Run it on the server (or through your remoting tool of choice). It changes nothing.
Hand-written reference for the episode; the AdminGate review must stay Clean on this file in ReadOnly mode.
.EXAMPLE
./Get-ServerHealth.ps1 | Format-Table
#>
[CmdletBinding()]
param(
    [ValidateRange(1, 90)] [int] $MinFreePercent = 15,
    [ValidateRange(1, 365)] [int] $MaxUptimeDays = 60,
    [ValidateRange(1, 365)] [int] $MaxHotfixAgeDays = 45,
    [datetime] $Now = (Get-Date)
)

function Get-DiskData {
    Get-Volume | Where-Object { $_.DriveType -eq 'Fixed' -and $_.DriveLetter } |
        ForEach-Object { [pscustomobject]@{ Drive = "$($_.DriveLetter):"; Size = [int64] $_.Size; Free = [int64] $_.SizeRemaining } }
}

function Get-AutoServiceData {
    Get-Service | Where-Object { $_.StartType -eq 'Automatic' } |
        ForEach-Object { [pscustomobject]@{ Name = $_.Name; Status = [string] $_.Status } }
}

function Get-PendingRebootState {
    # Component Based Servicing and Windows Update flags. PendingFileRenameOperations is ignored on purpose:
    # many applications set it, so it gives false positives.
    $cbs = Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending'
    $wu = Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired'
    [pscustomobject]@{ ComponentServicing = [bool] $cbs; WindowsUpdate = [bool] $wu }
}

function Get-BootTime {
    (Get-CimInstance -ClassName Win32_OperatingSystem).LastBootUpTime
}

function Get-LastHotfixDate {
    $latest = Get-HotFix | Where-Object { $_.InstalledOn } | Sort-Object InstalledOn -Descending | Select-Object -First 1
    if ($latest) { [datetime] $latest.InstalledOn } else { $null }
}

function Get-HealthFindings {
    <# Pure function: data in, findings out. Tested with fixture data. #>
    [CmdletBinding()]
    param(
        [object[]] $Disks = @(),
        [object[]] $Services = @(),
        $PendingReboot,
        $BootTime,
        $LastHotfix,
        [datetime] $Now,
        [int] $MinFreePercent = 15,
        [int] $MaxUptimeDays = 60,
        [int] $MaxHotfixAgeDays = 45
    )
    foreach ($d in $Disks) {
        if ($d.Size -le 0) { continue }
        $pct = [math]::Round(100 * $d.Free / $d.Size, 1)
        if ($pct -lt $MinFreePercent) {
            [pscustomobject]@{ Check = 'Disk'; Severity = 'Warning'; Detail = "$($d.Drive) has $pct % free (limit $MinFreePercent %)" }
        }
    }
    foreach ($s in $Services) {
        if ($s.Status -ne 'Running') {
            [pscustomobject]@{ Check = 'Service'; Severity = 'Info'; Detail = "$($s.Name) is set to Automatic but is $($s.Status)" }
        }
    }
    if ($PendingReboot -and ($PendingReboot.ComponentServicing -or $PendingReboot.WindowsUpdate)) {
        $why = @(); if ($PendingReboot.ComponentServicing) { $why += 'component servicing' }; if ($PendingReboot.WindowsUpdate) { $why += 'Windows Update' }
        [pscustomobject]@{ Check = 'Reboot'; Severity = 'Warning'; Detail = "Restart pending ($($why -join ', '))" }
    }
    if ($BootTime) {
        $days = [math]::Floor(($Now - $BootTime).TotalDays)
        if ($days -gt $MaxUptimeDays) {
            [pscustomobject]@{ Check = 'Uptime'; Severity = 'Info'; Detail = "Up for $days days (limit $MaxUptimeDays)" }
        }
    }
    if ($null -eq $LastHotfix) {
        [pscustomobject]@{ Check = 'Hotfix'; Severity = 'Info'; Detail = 'No hotfix with an install date found' }
    }
    else {
        $age = [math]::Floor(($Now - $LastHotfix).TotalDays)
        if ($age -gt $MaxHotfixAgeDays) {
            [pscustomobject]@{ Check = 'Hotfix'; Severity = 'Warning'; Detail = "Last hotfix is $age days old (limit $MaxHotfixAgeDays)" }
        }
    }
}

# Dot-sourcing (tests) defines the functions without running the check.
if ($MyInvocation.InvocationName -ne '.') {
    $findings = Get-HealthFindings -Disks @(Get-DiskData) -Services @(Get-AutoServiceData) `
        -PendingReboot (Get-PendingRebootState) -BootTime (Get-BootTime) -LastHotfix (Get-LastHotfixDate) `
        -Now $Now -MinFreePercent $MinFreePercent -MaxUptimeDays $MaxUptimeDays -MaxHotfixAgeDays $MaxHotfixAgeDays
    if (-not $findings) {
        [pscustomobject]@{ Check = 'All'; Severity = 'OK'; Detail = 'No findings' }
    }
    else { $findings }
}
