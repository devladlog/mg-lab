<#
  DEVLADLOG Windows Server #3 - GpoLab
  Group Policy as code for the lab.contoso.com domain:

    * Read-GpoLabDefinition   validates a JSON file that describes GPOs (registry-based settings, status, links,
                              security filtering).
    * Invoke-GpoLabDeployment makes the domain match the file. Idempotent, supports -WhatIf, and never leaves a
                              security-filtered GPO without Read for computers (MS16-072).
    * Export-GpoLabSnapshot   reads every GPO, its permissions, its settings (from Get-GPOReport XML) and every link
                              in the domain into one JSON file.
    * Test-GpoLabHygiene      pure checks on that snapshot: unlinked, empty, disabled halves that still hold settings,
                              AD/SYSVOL version mismatch, user settings computers can't read, nobody can apply, ...
    * Backup-GpoLab           Backup-GPO -All plus a links file (a backup restores settings, not links).

  Written for Windows PowerShell 5.1 (built into Windows Server) and PowerShell 7. The GroupPolicy and
  ActiveDirectory modules come with GPMC / RSAT; the tests stub and mock them.
#>

$script:SeverityOrder = @{ High = 0; Medium = 1; Low = 2; Info = 3 }
$script:ValidStatus = 'AllSettingsEnabled', 'UserSettingsDisabled', 'ComputerSettingsDisabled', 'AllSettingsDisabled'
$script:ValidTypes = 'String', 'ExpandString', 'DWord', 'QWord', 'MultiString', 'Binary'
# Permission levels that include Read (Get-GPPermission -All). GpoCustom is unknown, so it doesn't count.
$script:ReadLevels = 'GpoRead', 'GpoApply', 'GpoEdit', 'GpoEditDeleteModifySecurity'
$script:AuthenticatedUsersSid = 'S-1-5-11'

# ---------------------------------------------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------------------------------------------
function Get-GpoLabScope {
    <# HKLM -> Computer configuration, HKCU -> User configuration (Learn: Set-GPRegistryValue -Key). #>
    [CmdletBinding()] [OutputType([string])]
    param([Parameter(Mandatory)][string] $Key)
    $hive = ($Key -split '\\')[0].ToUpperInvariant()
    switch ($hive) {
        { $_ -in 'HKLM', 'HKEY_LOCAL_MACHINE' } { return 'Computer' }
        { $_ -in 'HKCU', 'HKEY_CURRENT_USER' } { return 'User' }
        default { throw "Key '$Key' must start with HKLM or HKCU." }
    }
}

function Test-GpoLabHalfEnabled {
    <# Is the Computer or User half of a GPO processed, given its GpoStatus? #>
    [CmdletBinding()] [OutputType([bool])]
    param([Parameter(Mandatory)][string] $Status, [Parameter(Mandatory)][ValidateSet('Computer', 'User')][string] $Half)
    if ($Status -eq 'AllSettingsDisabled') { return $false }
    if ($Half -eq 'User' -and $Status -eq 'UserSettingsDisabled') { return $false }
    if ($Half -eq 'Computer' -and $Status -eq 'ComputerSettingsDisabled') { return $false }
    $true
}

