#Requires -Version 7.2
<#
  DEVLADLOG Windows Server #1 - ServerBaseline
  Collect a snapshot from each Windows Server (PowerShell remoting), then check it against a baseline file.

  Two halves, on purpose:
    * The collector is a script block that runs ON the server. Remote sessions land in the Windows PowerShell 5.1
      endpoint (Microsoft.PowerShell) by default, so the collector must stay 5.1-safe: no ??, ?., ternary, && or ||.
      A Pester test parses it and fails the build if one slips in.
    * Everything else (Test-SbBaseline, ConvertTo-SbMarkdown) is pure: snapshot in, findings out. It runs anywhere,
      including Linux, and is what the unit tests cover.
#>

$script:SeverityOrder = @{ High = 0; Medium = 1; Low = 2; Info = 3 }

# ---------------------------------------------------------------------------------------------------------------
# Collector (runs on the target server, Windows PowerShell 5.1 or PowerShell 7)
# ---------------------------------------------------------------------------------------------------------------
$script:Collector = {
    $ErrorActionPreference = 'Stop'

    function ConvertTo-IsoUtc($value) {
        if ($null -eq $value) { return $null }
        ([datetime]$value).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    }

    $os = Get-CimInstance -ClassName Win32_OperatingSystem
    $cs = Get-CimInstance -ClassName Win32_ComputerSystem
    $cv = Get-ItemProperty -Path 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion'

    $disks = @(Get-CimInstance -ClassName Win32_LogicalDisk -Filter 'DriveType=3' | ForEach-Object {
        [pscustomobject]@{
            Drive  = $_.DeviceID
            SizeGB = [math]::Round($_.Size / 1GB, 1)
            FreeGB = [math]::Round($_.FreeSpace / 1GB, 1)
        }
    })

    # Automatic services that are not running. Trigger-start services are not exposed by Win32_Service,
    # which is why the baseline has an ignore list.
    $autoNotRunning = @(Get-CimInstance -ClassName Win32_Service -Filter "StartMode='Auto' AND State<>'Running'" |
        ForEach-Object { [pscustomobject]@{ Name = $_.Name; DisplayName = $_.DisplayName; State = $_.State } })

    $features = @()
    if (Get-Command -Name Get-WindowsFeature -ErrorAction SilentlyContinue) {
        $features = @(Get-WindowsFeature | Where-Object { $_.Installed } | ForEach-Object { $_.Name })
    }

    # Get-HotFix reads Win32_QuickFixEngineering: Component Based Servicing updates only (see README gotchas).
    $hotfixes = @(Get-HotFix | ForEach-Object {
        [pscustomobject]@{ Id = $_.HotFixID; Description = $_.Description; InstalledOn = (ConvertTo-IsoUtc $_.InstalledOn) }
    })

    $sm = 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager'
    $pfro = Get-ItemProperty -Path $sm -Name PendingFileRenameOperations -ErrorAction SilentlyContinue
    $activeName = (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\ComputerName\ActiveComputerName').ComputerName
    $pendingName = (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\ComputerName\ComputerName').ComputerName
    $pending = [pscustomobject]@{
        ComponentBasedServicing = Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending'
        WindowsUpdate           = Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired'
        PendingFileRename       = ($null -ne $pfro)
        ComputerRename          = ($activeName -ne $pendingName)
    }

    $timeSource = ((& w32tm.exe /query /source) | Out-String).Trim()

    $firewall = @(Get-NetFirewallProfile | ForEach-Object {
        [pscustomobject]@{ Profile = [string]$_.Name; Enabled = ([string]$_.Enabled -eq 'True') }
    })

    $rdp = Get-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server' -Name fDenyTSConnections

    # Domain controllers have no local SAM, so there is no local Administrators group to read (DomainRole 4 and 5).
    $localAdmins = $null
    if ($cs.DomainRole -lt 4) {
        # By SID, so it also works on non-English installs.
        $localAdmins = @(Get-LocalGroupMember -SID 'S-1-5-32-544' | ForEach-Object { [string]$_.Name })
    }

    [pscustomobject]@{
        SchemaVersion          = 1
        ComputerName           = $env:COMPUTERNAME
        CollectedAt            = (ConvertTo-IsoUtc (Get-Date))
        Os                     = [pscustomobject]@{
            Caption          = $os.Caption
            Version          = $os.Version
            Build            = [int]$cv.CurrentBuild
            Ubr              = [int]$cv.UBR
            EditionId        = $cv.EditionID
            InstallationType = $cv.InstallationType
            LastBootUpTime   = (ConvertTo-IsoUtc $os.LastBootUpTime)
        }
        DomainRole             = [int]$cs.DomainRole
        Domain                 = $cs.Domain
        Disks                  = $disks
        AutoServicesNotRunning = $autoNotRunning
        InstalledFeatures      = $features
        Hotfixes               = $hotfixes
        PendingReboot          = $pending
        TimeSource             = $timeSource
        Firewall               = $firewall
        RdpEnabled             = ($rdp.fDenyTSConnections -eq 0)
        LocalAdministrators    = $localAdmins
    }
}

function Get-SbCollectorScript {
    <# Returns the collector script block (used by the tests to check it stays Windows PowerShell 5.1-safe). #>
    [CmdletBinding()] [OutputType([scriptblock])] param()
    $script:Collector
}

function ConvertTo-SbSnapshot {
    <# Normalises collector output (local, deserialized from remoting, or read from JSON) into a plain object. #>
    [CmdletBinding()]
    param([Parameter(Mandatory, ValueFromPipeline)] $InputObject)
    process {
        # Round-trip through JSON: drops PSComputerName/RunspaceId/PSShowComputerName and deserialization type names.
        $json = $InputObject | Select-Object -Property * -ExcludeProperty PSComputerName, RunspaceId, PSShowComputerName |
            ConvertTo-Json -Depth 6
        $snap = $json | ConvertFrom-Json -Depth 6
        if ($snap.SchemaVersion -ne 1) { throw "Unsupported snapshot schema version '$($snap.SchemaVersion)'." }
        $snap
    }
}

function Get-SbSnapshot {
    <#
      Runs the collector locally (no -ComputerName) or on many servers at once (Invoke-Command fans out in parallel).
      Unreachable servers come back as error records in -ErrorVariable; the entry script turns them into findings.
    #>
    [CmdletBinding()]
    param(
        [string[]] $ComputerName,
        [pscredential] $Credential,
        [int] $ThrottleLimit = 32
    )
    if (-not $ComputerName) {
        return (& $script:Collector | ConvertTo-SbSnapshot)
    }
    $params = @{ ComputerName = $ComputerName; ScriptBlock = $script:Collector; ThrottleLimit = $ThrottleLimit }
    if ($Credential) { $params.Credential = $Credential }
    Invoke-Command @params | ConvertTo-SbSnapshot
}

# ---------------------------------------------------------------------------------------------------------------
# Pure evaluation (runs anywhere)
# ---------------------------------------------------------------------------------------------------------------
function New-SbFinding {
    param([string] $Server, [ValidateSet('High', 'Medium', 'Low', 'Info')] [string] $Severity, [string] $Check, [string] $Detail)
    [pscustomobject]@{ Server = $Server; Severity = $Severity; Check = $Check; Detail = $Detail }
}

function Test-SbNameMatch {
    <# True if $Name matches any of the wildcard patterns (case-insensitive). #>
    param([string] $Name, [string[]] $Patterns)
    foreach ($p in @($Patterns)) { if ($Name -like $p) { return $true } }
    $false
}

function Test-SbBaseline {
    <#
      Compares one snapshot with the baseline and returns findings (Server, Severity, Check, Detail).
      -Now is a parameter so tests (and re-runs of old snapshots) are deterministic.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] $Snapshot,
        [Parameter(Mandatory)] $Baseline,
        [datetime] $Now = [datetime]::UtcNow
    )
    $s = $Snapshot
    $b = $Baseline
    $name = $s.ComputerName
    $now = $Now.ToUniversalTime()
    $out = [Collections.Generic.List[object]]::new()

    # Operating system build and edition
    if ($s.Os.Build -lt $b.MinimumBuild) {
        $out.Add((New-SbFinding $name High 'OsBuild' "Build $($s.Os.Build).$($s.Os.Ubr) is below the baseline build $($b.MinimumBuild)."))
    }
    elseif ($b.MinimumUbr -and $s.Os.Build -eq $b.MinimumBuild -and $s.Os.Ubr -lt $b.MinimumUbr) {
        $out.Add((New-SbFinding $name High 'OsPatchLevel' "OS build $($s.Os.Build).$($s.Os.Ubr) is older than the required $($b.MinimumBuild).$($b.MinimumUbr)."))
    }
    if ($s.Os.Caption -match 'Evaluation' -or $s.Os.EditionId -like '*Eval') {
        $out.Add((New-SbFinding $name Info 'EvaluationEdition' 'Evaluation edition (180-day licence). Fine for a lab, not for production.'))
    }
    if ($b.PreferServerCore -and $s.Os.InstallationType -ne 'Server Core') {
        $out.Add((New-SbFinding $name Low 'InstallationType' "Installed as '$($s.Os.InstallationType)'. Baseline prefers Server Core (smaller footprint and attack surface)."))
    }

    # Uptime and pending reboots
    $boot = [datetime]::Parse($s.Os.LastBootUpTime, [cultureinfo]::InvariantCulture, 'AdjustToUniversal,AssumeUniversal')
    $uptimeDays = [math]::Floor(($now - $boot).TotalDays)
    if ($uptimeDays -gt $b.MaxUptimeDays) {
        $out.Add((New-SbFinding $name Medium 'Uptime' "Up for $uptimeDays days (baseline: $($b.MaxUptimeDays)). Patch reboots are being skipped."))
    }
    $reasons = @()
    if ($s.PendingReboot.ComponentBasedServicing) { $reasons += 'Component Based Servicing' }
    if ($s.PendingReboot.WindowsUpdate)           { $reasons += 'Windows Update' }
    if ($s.PendingReboot.ComputerRename)          { $reasons += 'computer rename' }
    if ($reasons) {
        $out.Add((New-SbFinding $name High 'PendingReboot' "Reboot pending: $($reasons -join ', ')."))
    }
    elseif ($s.PendingReboot.PendingFileRename) {
        # Applications queue file renames too; on its own this is not a reason to block maintenance.
        $out.Add((New-SbFinding $name Info 'PendingFileRename' 'PendingFileRenameOperations is set (applications use it as well). Clears on the next planned reboot.'))
    }

    # Updates (Get-HotFix data)
    $dated = @($s.Hotfixes | Where-Object { $_.InstalledOn } |
        ForEach-Object { [datetime]::Parse($_.InstalledOn, [cultureinfo]::InvariantCulture, 'AdjustToUniversal,AssumeUniversal') })
    if ($dated.Count -eq 0) {
        $out.Add((New-SbFinding $name Medium 'Updates' 'No dated hotfix found. Get-HotFix only lists CBS updates: confirm in Windows Update history.'))
    }
    else {
        $latest = ($dated | Sort-Object -Descending)[0]
        $age = [math]::Floor(($now - $latest).TotalDays)
        if ($age -gt $b.MaxDaysSinceLastUpdate) {
            $out.Add((New-SbFinding $name High 'Updates' "Last update installed $age days ago ($($latest.ToString('yyyy-MM-dd'))). Baseline: $($b.MaxDaysSinceLastUpdate) days."))
        }
    }

    # Disks
    foreach ($d in @($s.Disks)) {
        if ($d.SizeGB -le 0) { continue }
        $pct = [math]::Round(100 * $d.FreeGB / $d.SizeGB, 1)
        if ($pct -lt $b.CriticalFreePercent) {
            $out.Add((New-SbFinding $name High 'DiskSpace' "$($d.Drive) has $pct% free ($($d.FreeGB) of $($d.SizeGB) GB)."))
        }
        elseif ($pct -lt $b.MinFreePercent) {
            $out.Add((New-SbFinding $name Medium 'DiskSpace' "$($d.Drive) has $pct% free ($($d.FreeGB) of $($d.SizeGB) GB)."))
        }
    }

    # Services
    foreach ($svc in @($s.AutoServicesNotRunning)) {
        if (-not (Test-SbNameMatch $svc.Name $b.IgnoreStoppedServices)) {
            $out.Add((New-SbFinding $name Medium 'Service' "Automatic service '$($svc.Name)' ($($svc.DisplayName)) is $($svc.State)."))
        }
    }

    # Features
    foreach ($f in @($b.ForbiddenFeatures)) {
        if ($s.InstalledFeatures -contains $f) {
            $out.Add((New-SbFinding $name High 'ForbiddenFeature' "Feature '$f' is installed. Remove it: Uninstall-WindowsFeature $f"))
        }
    }
    foreach ($rule in @($b.RequiredFeatures)) {
        if ($name -like $rule.Server) {
            foreach ($f in @($rule.Features)) {
                if ($s.InstalledFeatures -notcontains $f) {
                    $out.Add((New-SbFinding $name Medium 'MissingFeature' "Feature '$f' is required for servers matching '$($rule.Server)'."))
                }
            }
        }
    }

    # Time, firewall, remote access
    if (Test-SbNameMatch $s.TimeSource $b.BadTimeSources) {
        $out.Add((New-SbFinding $name High 'TimeSource' "Time source is '$($s.TimeSource)'. Domain members must follow the domain hierarchy; the PDC emulator an external NTP source."))
    }
    foreach ($fw in @($s.Firewall)) {
        if (-not $fw.Enabled) {
            $out.Add((New-SbFinding $name High 'Firewall' "Windows Firewall '$($fw.Profile)' profile is off."))
        }
    }
    if ($s.RdpEnabled -and $b.RdpAllowed -and -not (Test-SbNameMatch $name $b.RdpAllowed)) {
        $out.Add((New-SbFinding $name Low 'Rdp' 'Remote Desktop is enabled on a server that the baseline manages remotely only.'))
    }

    # Local Administrators
    if ($null -eq $s.LocalAdministrators) {
        if ($s.DomainRole -ge 4) {
            $out.Add((New-SbFinding $name Info 'LocalAdministrators' 'Domain controller: no local Administrators group. Review the domain Administrators group instead (episode 2).'))
        }
    }
    else {
        foreach ($m in @($s.LocalAdministrators)) {
            $short = ($m -split '\\')[-1]
            $allowed = Test-SbNameMatch $m $b.AllowedLocalAdmins
            $allowed = $allowed -or (Test-SbNameMatch $short $b.AllowedLocalAdmins)
            if (-not $allowed) {
                $out.Add((New-SbFinding $name Medium 'LocalAdministrators' "Unexpected member of local Administrators: $m"))
            }
        }
    }

    $out.ToArray()
}

