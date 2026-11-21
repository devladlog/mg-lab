Set-StrictMode -Version Latest

# ---------------------------------------------------------------------------------------------------------------
# CoreLab: read-only Server Core readiness and footprint check for the lab, a setup plan for Core servers, and a
# check of container Dockerfiles that use the Nano Server base image. Windows PowerShell 5.1 and PowerShell 7.
# Facts that come from Microsoft Learn are in comments next to the code; OUR policy lives in core-lab.json.
# ---------------------------------------------------------------------------------------------------------------

function New-CoreFinding {
    param([string] $Target, [string] $Severity, [string] $Check, [string] $Message, [string] $Fix = '')
    [pscustomobject]@{ Severity = $Severity; Target = $Target; Check = $Check; Message = $Message; Fix = $Fix }
}

function Get-CoreProp {
    param($Object, [string] $Name, $Default = $null)
    if ($null -eq $Object) { return $Default }
    if ($Object -is [System.Collections.IDictionary]) { if ($Object.Contains($Name)) { return $Object[$Name] }; return $Default }
    $p = $Object.PSObject.Properties[$Name]
    if ($p) { return $p.Value }
    $Default
}

function Read-CoreLabConfig {
    [CmdletBinding()]
    param([Parameter(Mandatory)] [string] $Path)
    $c = Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json
    if ((Get-CoreProp $c 'SchemaVersion') -ne 1) { throw "Unsupported SchemaVersion in '$Path' (expected 1)." }
    foreach ($k in 'Policy', 'DesktopOnlyFeatures', 'Targets', 'Setup') { if (-not (Get-CoreProp $c $k)) { throw "'$Path' is missing '$k'." } }
    if ([int]$c.Policy.MaxCoreSystemDriveUsedGB -lt 1) { throw 'Policy.MaxCoreSystemDriveUsedGB must be at least 1.' }
    foreach ($t in @($c.Targets)) {
        $n = [string]$t.Name
        # Learn: Nano Server is not an installable host operating system any more (it is a container base image).
        if ([string](Get-CoreProp $t 'ExpectedInstall') -match 'nano' -or [string](Get-CoreProp $t 'Role') -match 'nano') {
            throw "Target '$n': Nano Server is not an installation option for a host (Learn: it is only available as a container base image). Use Core or DesktopExperience."
        }
        if (@('Core', 'DesktopExperience') -notcontains [string](Get-CoreProp $t 'ExpectedInstall')) { throw "Target '$n': ExpectedInstall must be Core or DesktopExperience." }
        if (@('Required', 'No') -notcontains [string](Get-CoreProp $t 'AppCompat' 'No')) { throw "Target '$n': AppCompat must be Required or No." }
        if ([string](Get-CoreProp $t 'ExpectedInstall') -eq 'DesktopExperience' -and -not (Get-CoreProp $t 'Reason')) { throw "Target '$n': a Desktop Experience server needs a Reason (we want a Core server unless there is one)." }
        if ([string](Get-CoreProp $t 'ExpectedInstall') -eq 'DesktopExperience' -and [string](Get-CoreProp $t 'AppCompat' 'No') -eq 'Required') { throw "Target '$n': the App Compatibility FOD only installs on Server Core." }
    }
    $dupe = @($c.Targets | ForEach-Object { ([string]$_.Name).ToUpperInvariant() } | Group-Object | Where-Object Count -gt 1 | ForEach-Object Name)
    if ($dupe.Count) { throw "Duplicate target(s) in '$Path': $($dupe -join ', ')." }
    # these two values end up inside generated scripts: allow only plain characters
    if ([string]$c.Setup.AppCompatCapability -notmatch '^[A-Za-z0-9.~]+$') { throw 'Setup.AppCompatCapability may only contain letters, digits, dots and tildes.' }
    $src = [string](Get-CoreProp $c.Setup 'FodSourcePath' '')
    if ($src -ne '' -and $src -notmatch '^([A-Za-z]:\\|\\\\)[^''";|&`$<>]*$') { throw 'Setup.FodSourcePath must be a drive or UNC path without quotes, semicolons or other shell characters.' }
    $c
}