function Read-GpoLabDefinition {
    <#
      Loads and validates the definition file. Fails early (before touching the domain) on: duplicate names, keys
      outside HKLM/HKCU, unknown value types, settings in a half the status disables, links outside the domain,
      and security filtering without a computer Read group.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string] $Path)
    $def = Get-Content -Raw -Path $Path | ConvertFrom-Json
    $errors = New-Object System.Collections.Generic.List[string]
    if (-not $def.Domain -or -not $def.DomainDn) { $errors.Add('Domain and DomainDn are required.') }
    $names = @{}
    foreach ($g in @($def.Gpos)) {
        if (-not $g.Name) { $errors.Add('Every GPO needs a Name.'); continue }
        if ($names.ContainsKey($g.Name)) { $errors.Add("Duplicate GPO name '$($g.Name)'.") }
        $names[$g.Name] = $true
        $status = if ($g.Status) { [string]$g.Status } else { 'AllSettingsEnabled' }
        if ($script:ValidStatus -notcontains $status) { $errors.Add("$($g.Name): unknown Status '$status'.") }
        foreach ($r in @($g.Registry)) {
            try { $half = Get-GpoLabScope -Key $r.Key } catch { $errors.Add("$($g.Name): $($_.Exception.Message)"); continue }
            if ($script:ValidTypes -notcontains [string]$r.Type) { $errors.Add("$($g.Name): $($r.ValueName) has unknown Type '$($r.Type)'.") }
            if (($script:ValidStatus -contains $status) -and -not (Test-GpoLabHalfEnabled -Status $status -Half $half)) {
                $errors.Add("$($g.Name): $($r.ValueName) is a $half setting but Status '$status' disables that half.")
            }
        }
        foreach ($l in @($g.Links)) {
            if (-not ([string]$l.Target).EndsWith([string]$def.DomainDn, [StringComparison]::OrdinalIgnoreCase)) {
                $errors.Add("$($g.Name): link target '$($l.Target)' is not in $($def.DomainDn).")
            }
        }
        if (@($g.SecurityFiltering).Count -gt 0 -and -not $g.ComputerRead) {
            $errors.Add("$($g.Name): SecurityFiltering needs ComputerRead (computers must read the GPO, MS16-072).")
        }
    }
    if ($errors.Count) { throw ("Definition '$Path' is invalid:`n - " + ($errors -join "`n - ")) }
    $def
}

function New-GpoLabFinding {
    param([string] $Severity, [string] $Check, [string] $Target, [string] $Detail)
    [pscustomobject]@{ Severity = $Severity; Check = $Check; Target = $Target; Detail = $Detail }
}

function Test-GpoLabHygiene {
    <#
      Checks a snapshot (Export-GpoLabSnapshot) and returns findings, worst first. Pure: no domain needed.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] $Snapshot)
    $out = New-Object System.Collections.ArrayList
    $domainComputersSid = "$($Snapshot.DomainSid)-515"

    $linksByGpo = @{}
    foreach ($som in @($Snapshot.Soms)) {
        foreach ($l in @($som.Links)) {
            $id = ([string]$l.GpoId).ToLowerInvariant()
            if (-not $linksByGpo.ContainsKey($id)) { $linksByGpo[$id] = New-Object System.Collections.ArrayList }
            [void]$linksByGpo[$id].Add([pscustomobject]@{ Path = $som.Path; Enabled = [bool]$l.Enabled; Enforced = [bool]$l.Enforced })
        }
        if ($som.InheritanceBlocked) {
            [void]$out.Add((New-GpoLabFinding Info 'BlockedInheritance' $som.Path 'Inheritance is blocked here: only enforced links from above apply.'))
        }
    }

    foreach ($g in @($Snapshot.Gpos)) {
        $id = ([string]$g.Id).ToLowerInvariant()
        $links = if ($linksByGpo.ContainsKey($id)) { @($linksByGpo[$id]) } else { @() }
        $enabledLinks = @($links | Where-Object Enabled)
        $hasComputer = [bool]$g.Computer.HasSettings
        $hasUser = [bool]$g.User.HasSettings

        if ($links.Count -eq 0) {
            [void]$out.Add((New-GpoLabFinding Low 'UnlinkedGpo' $g.Name 'Not linked anywhere: it applies to nobody. Delete it or link it (back it up first).'))
        }
        elseif ($enabledLinks.Count -eq 0) {
            [void]$out.Add((New-GpoLabFinding Low 'AllLinksDisabled' $g.Name "Linked $($links.Count) time(s), every link disabled."))
        }
        if (-not $hasComputer -and -not $hasUser) {
            [void]$out.Add((New-GpoLabFinding Low 'EmptyGpo' $g.Name 'No settings in either half.'))
        }
        foreach ($half in 'Computer', 'User') {
            $info = $g.$half
            if ($info.HasSettings -and -not (Test-GpoLabHalfEnabled -Status $g.Status -Half $half)) {
                [void]$out.Add((New-GpoLabFinding High 'DisabledHalfHasSettings' $g.Name "$half settings exist but GpoStatus is $($g.Status): they are silently ignored."))
            }
            if ([int]$info.DSVersion -ne [int]$info.SysvolVersion) {
                [void]$out.Add((New-GpoLabFinding Medium 'VersionMismatch' $g.Name "$half version AD $($info.DSVersion) vs SYSVOL $($info.SysvolVersion): the two halves of the GPO replicate separately and disagree."))
            }
        }

        $perms = @($g.Permissions)
        $appliers = @($perms | Where-Object { $_.Permission -eq 'GpoApply' -and -not $_.Denied })
        if ($enabledLinks.Count -gt 0 -and $appliers.Count -eq 0) {
            [void]$out.Add((New-GpoLabFinding Medium 'NobodyCanApply' $g.Name 'Linked, but no trustee has Apply group policy.'))
        }
        if ($enabledLinks.Count -gt 0 -and $hasUser -and (Test-GpoLabHalfEnabled -Status $g.Status -Half 'User')) {
            $computerRead = @($perms | Where-Object {
                    ($_.Sid -eq $script:AuthenticatedUsersSid -or $_.Sid -eq $domainComputersSid) -and
                    ($script:ReadLevels -contains $_.Permission) -and -not $_.Denied
                })
            if ($computerRead.Count -eq 0) {
                [void]$out.Add((New-GpoLabFinding High 'UserGpoNoComputerRead' $g.Name 'User settings, but neither Authenticated Users nor Domain Computers can read it. Since MS16-072 the computer reads user policy: grant Read (not Apply) to Authenticated Users or Domain Computers.'))
            }
        }
        foreach ($l in @($links | Where-Object Enforced)) {
            [void]$out.Add((New-GpoLabFinding Info 'EnforcedLink' $g.Name "Enforced at $($l.Path). Use sparingly: it overrides lower links and ignores blocked inheritance."))
        }
    }
    $out | Sort-Object @{ e = { $script:SeverityOrder[$_.Severity] } }, Check, Target
}