function New-SbUnreachableFinding {
    <# Turns a failed remote connection into a finding, so a dead server never disappears from the report. #>
    [CmdletBinding()] param([Parameter(Mandatory)][string] $Server, [string] $Reason = 'Could not connect')
    New-SbFinding $Server High 'Unreachable' $Reason
}

function Format-SbFindingOrder {
    <# High first, then server name, then check. #>
    [CmdletBinding()] param([Parameter(ValueFromPipeline)] $Finding)
    begin { $all = [Collections.Generic.List[object]]::new() }
    process { if ($null -ne $Finding) { $all.Add($Finding) } }
    end {
        $all | Sort-Object -Property @{ Expression = { $script:SeverityOrder[$_.Severity] } }, Server, Check, Detail
    }
}

function ConvertTo-SbMarkdown {
    <# Markdown report: one summary row per server, then every finding, worst first. #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [AllowEmptyCollection()] [object[]] $Finding,
        [Parameter(Mandatory)] [string[]] $Server,
        [datetime] $Now = [datetime]::UtcNow
    )
    $sorted = @($Finding | Format-SbFindingOrder)
    $sb = [Text.StringBuilder]::new()
    [void]$sb.AppendLine('# Server baseline report')
    [void]$sb.AppendLine('')
    [void]$sb.AppendLine("Generated $($Now.ToUniversalTime().ToString('yyyy-MM-dd HH:mm')) UTC for $($Server.Count) server(s).")
    [void]$sb.AppendLine('')
    [void]$sb.AppendLine('| Server | High | Medium | Low | Info |')
    [void]$sb.AppendLine('|---|---:|---:|---:|---:|')
    foreach ($srv in ($Server | Sort-Object)) {
        $mine = @($sorted | Where-Object Server -eq $srv)
        $c = foreach ($sev in 'High', 'Medium', 'Low', 'Info') { @($mine | Where-Object Severity -eq $sev).Count }
        [void]$sb.AppendLine("| $srv | $($c[0]) | $($c[1]) | $($c[2]) | $($c[3]) |")
    }
    [void]$sb.AppendLine('')
    [void]$sb.AppendLine('| Severity | Server | Check | Detail |')
    [void]$sb.AppendLine('|---|---|---|---|')
    foreach ($f in $sorted) {
        $detail = $f.Detail -replace '\|', '\|'
        [void]$sb.AppendLine("| $($f.Severity) | $($f.Server) | $($f.Check) | $detail |")
    }
    $sb.ToString()
}

Export-ModuleMember -Function Get-SbCollectorScript, ConvertTo-SbSnapshot, Get-SbSnapshot, Test-SbBaseline,
    New-SbUnreachableFinding, Format-SbFindingOrder, ConvertTo-SbMarkdown