# ---------------------------------------------------------------------------------------------------------------
# Collector (runs ON each server; read-only; self-contained; Windows PowerShell 5.1 safe)
# ---------------------------------------------------------------------------------------------------------------

$script:CoreCollector = {
    $ErrorActionPreference = 'Stop'
    $errors = New-Object System.Collections.ArrayList
    # Learn (Server apps must be able to run without the Server Graphical Shell): ServerLevels registry values
    $levels = @()
    try {
        $k = Get-ItemProperty -Path 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Server\ServerLevels'
        $levels = @($k.PSObject.Properties |
            Where-Object { $_.Name -notlike 'PS*' -and [string]$_.Value -eq '1' } |
            ForEach-Object { [string]$_.Name })
    } catch { [void]$errors.Add("ServerLevels: $($_.Exception.Message)") }
    $features = @()
    try { $features = @(Get-WindowsFeature | Where-Object { $_.Installed } | ForEach-Object { [string]$_.Name }) } catch { [void]$errors.Add("Get-WindowsFeature: $($_.Exception.Message)") }
    $app = 'Unknown'
    try {
        $cap = @(Get-WindowsCapability -Online | Where-Object { [string]$_.Name -like 'ServerCore.AppCompatibility*' })
        if ($cap.Count) { $app = [string]$cap[0].State } else { $app = 'NotListed' }
    } catch { [void]$errors.Add("Get-WindowsCapability: $($_.Exception.Message)") }
    $caption = ''; $version = ''; $memTotal = 0; $memFree = 0
    try {
        $os = Get-CimInstance -ClassName Win32_OperatingSystem
        $caption = [string]$os.Caption; $version = [string]$os.Version
        $memTotal = [double]$os.TotalVisibleMemorySize; $memFree = [double]$os.FreePhysicalMemory      # KB
    } catch { [void]$errors.Add("Win32_OperatingSystem: $($_.Exception.Message)") }
    $size = 0; $free = 0
    try {
        $d = Get-CimInstance -ClassName Win32_LogicalDisk -Filter ("DeviceID='" + $env:SystemDrive + "'")
        $size = [double]$d.Size; $free = [double]$d.FreeSpace
    } catch { [void]$errors.Add("Win32_LogicalDisk: $($_.Exception.Message)") }
    $svc = 0; $winrm = 'Unknown'
    try {
        $all = @(Get-Service)
        $svc = @($all | Where-Object { [string]$_.Status -eq 'Running' }).Count
        $w = @($all | Where-Object { $_.Name -eq 'WinRM' })
        if ($w.Count) { $winrm = [string]$w[0].Status }
    } catch { [void]$errors.Add("Get-Service: $($_.Exception.Message)") }
    $fw = -1
    try { $fw = @(Get-NetFirewallRule -DisplayGroup 'Windows Remote Management' | Where-Object { [string]$_.Enabled -eq 'True' }).Count } catch { [void]$errors.Add("Get-NetFirewallRule: $($_.Exception.Message)") }
    [pscustomobject]@{
        ComputerName             = [string]$env:COMPUTERNAME
        Unreachable              = $false
        OsCaption                = $caption
        OsVersion                = $version
        ServerLevels             = @($levels)
        InstalledFeatures        = @($features)
        AppCompatState           = $app
        WinRmService             = $winrm
        WinRmFirewallRulesEnabled = $fw
        SystemDriveSizeGB        = [Math]::Round($size / 1GB, 1)
        SystemDriveUsedGB        = [Math]::Round(($size - $free) / 1GB, 1)
        MemoryTotalMB            = [Math]::Round($memTotal / 1KB, 0)
        MemoryUsedMB             = [Math]::Round(($memTotal - $memFree) / 1KB, 0)
        RunningServices          = $svc
        Errors                   = @($errors)
    }
}

function Get-CoreCollectorScript { $script:CoreCollector }