function ConvertTo-GpoLabMarkdown {
    [CmdletBinding()] [OutputType([string])]
    param([Parameter(Mandatory)] $Snapshot, [Parameter(Mandatory)][AllowEmptyCollection()][object[]] $Finding)
    $count = { param($s) @($Finding | Where-Object Severity -eq $s).Count }
    $sb = New-Object System.Text.StringBuilder
    [void]$sb.AppendLine("# Group Policy hygiene report: $($Snapshot.Domain)")
    [void]$sb.AppendLine('')
    $when = $Snapshot.ExportedAt
    if ($when -is [datetime]) { $when = $when.ToUniversalTime().ToString('yyyy-MM-dd HH:mm') + ' UTC' }
    [void]$sb.AppendLine("Snapshot: $when - $(@($Snapshot.Gpos).Count) GPO(s), $(@($Snapshot.Soms).Count) container(s) with links or blocked inheritance.")
    [void]$sb.AppendLine('')
    [void]$sb.AppendLine("**High $(& $count 'High') / Medium $(& $count 'Medium') / Low $(& $count 'Low') / Info $(& $count 'Info')**")
    [void]$sb.AppendLine('')
    [void]$sb.AppendLine('| GPO | Status | Links | Computer | User |')
    [void]$sb.AppendLine('|---|---|---|---|---|')
    foreach ($g in @($Snapshot.Gpos | Sort-Object Name)) {
        $n = 0
        foreach ($som in @($Snapshot.Soms)) { $n += @($som.Links | Where-Object { ([string]$_.GpoId) -eq ([string]$g.Id) }).Count }
        $c = if ($g.Computer.HasSettings) { "settings (v$($g.Computer.DSVersion))" } else { '-' }
        $u = if ($g.User.HasSettings) { "settings (v$($g.User.DSVersion))" } else { '-' }
        [void]$sb.AppendLine("| $($g.Name) | $($g.Status) | $n | $c | $u |")
    }
    [void]$sb.AppendLine('')
    [void]$sb.AppendLine('| Severity | Check | Target | Detail |')
    [void]$sb.AppendLine('|---|---|---|---|')
    foreach ($f in $Finding) { [void]$sb.AppendLine("| $($f.Severity) | $($f.Check) | $($f.Target) | $($f.Detail) |") }
    $sb.ToString()
}

