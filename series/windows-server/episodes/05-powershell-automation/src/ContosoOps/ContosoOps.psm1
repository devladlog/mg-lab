#Requires -Version 5.1
<#
    ContosoOps: the functions a JEA session on the app server exposes (VisibleFunctions).
    Deployed by Install-OpsEndpoint to "$env:ProgramFiles\WindowsPowerShell\Modules\ContosoOps",
    next to the RoleCapabilities folder. Runs inside Windows PowerShell 5.1 on the target.

    JEA sessions have no providers and run in NoLanguage mode; these functions do the
    file system and CIM work on the user's behalf, with their own validation.
#>
Set-StrictMode -Version 3.0

$script:Settings = [pscustomobject]@{
    WatchedServices = @('W3SVC', 'WAS')
    LogRoot         = 'C:\inetpub\logs\LogFiles'
}

function Set-OpsSetting {
    <# Loads ContosoOps.settings.json (written by Install-OpsEndpoint). Not visible in JEA. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [string] $Path)
    $json = Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json
    if ($json.PSObject.Properties['WatchedServices']) { $script:Settings.WatchedServices = @($json.WatchedServices) }
    if ($json.PSObject.Properties['LogRoot']) { $script:Settings.LogRoot = [string]$json.LogRoot }
}

$settingsFile = Join-Path $PSScriptRoot 'ContosoOps.settings.json'
if (Test-Path -LiteralPath $settingsFile) { Set-OpsSetting -Path $settingsFile }

function Get-OpsFolderStat {
    param([string] $Root, [datetime] $OlderThan)
    $files = @(Get-ChildItem -LiteralPath $Root -Recurse -File -Filter '*.log' -ErrorAction SilentlyContinue)
    $old = @($files | Where-Object { $_.LastWriteTime -lt $OlderThan })
    $total = ($files | Measure-Object -Property Length -Sum).Sum
    $oldBytes = ($old | Measure-Object -Property Length -Sum).Sum
    if (-not $total) { $total = 0 }
    if (-not $oldBytes) { $oldBytes = 0 }
    [pscustomobject]@{ Files = $files.Count; Bytes = [long]$total; OldFiles = $old; OldBytes = [long]$oldBytes }
}

function Get-OpsHealth {
    <#
    .SYNOPSIS
    Health facts for the operations runbook: uptime, system disk, watched services, reboot signals, log folder size.
    #>
    [CmdletBinding()]
    [OutputType([pscustomobject])]
    param()

    $os = Get-CimInstance -ClassName Win32_OperatingSystem
    $disk = Get-CimInstance -ClassName Win32_LogicalDisk -Filter ("DeviceID='{0}'" -f $os.SystemDrive)
    $freePercent = 0
    if ($disk.Size -gt 0) { $freePercent = [math]::Round(100 * $disk.FreeSpace / $disk.Size, 1) }

    $services = foreach ($name in $script:Settings.WatchedServices) {
        $svc = Get-Service -Name $name -ErrorAction SilentlyContinue
        $status = 'Missing'
        if ($svc) { $status = [string]$svc.Status }
        [pscustomobject]@{ Name = $name; Status = $status }
    }

    $cbs = Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending'
    $wu = Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired'
    $logs = Get-OpsFolderStat -Root $script:Settings.LogRoot -OlderThan ([datetime]::MaxValue)

    [pscustomobject]@{
        ComputerName      = $env:COMPUTERNAME
        CollectedUtc      = (Get-Date).ToUniversalTime().ToString('o')
        UptimeDays        = [math]::Round(((Get-Date) - $os.LastBootUpTime).TotalDays, 1)
        SystemFreePercent = $freePercent
        Services          = @($services)
        RebootPending     = [bool]($cbs -or $wu)
        LogRoot           = $script:Settings.LogRoot
        LogFolderMB       = [math]::Round($logs.Bytes / 1MB, 1)
    }
}

function Clear-OpsLogFolder {
    <#
    .SYNOPSIS
    Deletes *.log files older than N days under the configured log root (never anywhere else).
    .PARAMETER OlderThanDays
    7 to 365. A JEA user can't pick the folder, only the age.
    #>
    [CmdletBinding(SupportsShouldProcess)]
    [OutputType([pscustomobject])]
    param(
        [ValidateRange(7, 365)]
        [int] $OlderThanDays = 30
    )

    $root = $script:Settings.LogRoot
    $cutoff = (Get-Date).AddDays(-$OlderThanDays)
    $stat = Get-OpsFolderStat -Root $root -OlderThan $cutoff
    $removed = 0
    [long]$freed = 0
    foreach ($file in $stat.OldFiles) {
        if ($PSCmdlet.ShouldProcess($file.FullName, 'Delete log file')) {
            Remove-Item -LiteralPath $file.FullName -Force
            $removed++
            $freed += $file.Length
        }
    }
    [pscustomobject]@{
        ComputerName  = $env:COMPUTERNAME
        LogRoot       = $root
        OlderThanDays = $OlderThanDays
        Candidates    = @($stat.OldFiles).Count
        FilesRemoved  = $removed
        MBFreed       = [math]::Round($freed / 1MB, 1)
    }
}

Export-ModuleMember -Function Get-OpsHealth, Clear-OpsLogFolder, Set-OpsSetting