function Get-CoreFacts {
    <# Facts from each computer over WinRM. A computer that cannot be reached becomes a fact (Unreachable), not an exception. Read-only. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [string[]] $ComputerName, [pscredential] $Credential)
    foreach ($name in $ComputerName) {
        $p = @{ ComputerName = $name; ScriptBlock = $script:CoreCollector; ErrorAction = 'Stop' }
        if ($Credential) { $p.Credential = $Credential }
        try {
            Invoke-Command @p | Select-Object -Property * -ExcludeProperty PSComputerName, RunspaceId, PSShowComputerName
        }
        catch {
            [pscustomobject]@{ ComputerName = $name; Unreachable = $true; Errors = @($_.Exception.Message) }
        }
    }
}

function Get-CoreInstallType {
    <# Learn: the server levels are additive. ServerGuiShell means Desktop Experience, Server-GuiMgmt the Minimal Server Interface, ServerCore alone is Server Core. #>
    param([string[]] $ServerLevels)
    $l = @($ServerLevels)
    if ($l -contains 'ServerGuiShell') { return 'DesktopExperience' }
    if ($l -contains 'Server-GuiMgmt') { return 'MinimalInterface' }
    if ($l -contains 'ServerCore') { return 'Core' }
    'Unknown'
}

# ---------------------------------------------------------------------------------------------------------------
# Rules (pure)
# ---------------------------------------------------------------------------------------------------------------

function Test-CoreHost {
    [CmdletBinding()]
    param([Parameter(Mandatory)] $Facts, [Parameter(Mandatory)] $Config)
    $name = [string]$Facts.ComputerName
    $t = @($Config.Targets | Where-Object { ([string]$_.Name) -eq $name }) | Select-Object -First 1
    $f = New-Object System.Collections.ArrayList
    if (-not $t) { return (New-CoreFinding $name Low 'UnknownHost' 'Not in core-lab.json, so no expectation to compare with.' 'Add it to Targets.') }
    if (Get-CoreProp $Facts 'Unreachable' $false) {
        $why = ((@(Get-CoreProp $Facts 'Errors' @())) -join ' ')
        [void]$f.Add((New-CoreFinding $name High 'Unreachable' "No answer over WinRM. A Core server has no desktop to fall back on: $why" 'Console: SConfig, option 4 (Configure remote management), then 1 (Enable). Learn: enabled by default on a domain network.'))
        return $f
    }
    $type = Get-CoreInstallType -ServerLevels @(Get-CoreProp $Facts 'ServerLevels' @())
    $expected = [string]$t.ExpectedInstall
    $installed = @(Get-CoreProp $Facts 'InstalledFeatures' @())
    $blockers = @($installed | Where-Object { @($Config.DesktopOnlyFeatures) -contains $_ } | Sort-Object)
    if ($type -eq 'Unknown') {
        [void]$f.Add((New-CoreFinding $name Low 'InstallTypeUnknown' 'The ServerLevels registry key could not be read, so Core or Desktop is unknown.' 'Look at the CollectorError rows.'))
    }
    elseif ($type -ne $expected) {
        # Learn: you cannot convert between Server Core and Server with Desktop Experience after installation
        $sev = 'Medium'
        [void]$f.Add((New-CoreFinding $name $sev 'InstallTypeMismatch' "Expected $expected, found $type. There is no in-place conversion (Learn): the fix is a clean install." 'Plan the rebuild: move the roles, then reinstall as the expected option.'))
    }
    elseif ($type -eq 'DesktopExperience') {
        [void]$f.Add((New-CoreFinding $name Info 'DesktopJustified' "Desktop Experience on purpose: $($t.Reason)."))
    }
    if ($type -ne 'Core' -and $type -ne 'Unknown' -and $blockers.Count) {
        [void]$f.Add((New-CoreFinding $name Info 'CoreBlockers' "$($blockers.Count) installed feature(s) are not in Server Core (Learn): $($blockers -join ', ')." 'They would have to move, or stay on a Desktop Experience server.'))
    }
    if ($type -eq 'Core') {
        $fw = [int](Get-CoreProp $Facts 'WinRmFirewallRulesEnabled' -1)
        if ($fw -eq 0) { [void]$f.Add((New-CoreFinding $name Medium 'WinRmFirewall' 'No enabled firewall rule in the group Windows Remote Management.' 'Enable-NetFirewallRule -DisplayGroup "Windows Remote Management" (Learn)')) }
        $app = [string](Get-CoreProp $Facts 'AppCompatState' 'Unknown')
        $need = [string](Get-CoreProp $t 'AppCompat' 'No')
        if ($need -eq 'Required' -and $app -ne 'Installed') {
            [void]$f.Add((New-CoreFinding $name Medium 'AppCompatMissing' "The App Compatibility FOD is required here ($(Get-CoreProp $t 'AppCompatReason' 'see core-lab.json')) and its state is '$app'." 'Add-WindowsCapability -Online -Name ServerCore.AppCompatibility~~~~0.0.1.0, then restart (Learn)'))
        }
        if ($need -ne 'Required' -and $app -eq 'Installed') {
            [void]$f.Add((New-CoreFinding $name Low 'AppCompatNotNeeded' 'The App Compatibility FOD adds tools from Desktop Experience (Learn) but nothing here needs them.' 'Remove it, or mark the host AppCompat Required.'))
        }
        $max = [double]$Config.Policy.MaxCoreSystemDriveUsedGB
        $used = [double](Get-CoreProp $Facts 'SystemDriveUsedGB' 0)
        if ($used -gt $max) { [void]$f.Add((New-CoreFinding $name Low 'FootprintHigh' "System drive used: $used GB, our limit for a Core server is $max GB." 'Find out what grew: logs, the component store, the page file, data on C:.')) }
    }
    foreach ($e in @(Get-CoreProp $Facts 'Errors' @())) { [void]$f.Add((New-CoreFinding $name Low 'CollectorError' ([string]$e))) }
    $f
}