# ---------------------------------------------------------------------------------------------------------------
# Domain side (GroupPolicy / ActiveDirectory modules)
# ---------------------------------------------------------------------------------------------------------------
function Assert-GpoLabModule {
    foreach ($m in 'GroupPolicy', 'ActiveDirectory') {
        if (-not (Get-Module -Name $m)) {
            if (Get-Module -ListAvailable -Name $m) { Import-Module $m -ErrorAction Stop }
            elseif (-not (Get-Command -Name 'Get-GPO' -ErrorAction SilentlyContinue)) {
                throw "Module '$m' not found. Install-WindowsFeature GPMC, RSAT-AD-PowerShell (or run on a DC)."
            }
        }
    }
}

function New-GpoLabLog {
    param([string] $Gpo, [string] $Action, [string] $Target, [string] $Result)
    [pscustomobject]@{ Gpo = $Gpo; Action = $Action; Target = $Target; Result = $Result }
}

function Test-GpoLabValueEqual {
    param($Current, $Wanted)
    if ($null -eq $Current) { return $false }
    if ([string]$Current.Type -ne [string]$Wanted.Type) { return $false }
    [string]$Current.Value -eq [string]$Wanted.Value
}

function Invoke-GpoLabDeployment {
    <#
      Makes the domain match the definition. Every change goes through ShouldProcess (-WhatIf / -Confirm) and is
      logged; a second run reports NoChange for everything.
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)][string] $DefinitionPath, [string] $Server)
    $def = Read-GpoLabDefinition -Path $DefinitionPath
    Assert-GpoLabModule
    $common = @{ Domain = $def.Domain }
    if ($Server) { $common.Server = $Server }

    foreach ($g in @($def.Gpos)) {
        $name = [string]$g.Name
        $status = if ($g.Status) { [string]$g.Status } else { 'AllSettingsEnabled' }

        # 1. The GPO itself
        $gpo = Get-GPO @common -Name $name -ErrorAction SilentlyContinue
        if (-not $gpo) {
            if ($PSCmdlet.ShouldProcess($name, 'New-GPO')) {
                $gpo = New-GPO @common -Name $name -Comment ([string]$g.Comment)
                New-GpoLabLog $name 'CreateGpo' $name 'Done'
            }
            else { New-GpoLabLog $name 'CreateGpo' $name 'WhatIf' }
        }
        else { New-GpoLabLog $name 'CreateGpo' $name 'NoChange' }

        # 2. Status: disable the half we don't use
        if (-not $gpo) { New-GpoLabLog $name 'SetStatus' $status 'WhatIf' }
        elseif ([string]$gpo.GpoStatus -ne $status) {
            if ($PSCmdlet.ShouldProcess($name, "GpoStatus = $status")) {
                $gpo.GpoStatus = $status
                New-GpoLabLog $name 'SetStatus' $status 'Done'
            }
            else { New-GpoLabLog $name 'SetStatus' $status 'WhatIf' }
        }
        else { New-GpoLabLog $name 'SetStatus' $status 'NoChange' }

        # 3. Registry-based settings, one value at a time
        foreach ($r in @($g.Registry)) {
            $target = "$($r.Key)\$($r.ValueName)"
            $current = $null
            if ($gpo) { $current = Get-GPRegistryValue @common -Name $name -Key $r.Key -ValueName $r.ValueName -ErrorAction SilentlyContinue }
            if (Test-GpoLabValueEqual -Current $current -Wanted $r) { New-GpoLabLog $name 'SetRegistry' $target 'NoChange'; continue }
            if ($PSCmdlet.ShouldProcess("$name : $target", "Set-GPRegistryValue $($r.Type) $($r.Value)")) {
                Set-GPRegistryValue @common -Name $name -Key $r.Key -ValueName $r.ValueName -Type $r.Type -Value $r.Value | Out-Null
                New-GpoLabLog $name 'SetRegistry' $target 'Done'
            }
            else { New-GpoLabLog $name 'SetRegistry' $target 'WhatIf' }
        }

        # 4. Links (matched by GPO id, not by name)
        foreach ($l in @($g.Links)) {
            $existing = $null
            if ($gpo) {
                $som = Get-GPInheritance @common -Target $l.Target
                $existing = @($som.GpoLinks | Where-Object { [string]$_.GpoId -eq [string]$gpo.Id }) | Select-Object -First 1
            }
            $enforced = if ($l.Enforced) { 'Yes' } else { 'No' }
            if (-not $existing) {
                if ($PSCmdlet.ShouldProcess("$name -> $($l.Target)", 'New-GPLink')) {
                    $p = @{ Name = $name; Target = $l.Target; LinkEnabled = 'Yes'; Enforced = $enforced }
                    if ($l.Order) { $p.Order = [int]$l.Order }
                    New-GPLink @common @p | Out-Null
                    New-GpoLabLog $name 'Link' $l.Target 'Done'
                }
                else { New-GpoLabLog $name 'Link' $l.Target 'WhatIf' }
                continue
            }
            $drift = (-not $existing.Enabled) -or ([bool]$existing.Enforced -ne [bool]$l.Enforced) -or ($l.Order -and [int]$existing.Order -ne [int]$l.Order)
            if (-not $drift) { New-GpoLabLog $name 'Link' $l.Target 'NoChange'; continue }
            if ($PSCmdlet.ShouldProcess("$name -> $($l.Target)", 'Set-GPLink')) {
                $p = @{ Name = $name; Target = $l.Target; LinkEnabled = 'Yes'; Enforced = $enforced }
                if ($l.Order) { $p.Order = [int]$l.Order }
                Set-GPLink @common @p | Out-Null
                New-GpoLabLog $name 'Link' $l.Target 'Updated'
            }
            else { New-GpoLabLog $name 'Link' $l.Target 'WhatIf' }
        }

        # 5. Security filtering: groups get Apply, computers keep Read (MS16-072), Authenticated Users loses Apply
        if (@($g.SecurityFiltering).Count -gt 0) {
            $perms = @()
            if ($gpo) { $perms = @(Get-GPPermission @common -Name $name -All) }
            $wanted = @()
            foreach ($grp in @($g.SecurityFiltering)) { $wanted += [pscustomobject]@{ Name = [string]$grp; Level = 'GpoApply' } }
            $wanted += [pscustomobject]@{ Name = [string]$g.ComputerRead; Level = 'GpoRead' }
            foreach ($w in $wanted) {
                $have = @($perms | Where-Object { [string]$_.Trustee.Name -eq $w.Name }) | Select-Object -First 1
                if ($have -and [string]$have.Permission -eq $w.Level) { New-GpoLabLog $name 'Permission' "$($w.Name)=$($w.Level)" 'NoChange'; continue }
                if ($PSCmdlet.ShouldProcess("$name : $($w.Name)", "Set-GPPermission $($w.Level)")) {
                    Set-GPPermission @common -Name $name -TargetName $w.Name -TargetType Group -PermissionLevel $w.Level -Replace | Out-Null
                    New-GpoLabLog $name 'Permission' "$($w.Name)=$($w.Level)" 'Done'
                }
                else { New-GpoLabLog $name 'Permission' "$($w.Name)=$($w.Level)" 'WhatIf' }
            }
        }
    }
}