function Get-CoreFootprint {
    <# Averages per install type over the hosts that answered. A measurement of THESE servers, not a benchmark: they run different roles. #>
    [CmdletBinding()]
    param([object[]] $Hosts = @())
    $rows = New-Object System.Collections.ArrayList
    $withType = @($Hosts | Where-Object { -not (Get-CoreProp $_ 'Unreachable' $false) } | ForEach-Object {
            [pscustomobject]@{ Type = (Get-CoreInstallType -ServerLevels @(Get-CoreProp $_ 'ServerLevels' @())); H = $_ } })
    foreach ($g in @($withType | Where-Object { $_.Type -ne 'Unknown' } | Group-Object Type | Sort-Object Name)) {
        $hs = @($g.Group | ForEach-Object { $_.H })
        [void]$rows.Add([pscustomobject]@{
                InstallType        = [string]$g.Name
                Hosts              = $hs.Count
                AvgDiskUsedGB      = [Math]::Round((@($hs | ForEach-Object { [double]$_.SystemDriveUsedGB }) | Measure-Object -Average).Average, 1)
                AvgMemoryUsedMB    = [Math]::Round((@($hs | ForEach-Object { [double]$_.MemoryUsedMB }) | Measure-Object -Average).Average, 0)
                AvgRunningServices = [Math]::Round((@($hs | ForEach-Object { [double]$_.RunningServices }) | Measure-Object -Average).Average, 0)
                AvgFeatures        = [Math]::Round((@($hs | ForEach-Object { @($_.InstalledFeatures).Count }) | Measure-Object -Average).Average, 1)
            })
    }
    $rows
}

# ---------------------------------------------------------------------------------------------------------------
# Nano Server is not a host any more: it is a container base image. So the Nano check is a Dockerfile check.
# Learn: the Nano Server image has a smaller API surface; PowerShell, WMI and the Windows servicing stack are absent.
# ---------------------------------------------------------------------------------------------------------------

function Test-NanoDockerfile {
    [CmdletBinding()]
    param([Parameter(Mandatory)] [string] $Content, [string] $Name = 'Dockerfile', $Config)
    $requirePin = $true
    if ($Config) { $requirePin = [bool](Get-CoreProp (Get-CoreProp $Config 'Policy') 'RequirePinnedImageTag' $true) }
    $findings = New-Object System.Collections.ArrayList
    $lines = @($Content -split "\r?\n")
    $esc = '\'
    foreach ($l in $lines) { if ($l -match '^\s*#\s*escape\s*=\s*(.)\s*$') { $esc = $Matches[1] }; if ($l -notmatch '^\s*#') { break } }
    # join continuation lines, remember the line each instruction started on
    $ins = New-Object System.Collections.ArrayList
    $buf = ''; $start = 0
    for ($i = 0; $i -lt $lines.Count; $i++) {
        $l = $lines[$i]
        if ($buf -eq '' -and ($l -match '^\s*#' -or $l.Trim() -eq '')) { continue }
        if ($l -match '^\s*#') { continue }
        if ($buf -eq '') { $start = $i + 1 }
        $t = $l.TrimEnd()
        if ($t.EndsWith($esc)) { $buf += $t.Substring(0, $t.Length - 1) + ' '; continue }
        $buf += $t
        [void]$ins.Add([pscustomobject]@{ Line = $start; Text = $buf.Trim() })
        $buf = ''
    }
    if ($buf -ne '') { [void]$ins.Add([pscustomobject]@{ Line = $start; Text = $buf.Trim() }) }
    $stages = @{}          # alias -> base image
    $current = $null; $stageNo = 0
    $psPattern = '(^|[\s;&|\[",])powershell(\.exe)?(\s|"|,|$)'
    foreach ($x in $ins) {
        $word = ($x.Text -split '\s+', 2)[0].ToUpperInvariant()
        $rest = if ($x.Text.Length -gt $word.Length) { $x.Text.Substring($word.Length).Trim() } else { '' }
        if ($word -eq 'FROM') {
            $stageNo++
            $tok = @($rest -split '\s+' | Where-Object { $_ -and $_ -notlike '--*' })
            $image = [string]$tok[0]
            $alias = $null
            if ($tok.Count -ge 3 -and $tok[1] -ieq 'AS') { $alias = [string]$tok[2] }
            $isStageRef = $stages.ContainsKey($image.ToLowerInvariant())
            $base = if ($isStageRef) { [string]$stages[$image.ToLowerInvariant()] } else { $image }
            $current = [pscustomobject]@{ Base = $base; Nano = ($base -match 'nanoserver'); No = $stageNo }
            if ($alias) { $stages[$alias.ToLowerInvariant()] = $base }
            if (-not $isStageRef -and $image -ne 'scratch' -and $image -notmatch '@sha256:') {
                $lastSeg = ($image -split '/')[-1]
                $tag = if ($lastSeg -match ':(.+)$') { $Matches[1] } else { '' }
                if ($requirePin -and ($tag -eq '' -or $tag -eq 'latest')) {
                    [void]$findings.Add((New-CoreFinding "${Name}:$($x.Line)" Low 'UnpinnedTag' "Base image '$image' has no pinned tag, so a rebuild can change the OS under you." 'Pin the tag (for example ltsc2025) or a digest.'))
                }
            }
            if ($base -match 'servercore') {
                [void]$findings.Add((New-CoreFinding "${Name}:$($x.Line)" Info 'ServerCoreBase' 'Server Core base image: it runs traditional .NET Framework apps; Nano Server is built for .NET Core apps (Learn).' 'If the app has no .NET Framework dependency, test it on Nano Server.'))
            }
            continue
        }
        if ($null -eq $current -or -not $current.Nano) { continue }
        if (($word -eq 'RUN' -or $word -eq 'SHELL' -or $word -eq 'CMD' -or $word -eq 'ENTRYPOINT') -and
            $rest -match $psPattern) {
            [void]$findings.Add((New-CoreFinding "${Name}:$($x.Line)" High 'NanoNoPowerShell' `
                ("$word uses Windows PowerShell in a stage based on '$($current.Base)'. " +
                 'The Nano Server image has no PowerShell (Learn).') `
                'Build the step in a Server Core stage and copy the result over.'))
        }
    }
    $findings
}

# ---------------------------------------------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------------------------------------------