function Get-GpoLabReportHalf {
    <# HasSettings = the half of a Get-GPOReport XML document has at least one ExtensionData element. #>
    param($ReportXml, [string] $Half)
    $node = $ReportXml.GPO.$Half
    [bool](@($node.ExtensionData).Count -gt 0 -and $null -ne @($node.ExtensionData)[0])
}

function Export-GpoLabSnapshot {
    <# Reads the domain's GPOs, permissions, settings presence and links into one JSON file. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string] $Path, [string] $Server)
    Assert-GpoLabModule
    $ad = @{}
    if ($Server) { $ad.Server = $Server }
    $domain = Get-ADDomain @ad
    $gp = @{ Domain = [string]$domain.DNSRoot }
    if ($Server) { $gp.Server = $Server }

    $gpos = foreach ($g in @(Get-GPO @gp -All)) {
        [xml]$report = Get-GPOReport @gp -Guid $g.Id -ReportType Xml
        $perms = foreach ($p in @(Get-GPPermission @gp -Guid $g.Id -All)) {
            [pscustomobject]@{ Trustee = [string]$p.Trustee.Name; Sid = [string]$p.Trustee.Sid; Permission = [string]$p.Permission; Denied = [bool]$p.Denied }
        }
        [pscustomobject]@{
            Name        = [string]$g.DisplayName
            Id          = ([string]$g.Id).ToLowerInvariant()
            Status      = [string]$g.GpoStatus
            Description = [string]$g.Description
            Modified    = ([datetime]$g.ModificationTime).ToUniversalTime().ToString('o')
            WmiFilter   = if ($g.WmiFilter) { [string]$g.WmiFilter.Name } else { $null }
            Computer    = [pscustomobject]@{ DSVersion = [int]$g.Computer.DSVersion; SysvolVersion = [int]$g.Computer.SysvolVersion; HasSettings = (Get-GpoLabReportHalf $report 'Computer') }
            User        = [pscustomobject]@{ DSVersion = [int]$g.User.DSVersion; SysvolVersion = [int]$g.User.SysvolVersion; HasSettings = (Get-GpoLabReportHalf $report 'User') }
            Permissions = @($perms)
        }
    }

    $targets = @([string]$domain.DistinguishedName) + @(Get-ADOrganizationalUnit @ad -Filter * | ForEach-Object { [string]$_.DistinguishedName })
    $soms = foreach ($t in $targets) {
        $som = Get-GPInheritance @gp -Target $t
        $blocked = ($som.GpoInheritanceBlocked -eq $true) -or ([string]$som.GpoInheritanceBlocked -eq 'Yes')
        $links = foreach ($l in @($som.GpoLinks)) {
            [pscustomobject]@{ GpoId = ([string]$l.GpoId).ToLowerInvariant(); DisplayName = [string]$l.DisplayName; Enabled = [bool]$l.Enabled; Enforced = [bool]$l.Enforced; Order = [int]$l.Order }
        }
        if (@($links).Count -or $blocked) { [pscustomobject]@{ Path = $t; InheritanceBlocked = $blocked; Links = @($links) } }
    }

    $snapshot = [pscustomobject]@{
        Domain     = [string]$domain.DNSRoot
        DomainSid  = [string]$domain.DomainSID
        ExportedAt = (Get-Date).ToUniversalTime().ToString('o')
        Gpos       = @($gpos)
        Soms       = @($soms)
    }
    $snapshot | ConvertTo-Json -Depth 8 | Set-Content -Path $Path -Encoding UTF8
    $snapshot
}