function ConvertTo-CoreMarkdown {
    [CmdletBinding()]
    param([object[]] $Hosts = @(), [object[]] $Findings = @())
    $sb = New-Object System.Text.StringBuilder
    [void]$sb.AppendLine('# Server Core check')
    [void]$sb.AppendLine()
    [void]$sb.AppendLine('## Servers')
    [void]$sb.AppendLine()
    [void]$sb.AppendLine('| Server | Install type | OS | System drive used GB | Memory used MB | Running services | Features | App Compat FOD | WinRM firewall rules |')
    [void]$sb.AppendLine('|---|---|---|---|---|---|---|---|---|')
    foreach ($h in $Hosts) {
        if (Get-CoreProp $h 'Unreachable' $false) { [void]$sb.AppendLine(('| {0} | no answer | - | - | - | - | - | - | - |' -f $h.ComputerName)); continue }
        [void]$sb.AppendLine(('| {0} | {1} | {2} | {3} | {4} | {5} | {6} | {7} | {8} |' -f $h.ComputerName, (Get-CoreInstallType -ServerLevels @($h.ServerLevels)), $h.OsCaption,
                $h.SystemDriveUsedGB, $h.MemoryUsedMB, $h.RunningServices, @($h.InstalledFeatures).Count, $h.AppCompatState, $h.WinRmFirewallRulesEnabled))
    }
    $fp = @(Get-CoreFootprint -Hosts $Hosts)
    if ($fp.Count) {
        [void]$sb.AppendLine()
        [void]$sb.AppendLine('## Footprint by install type')
        [void]$sb.AppendLine()
        [void]$sb.AppendLine('Averages over the servers that answered. A measurement of these servers, not a benchmark: they do not run the same roles.')
        [void]$sb.AppendLine()
        [void]$sb.AppendLine('| Install type | Servers | Avg disk used GB | Avg memory used MB | Avg running services | Avg features installed |')
        [void]$sb.AppendLine('|---|---|---|---|---|---|')
        foreach ($r in $fp) { [void]$sb.AppendLine(('| {0} | {1} | {2} | {3} | {4} | {5} |' -f $r.InstallType, $r.Hosts, $r.AvgDiskUsedGB, $r.AvgMemoryUsedMB, $r.AvgRunningServices, $r.AvgFeatures)) }
    }
    [void]$sb.AppendLine()
    [void]$sb.AppendLine('## Findings')
    [void]$sb.AppendLine()
    if (-not @($Findings).Count) { [void]$sb.AppendLine('None.') }
    else {
        [void]$sb.AppendLine('| Severity | Target | Check | Message |')
        [void]$sb.AppendLine('|---|---|---|---|')
        foreach ($x in $Findings) { [void]$sb.AppendLine(('| {0} | {1} | {2} | {3} |' -f $x.Severity, $x.Target, $x.Check, ($x.Message -replace '\|', '/'))) }
    }
    $sb.ToString()
}

# ---------------------------------------------------------------------------------------------------------------
# Setup: a plan (pure), then apply. Remote steps run over WinRM. Restart needs -AllowRestart. Manual steps never run.
# ---------------------------------------------------------------------------------------------------------------