function Backup-GpoLab {
    <#
      Backup-GPO -All into a new timestamped folder, plus links.json from a fresh snapshot: Import-GPO brings the
      settings back, not the links.
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)][string] $Path, [string] $Server, [datetime] $Now = (Get-Date))
    $dir = Join-Path $Path ($Now.ToString('yyyyMMdd-HHmmss'))
    if (-not $PSCmdlet.ShouldProcess($dir, 'Backup-GPO -All + links.json')) { return }
    Assert-GpoLabModule
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
    $p = @{ All = $true; Path = $dir; Comment = "GpoLab backup $($Now.ToString('s'))" }
    if ($Server) { $p.Server = $Server }
    $backups = @(Backup-GPO @p)
    $snapshot = Export-GpoLabSnapshot -Path (Join-Path $dir 'snapshot.json') -Server $Server
    $snapshot.Soms | ConvertTo-Json -Depth 6 | Set-Content -Path (Join-Path $dir 'links.json') -Encoding UTF8
    [pscustomobject]@{ Path = $dir; GpoCount = $backups.Count; LinkFile = (Join-Path $dir 'links.json') }
}

Export-ModuleMember -Function Get-GpoLabScope, Test-GpoLabHalfEnabled, Read-GpoLabDefinition, Test-GpoLabHygiene,
ConvertTo-GpoLabMarkdown, Invoke-GpoLabDeployment, Export-GpoLabSnapshot, Backup-GpoLab