function Get-CoreSetupPlan {
    [CmdletBinding()]
    param([Parameter(Mandatory)] [object[]] $Hosts, [Parameter(Mandatory)] $Config)
    $steps = New-Object System.Collections.ArrayList
    $add = { param($target, $id, $kind, $desc, $switch, $script) [void]$steps.Add([pscustomobject]@{ Target = $target; Id = $id; Kind = $kind; Description = $desc; NeedsSwitch = $switch; Script = $script }) }
    $cap = [string]$Config.Setup.AppCompatCapability
    $src = [string](Get-CoreProp $Config.Setup 'FodSourcePath' '')
    foreach ($h in $Hosts) {
        $name = [string]$h.ComputerName
        $t = @($Config.Targets | Where-Object { ([string]$_.Name) -eq $name }) | Select-Object -First 1
        if (-not $t) { continue }
        if (Get-CoreProp $h 'Unreachable' $false) {
            & $add $name 'Console' 'Manual' 'No answer over WinRM: at the console run SConfig, option 4 (Configure remote management), then 1 (Enable). SConfig cannot run in a remote PowerShell session (Learn).' '' ''
            continue
        }
        $type = Get-CoreInstallType -ServerLevels @(Get-CoreProp $h 'ServerLevels' @())
        if ($type -ne 'Unknown' -and $type -ne [string]$t.ExpectedInstall) {
            & $add $name 'Rebuild' 'Manual' `
                "Expected $($t.ExpectedInstall), found ${type}: no in-place conversion (Learn). Reinstall, then move the roles." '' ''
            continue
        }
        if ($type -ne 'Core') { continue }
        if ([int](Get-CoreProp $h 'WinRmFirewallRulesEnabled' -1) -eq 0) {
            & $add $name 'WinRmFirewall' 'Run' 'Enable the firewall rule group Windows Remote Management' '' 'Enable-NetFirewallRule -DisplayGroup "Windows Remote Management"'
        }
        if ([string](Get-CoreProp $t 'AppCompat' 'No') -eq 'Required' -and [string](Get-CoreProp $h 'AppCompatState' 'Unknown') -ne 'Installed') {
            $srcArg = ''
            if ($src -ne '') { $srcArg = " -Source '$src' -LimitAccess" }
            & $add $name 'AppCompatFod' 'Run' $(if ($src -ne '') { "Add the App Compatibility FOD from '$src'" } else { 'Add the App Compatibility FOD from Windows Update' }) '' @"
`$r = Add-WindowsCapability -Online -Name '$cap'$srcArg
[pscustomobject]@{ RestartNeeded = [bool]`$r.RestartNeeded }
"@
            & $add $name 'Restart' 'Restart' 'Restart the server so the App Compatibility FOD takes effect (Learn: restart, then install updates)' 'AllowRestart' ''
        }
    }
    $steps
}

function Invoke-CoreSetupPlan {
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)] [object[]] $Plan, [pscredential] $Credential, [switch] $AllowRestart)
    $failed = @{}
    foreach ($s in $Plan) {
        if ($s.Kind -eq 'Manual') { [pscustomobject]@{ Target = $s.Target; Id = $s.Id; Result = 'Manual'; Detail = $s.Description }; continue }
        if ($failed.ContainsKey($s.Target)) { [pscustomobject]@{ Target = $s.Target; Id = $s.Id; Result = 'Skipped'; Detail = 'An earlier step on this server did not finish.' }; continue }
        if ($s.NeedsSwitch -eq 'AllowRestart' -and -not $AllowRestart) {
            [pscustomobject]@{ Target = $s.Target; Id = $s.Id; Result = 'Skipped'
                Detail = 'Restarts the server: run again with -AllowRestart.' }
            continue
        }
        if (-not $PSCmdlet.ShouldProcess($s.Target, $s.Description)) { continue }
        try {
            if ($s.Kind -eq 'Restart') {
                $r = @{ ComputerName = $s.Target; Force = $true; ErrorAction = 'Stop' }
                if ($Credential) { $r.Credential = $Credential }
                Restart-Computer @r
                [pscustomobject]@{ Target = $s.Target; Id = $s.Id; Result = 'Done'; Detail = 'restart requested' }
            }
            else {
                $p = @{ ComputerName = $s.Target; ScriptBlock = [scriptblock]::Create($s.Script); ErrorAction = 'Stop' }
                if ($Credential) { $p.Credential = $Credential }
                $out = Invoke-Command @p
                $detail = ''
                if ($out -and (Get-CoreProp $out 'RestartNeeded' $false)) { $detail = 'restart needed' }
                [pscustomobject]@{ Target = $s.Target; Id = $s.Id; Result = 'Done'; Detail = $detail }
            }
        }
        catch { $failed[$s.Target] = $true; [pscustomobject]@{ Target = $s.Target; Id = $s.Id; Result = 'Failed'; Detail = $_.Exception.Message } }
    }
}

Export-ModuleMember -Function Read-CoreLabConfig, Get-CoreCollectorScript, Get-CoreFacts, Get-CoreInstallType, Test-CoreHost, Get-CoreFootprint, Test-NanoDockerfile, ConvertTo-CoreMarkdown, Get-CoreSetupPlan, Invoke-CoreSetupPlan
