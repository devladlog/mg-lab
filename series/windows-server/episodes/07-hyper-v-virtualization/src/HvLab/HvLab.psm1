#Requires -Version 5.1
<#
    HvLab - a Hyper-V host audit, a throwaway-VM builder and a checkpoint cleanup for the MG lab (DEVLADLOG Windows Server #7).

    Audit        Get-HvHostFacts (collector, runs ON the Hyper-V host) + Test-HvHost (pure rules) + ConvertTo-HvMarkdown
    Build        Read-HvLabConfig + Get-HvVmPlan (pure: spec -> ordered steps) + New-HvLabVm (runs the steps)
    Checkpoints  Get-HvCheckpointPlan (pure) + Invoke-HvCheckpointCleanup + Wait-HvDiskMerge
    Tear-down    Remove-HvLabVm (only touches paths under the configured lab root)

    Windows PowerShell 5.1 compatible (the Hyper-V module is Windows only); the tests run in PowerShell 7 on Linux with
    stubs and mocks for the Hyper-V cmdlets.
#>
Set-StrictMode -Version 3.0

# Learn, "Hyper-V maximum scale limits in Windows Server": 50 checkpoints per VM, "dependent on the amount of available storage"
$script:CheckpointLimit = 50
# Learn, "Upgrade virtual machine version": the minimum VM configuration version for some features
$script:FeatureMinVersion = [ordered]@{
    'GPU partitioning'                     = '12.0'
    'Dynamic processor compatibility mode' = '10.0'
    'Hibernation support'                  = '9.0'
    'Guest virtualization-based security'  = '8.0'
    'Nested virtualization'                = '8.0'
    'Virtual TPM'                          = '7.0'
    'Production checkpoints'               = '6.2'
}
# Learn, "Manage Hyper-V Integration Services": names as Get-VMIntegrationService prints them
$script:CriticalServices = [ordered]@{
    'Shutdown'             = 'Medium'   # Learn: "High impact" when disabled, every shutdown becomes a hard power-off
    'Time Synchronization' = 'Medium'   # Learn: "High impact" when disabled, the clock drifts
    'Heartbeat'            = 'Low'
    'VSS'                  = 'Low'
}
$script:Severity = @{ High = 0; Medium = 1; Low = 2; Info = 3 }

function New-HvFinding {
    param([string] $Target, [string] $Severity, [string] $Check, [string] $Message)
    [pscustomobject]@{ Target = $Target; Severity = $Severity; Check = $Check; Message = $Message }
}

function Get-HvProp {
    param($Object, [string] $Name, $Default = $null)
    if ($null -eq $Object) { return $Default }
    if ($Object -is [System.Collections.IDictionary]) { if ($Object.Contains($Name)) { return $Object[$Name] }; return $Default }
    $p = $Object.PSObject.Properties[$Name]
    if ($p) { return $p.Value }
    $Default
}

function ConvertTo-HvVersion {
    # '12.0' -> [version]'12.0'; anything else -> $null
    param($Value)
    $v = $null
    if ([version]::TryParse([string]$Value, [ref]$v)) { return $v }
    $null
}

function Test-HvUnder {
    # is $Path inside $Root? (case-insensitive, either slash)
    param([string] $Path, [string] $Root)
    if (-not $Path -or -not $Root) { return $false }
    $a = ($Path -replace '/', '\').TrimEnd('\').ToLowerInvariant()
    $b = ($Root -replace '/', '\').TrimEnd('\').ToLowerInvariant()
    ($a -eq $b) -or $a.StartsWith($b + '\')
}

# ---------------------------------------------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------------------------------------------

function Read-HvLabConfig {
    [CmdletBinding()]
    param([Parameter(Mandatory)] [string] $Path)
    $c = Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json
    if ((Get-HvProp $c 'SchemaVersion') -ne 1) { throw "Unsupported SchemaVersion in '$Path' (expected 1)." }
    foreach ($k in 'Policy', 'TestVm', 'CheckpointDemo') { if (-not (Get-HvProp $c $k)) { throw "'$Path' is missing '$k'." } }
    $c
}

# ---------------------------------------------------------------------------------------------------------------
# Audit: collector (runs on the Hyper-V host)
# ---------------------------------------------------------------------------------------------------------------

$script:Collector = {
    # Runs ON the Hyper-V host. Windows PowerShell 5.1, self-contained (no HvLab functions), read-only.
    function Get-Chain([string] $Path) {
        $chain = @()
        $cur = $Path
        $guard = 0
        while ($cur -and $guard -lt 32) {
            $guard++
            try { $v = Get-VHD -Path $cur -ErrorAction Stop } catch { $chain += [pscustomobject]@{ Path = $cur; Type = 'Unreadable'; SizeGB = 0; FileSizeGB = 0 }; break }
            $chain += [pscustomobject]@{
                Path       = [string]$v.Path
                Type       = [string]$v.VhdType
                SizeGB     = [math]::Round($v.Size / 1GB, 2)
                FileSizeGB = [math]::Round($v.FileSize / 1GB, 2)
            }
            $cur = [string]$v.ParentPath
        }
        , $chain
    }

    $os = Get-CimInstance -ClassName Win32_OperatingSystem
    $cs = Get-CimInstance -ClassName Win32_ComputerSystem
    $vmh = Get-VMHost
    $supported = @(Get-VMHostSupportedVersion -ErrorAction SilentlyContinue)
    $default = @($supported | Where-Object { $_.IsDefault } | ForEach-Object { [string]$_.Version.ToString() }) | Select-Object -First 1
    $volumes = @(Get-CimInstance -ClassName Win32_LogicalDisk -Filter 'DriveType=3' | ForEach-Object {
            [pscustomobject]@{ Root = ([string]$_.DeviceID + '\'); SizeGB = [math]::Round($_.Size / 1GB, 1); FreeGB = [math]::Round($_.FreeSpace / 1GB, 1) }
        })

    $vms = foreach ($vm in @(Get-VM)) {
        $gen = [int]$vm.Generation
        $secureBoot = $null; $template = $null
        if ($gen -eq 2) {
            $fw = Get-VMFirmware -VM $vm -ErrorAction SilentlyContinue
            if ($fw) { $secureBoot = ([string]$fw.SecureBoot -eq 'On'); $template = [string]$fw.SecureBootTemplate }
        }
        $tpm = $false
        $sec = Get-VMSecurity -VM $vm -ErrorAction SilentlyContinue
        if ($sec) { $tpm = [bool]$sec.TpmEnabled }
        $nested = $false
        $proc = Get-VMProcessor -VM $vm -ErrorAction SilentlyContinue
        if ($proc) { $nested = [bool]$proc.ExposeVirtualizationExtensions }
        $services = @(Get-VMIntegrationService -VM $vm -ErrorAction SilentlyContinue | ForEach-Object {
                [pscustomobject]@{ Name = [string]$_.Name; Enabled = [bool]$_.Enabled; Status = [string]$_.PrimaryStatusDescription }
            })
        $disks = @(Get-VMHardDiskDrive -VM $vm -ErrorAction SilentlyContinue | ForEach-Object {
                $c = Get-Chain ([string]$_.Path)
                [pscustomobject]@{ Path = [string]$_.Path; Chain = @($c) }
            })
        $adapters = @(Get-VMNetworkAdapter -VM $vm -ErrorAction SilentlyContinue | ForEach-Object {
                [pscustomobject]@{ SwitchName = [string]$_.SwitchName; MacSpoofing = ([string]$_.MacAddressSpoofing -eq 'On') }
            })
        $snaps = @(Get-VMSnapshot -VMName $vm.Name -ErrorAction SilentlyContinue | ForEach-Object {
                [pscustomobject]@{
                    Name       = [string]$_.Name
                    CreatedUtc = $_.CreationTime.ToUniversalTime().ToString('o')
                    Type       = [string]$_.SnapshotType
                    Parent     = [string]$_.ParentSnapshotName
                }
            })
        $repl = $null
        $r = Get-VMReplication -VMName $vm.Name -ErrorAction SilentlyContinue
        if ($r) { $repl = [pscustomobject]@{ State = [string]$r.State; Health = [string]$r.Health } }

        [pscustomobject]@{
            Name                = [string]$vm.Name
            State               = [string]$vm.State
            Status              = [string]$vm.Status
            Generation          = $gen
            Version             = [string]$vm.Version
            ProcessorCount      = [int]$vm.ProcessorCount
            MemoryStartupGB     = [math]::Round($vm.MemoryStartup / 1GB, 2)
            DynamicMemory       = [bool]$vm.DynamicMemoryEnabled
            MemoryMaximumGB     = [math]::Round($vm.MemoryMaximum / 1GB, 2)
            CheckpointType      = [string]$vm.CheckpointType
            AutomaticCheckpoints = [bool]$vm.AutomaticCheckpointsEnabled
            SecureBoot          = $secureBoot
            SecureBootTemplate  = $template
            TpmEnabled          = $tpm
            NestedVirtualization = $nested
            IntegrationServices = $services
            Disks               = $disks
            NetworkAdapters     = $adapters
            Checkpoints         = $snaps
            Replication         = $repl
        }
    }

    [pscustomobject]@{
        SchemaVersion = 1
        CollectedUtc  = (Get-Date).ToUniversalTime().ToString('o')
        Host          = [pscustomobject]@{
            ComputerName      = $env:COMPUTERNAME
            Caption           = [string]$os.Caption
            Build             = [int]$os.BuildNumber
            ProductType       = [int]$os.ProductType
            SystemDrive       = [string]$os.SystemDrive
            LogicalProcessors = [int]$vmh.LogicalProcessorCount
            MemoryGB          = [math]::Round($cs.TotalPhysicalMemory / 1GB, 1)
            VmPath            = [string]$vmh.VirtualMachinePath
            VhdPath           = [string]$vmh.VirtualHardDiskPath
            EnhancedSessionMode = [bool]$vmh.EnableEnhancedSessionMode
            SupportedVersions = @($supported | ForEach-Object { [string]$_.Version.ToString() })
            DefaultVersion    = [string]$default
            Volumes           = $volumes
        }
        Switches      = @(Get-VMSwitch | ForEach-Object { [pscustomobject]@{ Name = [string]$_.Name; SwitchType = [string]$_.SwitchType } })
        Vms           = @($vms)
    }
}

function Get-HvCollectorScript { $script:Collector }

function Get-HvHostFacts {
    <#
    .SYNOPSIS
    Runs the collector on the Hyper-V host (locally when ComputerName is empty or the local machine) and returns the facts.
    #>
    [CmdletBinding()]
    param([string] $ComputerName, [pscredential] $Credential)
    if (-not $ComputerName -or $ComputerName -eq $env:COMPUTERNAME -or $ComputerName -eq 'localhost') { return (& $script:Collector) }
    $p = @{ ComputerName = $ComputerName; ScriptBlock = $script:Collector }
    if ($Credential) { $p.Credential = $Credential }
    Invoke-Command @p | Select-Object -Property * -ExcludeProperty PSComputerName, RunspaceId, PSShowComputerName
}

# ---------------------------------------------------------------------------------------------------------------
# Audit: rules (pure)
# ---------------------------------------------------------------------------------------------------------------

function Get-HvChainDepth {
    # number of files in the longest disk chain of a VM facts object
    param($Vm)
    $max = 0
    foreach ($d in @(Get-HvProp $Vm 'Disks' @())) {
        $n = @(Get-HvProp $d 'Chain' @()).Count
        if ($n -gt $max) { $max = $n }
    }
    $max
}

function Test-HvHost {
    <#
    .SYNOPSIS
    Pure rules for the facts of one Hyper-V host. Thresholds that are OUR policy come from the config; the limits and
    feature versions that come from Microsoft Learn are constants in this module.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] $Facts, [Parameter(Mandatory)] $Config, [datetime] $Now = (Get-Date))
    $out = New-Object System.Collections.ArrayList
    $pol = $Config.Policy
    $h = $Facts.Host
    $hostName = [string]$h.ComputerName
    $vms = @($Facts.Vms)
    $dcs = @(Get-HvProp $pol 'DomainControllers' @() | ForEach-Object { ([string]$_).ToUpperInvariant() })
    $gen1ok = @(Get-HvProp $pol 'Gen1Allowed' @() | ForEach-Object { ([string]$_).ToUpperInvariant() })
    $sbOk = @(Get-HvProp $pol 'SecureBootOffAllowed' @() | ForEach-Object { ([string]$_).ToUpperInvariant() })
    $isServer = ([int]$h.ProductType -ne 1)
    $hostVersion = ConvertTo-HvVersion (Get-HvProp $h 'DefaultVersion')

    # --- host: where the files live --------------------------------------------------------------------------
    $sysDrive = [string](Get-HvProp $h 'SystemDrive' 'C:')
    $others = @(@($h.Volumes) | Where-Object { -not ([string]$_.Root).StartsWith($sysDrive, [StringComparison]::OrdinalIgnoreCase) })
    foreach ($pair in @(@('VmPath', 'virtual machine configuration'), @('VhdPath', 'virtual hard disk'))) {
        $path = [string](Get-HvProp $h $pair[0] '')
        if ($path -and $path.StartsWith($sysDrive, [StringComparison]::OrdinalIgnoreCase) -and $others.Count) {
            [void]$out.Add((New-HvFinding $hostName Low 'DefaultPathOnSystemDrive' "The default $($pair[1]) path ($path) is on the system drive while $($others[0].Root) exists: new VMs will fill C: first."))
        }
    }

    # --- host: thin provisioning vs free space ---------------------------------------------------------------
    $growth = @{}
    foreach ($vm in $vms) {
        foreach ($d in @(Get-HvProp $vm 'Disks' @())) {
            foreach ($f in @(Get-HvProp $d 'Chain' @())) {
                if ([string]$f.Type -in 'Dynamic', 'Differencing') {
                    $root = $null
                    foreach ($v in @($h.Volumes)) { if (Test-HvUnder -Path ([string]$f.Path) -Root ([string]$v.Root)) { $root = [string]$v.Root } }
                    if ($root) {
                        if (-not $growth.ContainsKey($root)) { $growth[$root] = 0.0 }
                        $growth[$root] += [math]::Max(0.0, [double]$f.SizeGB - [double]$f.FileSizeGB)
                    }
                }
            }
        }
    }
    foreach ($v in @($h.Volumes)) {
        $root = [string]$v.Root
        $g = 0.0
        if ($growth.ContainsKey($root)) { $g = [math]::Round($growth[$root], 1) }
        if ($g -gt [double]$v.FreeGB) {
            [void]$out.Add((New-HvFinding $hostName High 'DiskOvercommit' "Dynamic and differencing disks on $root can still grow by $g GB but only $($v.FreeGB) GB are free: if the guests fill their disks, the VMs pause with a critical error."))
        }
        elseif ($g -gt 0 -and [double]$v.FreeGB -lt [double](Get-HvProp $pol 'MinFreeGB' 50)) {
            [void]$out.Add((New-HvFinding $hostName Medium 'LowFreeSpace' "$root has $($v.FreeGB) GB free (policy: $(Get-HvProp $pol 'MinFreeGB' 50) GB) and its disks can still grow by $g GB."))
        }
    }

    # --- host: CPU and memory ratios (our policy: Hyper-V imposes no vCPU ratio, Learn) --------------------
    $running = @($vms | Where-Object { [string]$_.State -eq 'Running' })
    $vcpu = 0; $mem = 0.0
    foreach ($vm in $running) { $vcpu += [int]$vm.ProcessorCount; $mem += [double]$vm.MemoryStartupGB }
    $maxRatio = [double](Get-HvProp $pol 'MaxVcpuPerLogicalProcessor' 4)
    if ([int]$h.LogicalProcessors -gt 0 -and ($vcpu / [double]$h.LogicalProcessors) -gt $maxRatio) {
        [void]$out.Add((New-HvFinding $hostName Low 'VcpuRatio' "$vcpu virtual processors run on $($h.LogicalProcessors) logical processors (our policy: at most $maxRatio per logical processor; Hyper-V itself imposes no ratio)."))
    }
    $frac = [double](Get-HvProp $pol 'MaxMemoryFraction' 0.85)
    if ([double]$h.MemoryGB -gt 0 -and $mem -gt ([double]$h.MemoryGB * $frac)) {
        [void]$out.Add((New-HvFinding $hostName Medium 'MemoryCommitted' ("Running VMs start with {0:N1} GB of the host's {1} GB (policy: at most {2:N0}%); the host needs memory too." -f $mem, $h.MemoryGB, ($frac * 100))))
    }

    # --- per VM ----------------------------------------------------------------------------------------------
    foreach ($vm in $vms) {
        $n = [string]$vm.Name
        $up = $n.ToUpperInvariant()
        $isDc = $dcs -contains $up
        $gen = [int]$vm.Generation

        if ($gen -eq 1 -and $gen1ok -notcontains $up) {
            [void]$out.Add((New-HvFinding $n Low 'Generation1' 'Generation 1: no Secure Boot, no virtual TPM, boots from IDE. The generation cannot be changed after creation (Learn): rebuild as generation 2 when the guest allows it.'))
        }
        if ($gen -eq 2 -and (Get-HvProp $vm 'SecureBoot') -eq $false -and $sbOk -notcontains $up) {
            [void]$out.Add((New-HvFinding $n Medium 'SecureBootOff' 'Secure Boot is off on a generation 2 VM (it is on by default, Learn). Fine for a guest that cannot boot with it; otherwise turn it on.'))
        }

        # checkpoints
        $cps = @(Get-HvProp $vm 'Checkpoints' @())
        $ctype = [string](Get-HvProp $vm 'CheckpointType' '')
        if ($cps.Count -ge $script:CheckpointLimit) {
            [void]$out.Add((New-HvFinding $n High 'CheckpointLimit' "$($cps.Count) checkpoints: Learn's maximum is $($script:CheckpointLimit), dependent on available storage."))
        }
        elseif ($cps.Count -gt [int](Get-HvProp $pol 'MaxCheckpoints' 3)) {
            [void]$out.Add((New-HvFinding $n Medium 'TooManyCheckpoints' "$($cps.Count) checkpoints (policy: at most $(Get-HvProp $pol 'MaxCheckpoints' 3)). Every one is a differencing disk in the chain."))
        }
        $oldest = $null
        foreach ($c in $cps) {
            $age = ($Now.ToUniversalTime() - ([datetime]::Parse([string]$c.CreatedUtc, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::RoundtripKind)).ToUniversalTime()).TotalDays
            if ($null -eq $oldest -or $age -gt $oldest.Age) { $oldest = [pscustomobject]@{ Name = [string]$c.Name; Age = $age } }
        }
        if ($oldest) {
            $crit = [double](Get-HvProp $pol 'CheckpointCriticalDays' 30)
            $warn = [double](Get-HvProp $pol 'CheckpointMaxAgeDays' 7)
            if ($oldest.Age -ge $crit) {
                [void]$out.Add((New-HvFinding $n High 'CheckpointVeryOld' ("Checkpoint '{0}' is {1:N0} days old (policy: {2:N0}). Checkpoints are for hours or days, not a backup." -f $oldest.Name, $oldest.Age, $crit)))
            }
            elseif ($oldest.Age -ge $warn) {
                [void]$out.Add((New-HvFinding $n Medium 'CheckpointOld' ("Checkpoint '{0}' is {1:N0} days old (policy: {2:N0})." -f $oldest.Name, $oldest.Age, $warn)))
            }
        }
        if ($isDc -and $ctype -eq 'Standard') {
            [void]$out.Add((New-HvFinding $n High 'StandardCheckpointOnDc' 'Standard checkpoints can cause data consistency issues with systems that replicate data between nodes such as Active Directory (Learn). Use Production or turn checkpoints off for domain controllers.'))
        }
        elseif ($isDc -and $cps.Count) {
            [void]$out.Add((New-HvFinding $n Medium 'CheckpointOnDc' "$($cps.Count) checkpoint(s) on a domain controller. Applying one rolls AD back without telling the other DCs: delete them."))
        }
        if ($ctype -eq 'Production') {
            $vss = @(Get-HvProp $vm 'IntegrationServices' @()) | Where-Object { [string]$_.Name -eq 'VSS' } | Select-Object -First 1
            if ($vss -and -not [bool]$vss.Enabled) {
                [void]$out.Add((New-HvFinding $n Medium 'ProductionWithoutVss' 'Production checkpoints use VSS (Learn) but the VSS integration service is disabled, so the guest probably cannot take one: type Production then creates a standard checkpoint, ProductionOnly fails.'))
            }
        }
        if ((Get-HvProp $vm 'AutomaticCheckpoints' $false) -eq $true) {
            $sev = 'Low'; if ($isDc) { $sev = 'Medium' }
            [void]$out.Add((New-HvFinding $n $sev 'AutomaticCheckpoints' 'Automatic checkpoints are on: a checkpoint is created every time the VM starts (Learn). Turn off with Set-VM -AutomaticCheckpointsEnabled $false unless you want it.'))
        }

        # disks
        $depth = Get-HvChainDepth -Vm $vm
        if ($depth -gt [int](Get-HvProp $pol 'MaxDiskChainDepth' 3)) {
            [void]$out.Add((New-HvFinding $n Low 'DeepDiskChain' "The longest disk chain has $depth files (policy: $(Get-HvProp $pol 'MaxDiskChainDepth' 3)). Each level is a read through one more file; merge checkpoints."))
        }
        foreach ($d in @(Get-HvProp $vm 'Disks' @())) {
            foreach ($f in @(Get-HvProp $d 'Chain' @())) {
                if ([string]$f.Type -eq 'Unreadable') {
                    [void]$out.Add((New-HvFinding $n High 'BrokenDiskChain' "Cannot read '$($f.Path)': a parent disk was moved, deleted or is locked. Restore it before the VM is started."))
                }
            }
        }

        # configuration version vs features (Learn table) and vs the host
        $ver = ConvertTo-HvVersion (Get-HvProp $vm 'Version')
        if ($ver -and $hostVersion -and $ver -lt $hostVersion) {
            $missing = @($script:FeatureMinVersion.Keys | Where-Object { $ver -lt (ConvertTo-HvVersion $script:FeatureMinVersion[$_]) } | Select-Object -First 4)
            $detail = ''
            if ($missing.Count) { $detail = " Not available yet: $($missing -join ', ')." }
            [void]$out.Add((New-HvFinding $n Low 'OldConfigurationVersion' "Configuration version $ver, this host's default is $hostVersion.$detail Update-VMVersion is one-way: only after every host that may run it is upgraded."))
        }
        if ($ver -and (Get-HvProp $vm 'NestedVirtualization' $false) -eq $true -and $ver -lt (ConvertTo-HvVersion '8.0')) {
            [void]$out.Add((New-HvFinding $n High 'NestedNeedsVersion' "Nested virtualization needs configuration version 8.0 or higher (Learn); this VM is $ver."))
        }

        # nested virtualization
        if ((Get-HvProp $vm 'NestedVirtualization' $false) -eq $true) {
            if ($gen -eq 1) {
                [void]$out.Add((New-HvFinding $n Medium 'NestedOnGeneration1' 'Nested virtualization is exposed on a generation 1 VM; the checklist on Learn expects a generation 2 VM.'))
            }
            if ((Get-HvProp $vm 'DynamicMemory' $false) -eq $true) {
                [void]$out.Add((New-HvFinding $n Info 'NestedWithDynamicMemory' 'Dynamic Memory is on. Learn: enabling nested virtualization alone has no effect on it; once Hyper-V runs inside the VM, memory no longer fluctuates and can only be changed while the VM is off.'))
            }
            $spoof = @(@(Get-HvProp $vm 'NetworkAdapters' @()) | Where-Object { [string]$_.SwitchName -and -not [bool]$_.MacSpoofing })
            if ($spoof.Count) {
                [void]$out.Add((New-HvFinding $n Info 'NestedNetworking' 'Nested guests need either MAC address spoofing on this VM''s adapter or a NAT switch inside the VM (Learn).'))
            }
        }

        # health
        if ([string]$vm.State -eq 'Running') {
            $status = [string](Get-HvProp $vm 'Status' '')
            if ($status -and $status -ne 'Operating normally') {
                [void]$out.Add((New-HvFinding $n Medium 'HeartbeatNotNormal' "VM is Running but its heartbeat status is '$status'. Running only means Hyper-V set resources aside (Learn); no heartbeat means no operating system reported in."))
            }
        }
        foreach ($s in @(Get-HvProp $vm 'IntegrationServices' @())) {
            $name = [string]$s.Name
            if ($script:CriticalServices.Contains($name) -and -not [bool]$s.Enabled) {
                [void]$out.Add((New-HvFinding $n $script:CriticalServices[$name] 'IntegrationServiceOff' "The '$name' integration service is disabled."))
            }
        }
        $rep = Get-HvProp $vm 'Replication'
        if ($rep -and [string]$rep.Health -and [string]$rep.Health -ne 'Normal') {
            [void]$out.Add((New-HvFinding $n High 'ReplicationUnhealthy' "Hyper-V Replica health is $($rep.Health) (state $($rep.State))."))
        }
    }

    # --- differencing disks: one parent, many children ---------------------------------------------------------
    $parents = @{}
    foreach ($vm in $vms) {
        foreach ($d in @(Get-HvProp $vm 'Disks' @())) {
            $chain = @(Get-HvProp $d 'Chain' @())
            for ($i = 1; $i -lt $chain.Count; $i++) {
                $pp = [string]$chain[$i].Path
                if (-not $parents.ContainsKey($pp)) { $parents[$pp] = New-Object System.Collections.ArrayList }
                if ($parents[$pp] -notcontains [string]$vm.Name) { [void]$parents[$pp].Add([string]$vm.Name) }
            }
        }
    }
    foreach ($pp in @($parents.Keys | Sort-Object)) {
        if ($parents[$pp].Count -ge 2) {
            [void]$out.Add((New-HvFinding $hostName Info 'SharedParentDisk' "$($parents[$pp].Count) VMs ($($parents[$pp] -join ', ')) are differencing disks of $pp. Never write to, move or delete the parent: every child breaks."))
        }
    }

    @($out | Sort-Object { $script:Severity[$_.Severity] }, Target, Check)
}

function ConvertTo-HvMarkdown {
    [CmdletBinding()]
    param([Parameter(Mandatory)] $Facts, [object[]] $Findings = @())
    $h = $Facts.Host
    $lines = New-Object System.Collections.ArrayList
    [void]$lines.Add("# Hyper-V audit: $($h.ComputerName)")
    [void]$lines.Add('')
    [void]$lines.Add("Collected $($Facts.CollectedUtc) | $($h.Caption) (build $($h.Build)) | default VM configuration version $($h.DefaultVersion)")
    [void]$lines.Add('')
    [void]$lines.Add("$($h.LogicalProcessors) logical processors, $($h.MemoryGB) GB RAM. Default paths: VMs ``$($h.VmPath)``, disks ``$($h.VhdPath)``")
    [void]$lines.Add('')
    [void]$lines.Add('| Volume | Size GB | Free GB |')
    [void]$lines.Add('|---|---|---|')
    foreach ($v in @($h.Volumes)) { [void]$lines.Add("| $($v.Root) | $($v.SizeGB) | $($v.FreeGB) |") }
    [void]$lines.Add('')
    [void]$lines.Add('| VM | State | Gen | Version | vCPU | Start GB | Dynamic | Checkpoint type | Checkpoints | Disk chain | Secure Boot | TPM |')
    [void]$lines.Add('|---|---|---|---|---|---|---|---|---|---|---|---|')
    foreach ($vm in @($Facts.Vms)) {
        $sb = Get-HvProp $vm 'SecureBoot'
        $sbText = 'n/a'; if ($null -ne $sb) { $sbText = $(if ($sb) { 'on' } else { 'off' }) }
        [void]$lines.Add("| $($vm.Name) | $($vm.State) | $($vm.Generation) | $($vm.Version) | $($vm.ProcessorCount) | $($vm.MemoryStartupGB) | $(if ($vm.DynamicMemory) { 'yes' } else { 'no' }) | $($vm.CheckpointType) | $(@($vm.Checkpoints).Count) | $(Get-HvChainDepth -Vm $vm) | $sbText | $(if ($vm.TpmEnabled) { 'yes' } else { 'no' }) |")
    }
    [void]$lines.Add('')
    [void]$lines.Add('## Findings')
    [void]$lines.Add('')
    if (-not $Findings.Count) { [void]$lines.Add('None.') }
    else {
        [void]$lines.Add('| Severity | Target | Check | Message |')
        [void]$lines.Add('|---|---|---|---|')
        foreach ($x in $Findings) { [void]$lines.Add("| $($x.Severity) | $($x.Target) | $($x.Check) | $($x.Message.Replace('|', '\|')) |") }
    }
    ($lines -join "`n") + "`n"
}

# ---------------------------------------------------------------------------------------------------------------
# Build: spec -> plan -> VM
# ---------------------------------------------------------------------------------------------------------------

function Get-HvVmPlan {
    <#
    .SYNOPSIS
    Pure. Turns the TestVm spec into an ordered list of steps (cmdlet + parameters). Throws on an invalid spec.
    .PARAMETER Host
    Host facts (Facts.Host) for the default paths and the default configuration version.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] $Spec, [Parameter(Mandatory)] $HostFacts)
    $name = [string]$Spec.Name
    if ($name -notmatch '^[A-Za-z][A-Za-z0-9-]{0,14}$') { throw "VM name '$name' must be 1 to 15 letters, digits or hyphens and start with a letter." }
    $gen = [int](Get-HvProp $Spec 'Generation' 2)
    if (@(1, 2) -notcontains $gen) { throw "Generation must be 1 or 2, not $gen." }
    $startup = [int64](Get-HvProp $Spec 'MemoryStartupMB' 512) * 1MB
    $min = [int64](Get-HvProp $Spec 'MemoryMinimumMB' 512) * 1MB
    $max = [int64](Get-HvProp $Spec 'MemoryMaximumMB' 1024) * 1MB
    if (-not ($min -le $startup -and $startup -le $max)) { throw 'Memory must satisfy minimum <= startup <= maximum.' }
    $cpu = [int](Get-HvProp $Spec 'ProcessorCount' 2)
    if ($cpu -lt 1 -or $cpu -gt 64) { throw 'ProcessorCount must be between 1 and 64 for this lab builder.' }
    $secureBoot = [bool](Get-HvProp $Spec 'SecureBoot' $true)
    $tpm = [bool](Get-HvProp $Spec 'Tpm' $false)
    $nested = [bool](Get-HvProp $Spec 'NestedVirtualization' $false)
    $version = [string](Get-HvProp $Spec 'Version' '')
    if ($gen -eq 1 -and ($tpm -or (Get-HvProp $Spec 'SecureBoot') -eq $true)) { throw 'Secure Boot and the virtual TPM are generation 2 features (Learn).' }
    if ($nested -and $version -and (ConvertTo-HvVersion $version) -lt (ConvertTo-HvVersion '8.0')) { throw "Nested virtualization needs configuration version 8.0 or higher, not $version." }
    $ctype = [string](Get-HvProp $Spec 'CheckpointType' 'Production')
    if (@('Disabled', 'Standard', 'Production', 'ProductionOnly') -notcontains $ctype) { throw "CheckpointType '$ctype' is not one of Disabled, Standard, Production, ProductionOnly." }

    $root = [string](Get-HvProp $Spec 'Root' '')
    if (-not $root) { $root = [string]$HostFacts.VmPath }
    $vmFolder = $root.TrimEnd('\', '/') + '\' + $name
    $diskRoot = [string]$HostFacts.VhdPath
    $vhd = [string](Get-HvProp $Spec 'VhdPath' '')
    if (-not $vhd) { $vhd = $diskRoot.TrimEnd('\', '/') + '\' + "$name.vhdx" }
    $steps = New-Object System.Collections.ArrayList

    $parent = [string](Get-HvProp $Spec 'ParentVhd' '')
    if ($parent) {
        [void]$steps.Add([pscustomobject]@{ Order = 1; Action = 'CreateDisk'; Cmdlet = 'New-VHD'; Parameters = [ordered]@{ Path = $vhd; ParentPath = $parent; Differencing = $true }; Why = 'Differencing disk: the parent stays untouched and must stay read-only.' })
    }
    else {
        [void]$steps.Add([pscustomobject]@{ Order = 1; Action = 'CreateDisk'; Cmdlet = 'New-VHD'; Parameters = [ordered]@{ Path = $vhd; SizeBytes = ([int64](Get-HvProp $Spec 'DiskGB' 20) * 1GB); Dynamic = $true }; Why = 'Dynamically expanding VHDX.' })
    }
    $newVm = [ordered]@{ Name = $name; Generation = $gen; MemoryStartupBytes = $startup; VHDPath = $vhd; Path = $root }
    $switch = [string](Get-HvProp $Spec 'Switch' '')
    if ($switch) { $newVm.SwitchName = $switch }
    if ($version) { $newVm.Version = $version }
    [void]$steps.Add([pscustomobject]@{ Order = 2; Action = 'CreateVm'; Cmdlet = 'New-VM'; Parameters = $newVm; Why = "Generation $gen VM in $vmFolder." })
    $setVm = [ordered]@{ Name = $name; ProcessorCount = $cpu; DynamicMemory = $true; MemoryMinimumBytes = $min; MemoryMaximumBytes = $max; MemoryStartupBytes = $startup; CheckpointType = $ctype; AutomaticCheckpointsEnabled = [bool](Get-HvProp $Spec 'AutomaticCheckpoints' $false) }
    [void]$steps.Add([pscustomobject]@{ Order = 3; Action = 'ConfigureVm'; Cmdlet = 'Set-VM'; Parameters = $setVm; Why = "Dynamic Memory $([int]($min / 1MB))-$([int]($max / 1MB)) MB, checkpoint type $ctype, automatic checkpoints off unless asked." })
    if ($gen -eq 2) {
        $fw = [ordered]@{ VMName = $name; EnableSecureBoot = $(if ($secureBoot) { 'On' } else { 'Off' }) }
        $tmpl = [string](Get-HvProp $Spec 'SecureBootTemplate' '')
        if ($tmpl) { $fw.SecureBootTemplate = $tmpl }
        [void]$steps.Add([pscustomobject]@{ Order = 4; Action = 'Firmware'; Cmdlet = 'Set-VMFirmware'; Parameters = $fw; Why = 'Secure Boot is on by default for generation 2 (Learn); stated explicitly so the file is the source of truth.' })
    }
    if ($tpm) {
        [void]$steps.Add([pscustomobject]@{ Order = 5; Action = 'KeyProtector'; Cmdlet = 'Set-VMKeyProtector'; Parameters = [ordered]@{ VMName = $name; NewLocalKeyProtector = $true }; Why = 'A virtual TPM needs a key protector first.' })
        [void]$steps.Add([pscustomobject]@{ Order = 6; Action = 'Tpm'; Cmdlet = 'Enable-VMTPM'; Parameters = [ordered]@{ VMName = $name }; Why = 'Virtual TPM (generation 2 only).' })
    }
    if ($nested) {
        [void]$steps.Add([pscustomobject]@{ Order = 7; Action = 'Nested'; Cmdlet = 'Set-VMProcessor'; Parameters = [ordered]@{ VMName = $name; ExposeVirtualizationExtensions = $true }; Why = 'Nested virtualization; the VM must be off (Learn).' })
    }
    $steps
}

function New-HvLabVm {
    <#
    .SYNOPSIS
    Runs Get-HvVmPlan. Skips a VM that already exists (never modifies it) and VHDX files that already exist.
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)] $Spec, [Parameter(Mandatory)] $HostFacts)
    $plan = Get-HvVmPlan -Spec $Spec -HostFacts $HostFacts
    $existing = Get-VM -Name ([string]$Spec.Name) -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Warning "VM '$($Spec.Name)' already exists; nothing changed. Remove it first with Remove-HvLabVm."
        return
    }
    foreach ($s in $plan) {
        $p = @{}
        foreach ($k in $s.Parameters.Keys) { $p[$k] = $s.Parameters[$k] }
        $target = "$($Spec.Name): $($s.Cmdlet)"
        if ($s.Action -eq 'CreateDisk' -and (Test-Path -LiteralPath $s.Parameters['Path'])) { Write-Warning "Disk $($s.Parameters['Path']) exists; leaving it."; continue }
        if (-not $PSCmdlet.ShouldProcess($target, $s.Why)) { continue }
        switch ($s.Action) {
            'CreateDisk' { [void](New-VHD @p) }
            'CreateVm' { [void](New-VM @p) }
            'ConfigureVm' { Set-VM @p }
            'Firmware' { Set-VMFirmware @p }
            'KeyProtector' { Set-VMKeyProtector @p }
            'Tpm' { Enable-VMTPM @p }
            'Nested' { Set-VMProcessor @p }
        }
    }
    Get-VM -Name ([string]$Spec.Name)
}

# ---------------------------------------------------------------------------------------------------------------
# Checkpoints
# ---------------------------------------------------------------------------------------------------------------

function Get-HvCheckpointPlan {
    <#
    .SYNOPSIS
    Pure. Decides which checkpoints of one VM (facts object) to keep and which to delete, oldest first.
    Keeps the newest -KeepNewest and anything whose name starts with -ProtectedPrefix; deletes the rest older than -MaxAgeDays.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] $Vm,
        [int] $KeepNewest = 1,
        [double] $MaxAgeDays = 7,
        [string] $ProtectedPrefix = 'KEEP-',
        [datetime] $Now = (Get-Date)
    )
    $rows = @(@(Get-HvProp $Vm 'Checkpoints' @()) | ForEach-Object {
            $created = ([datetime]::Parse([string]$_.CreatedUtc, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::RoundtripKind)).ToUniversalTime()
            [pscustomobject]@{ Name = [string]$_.Name; CreatedUtc = $created; AgeDays = [math]::Round(($Now.ToUniversalTime() - $created).TotalDays, 1) }
        } | Sort-Object CreatedUtc)
    $newest = @($rows | Sort-Object CreatedUtc -Descending | Select-Object -First $KeepNewest | ForEach-Object Name)
    foreach ($r in $rows) {
        $action = 'Remove'; $reason = "older than $MaxAgeDays days"
        if ($ProtectedPrefix -and $r.Name.StartsWith($ProtectedPrefix, [StringComparison]::OrdinalIgnoreCase)) { $action = 'Keep'; $reason = "name starts with $ProtectedPrefix" }
        elseif ($newest -contains $r.Name) { $action = 'Keep'; $reason = "one of the newest $KeepNewest" }
        elseif ($r.AgeDays -lt $MaxAgeDays) { $action = 'Keep'; $reason = "younger than $MaxAgeDays days" }
        [pscustomobject]@{ VM = [string]$Vm.Name; Checkpoint = $r.Name; AgeDays = $r.AgeDays; Action = $action; Reason = $reason }
    }
}

function Get-HvLiveChainDepth {
    # files in the longest chain of the VM's attached disks, read live
    param([string] $VmName)
    $max = 0
    foreach ($d in @(Get-VMHardDiskDrive -VMName $VmName)) {
        $n = 0
        $cur = [string]$d.Path
        while ($cur -and $n -lt 64) {
            $n++
            $cur = [string](Get-VHD -Path $cur).ParentPath
        }
        if ($n -gt $max) { $max = $n }
    }
    $max
}

function Wait-HvDiskMerge {
    <#
    .SYNOPSIS
    After Remove-VMCheckpoint Hyper-V merges the .avhdx files in the background (Learn). Polls the live disk chain until it
    has shrunk to -ExpectedDepth files, or warns after -TimeoutSeconds. Never deletes anything.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [string] $VmName,
        [Parameter(Mandatory)] [int] $ExpectedDepth,
        [int] $TimeoutSeconds = 600,
        [scriptblock] $Sleep = { param($s) Start-Sleep -Seconds $s }
    )
    $waited = 0
    while ($true) {
        $depth = Get-HvLiveChainDepth -VmName $VmName
        if ($depth -le $ExpectedDepth) { return [pscustomobject]@{ VM = $VmName; Merged = $true; ChainDepth = $depth; WaitedSeconds = $waited } }
        if ($waited -ge $TimeoutSeconds) {
            Write-Warning "${VmName}: disk chain still has $depth files after $TimeoutSeconds s (expected $ExpectedDepth). The merge may still be running; check again later. Do not delete .avhdx files by hand."
            return [pscustomobject]@{ VM = $VmName; Merged = $false; ChainDepth = $depth; WaitedSeconds = $waited }
        }
        & $Sleep 5
        $waited += 5
    }
}

function Invoke-HvCheckpointCleanup {
    <#
    .SYNOPSIS
    Applies Get-HvCheckpointPlan to one VM with Remove-VMCheckpoint (one at a time, oldest first), then waits for the merge.
    #>
    [CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
    param(
        [Parameter(Mandatory)] [string] $VmName,
        [int] $KeepNewest = 1,
        [double] $MaxAgeDays = 7,
        [string] $ProtectedPrefix = 'KEEP-',
        [int] $TimeoutSeconds = 600,
        [datetime] $Now = (Get-Date),
        [scriptblock] $Sleep = { param($s) Start-Sleep -Seconds $s }
    )
    $facts = [pscustomobject]@{
        Name        = $VmName
        Checkpoints = @(Get-VMSnapshot -VMName $VmName | ForEach-Object {
                [pscustomobject]@{ Name = [string]$_.Name; CreatedUtc = $_.CreationTime.ToUniversalTime().ToString('o') }
            })
    }
    $plan = @(Get-HvCheckpointPlan -Vm $facts -KeepNewest $KeepNewest -MaxAgeDays $MaxAgeDays -ProtectedPrefix $ProtectedPrefix -Now $Now)
    $remove = @($plan | Where-Object Action -eq 'Remove')
    $baseDepth = (Get-HvLiveChainDepth -VmName $VmName) - $plan.Count
    foreach ($r in $remove) {
        if ($PSCmdlet.ShouldProcess("$VmName/$($r.Checkpoint)", 'Remove-VMCheckpoint (Hyper-V merges the .avhdx files afterwards)')) {
            Remove-VMCheckpoint -VMName $VmName -Name $r.Checkpoint
        }
    }
    $merge = $null
    if ($remove.Count -and -not $WhatIfPreference) {
        $keep = $plan.Count - $remove.Count
        $merge = Wait-HvDiskMerge -VmName $VmName -ExpectedDepth ([math]::Max(1, $baseDepth + $keep)) -TimeoutSeconds $TimeoutSeconds -Sleep $Sleep
    }
    [pscustomobject]@{ VM = $VmName; Plan = $plan; Removed = $remove.Count; Merge = $merge }
}

# ---------------------------------------------------------------------------------------------------------------
# Tear-down
# ---------------------------------------------------------------------------------------------------------------

function Remove-HvLabVm {
    <#
    .SYNOPSIS
    Turns the VM off, removes it, then deletes its VM folder and its disks, but only files under -LabRoot or the host's
    default VHD path. Refuses to touch a VM whose name is not on the allow list.
    #>
    [CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
    param(
        [Parameter(Mandatory)] [string] $Name,
        [Parameter(Mandatory)] [string[]] $AllowedNames,
        [Parameter(Mandatory)] [string[]] $AllowedRoots
    )
    if ($AllowedNames -notcontains $Name) { throw "Refusing to remove '$Name': not on the allow list ($($AllowedNames -join ', '))." }
    $vm = Get-VM -Name $Name -ErrorAction SilentlyContinue
    if (-not $vm) { Write-Warning "VM '$Name' does not exist."; return }
    $disks = @(Get-VMHardDiskDrive -VMName $Name | ForEach-Object { [string]$_.Path })
    # checkpoint files: take the whole chain, so no .avhdx is left behind
    $files = New-Object System.Collections.ArrayList
    foreach ($d in $disks) {
        $cur = $d; $n = 0
        while ($cur -and $n -lt 64) {
            $n++
            [void]$files.Add($cur)
            $cur = [string](Get-VHD -Path $cur).ParentPath
        }
    }
    $outside = @($files | Where-Object { $f = $_; -not @($AllowedRoots | Where-Object { Test-HvUnder -Path $f -Root $_ }).Count })
    if ($outside.Count) { throw "Refusing to delete disk(s) outside the allowed roots: $($outside -join '; ')." }
    if (-not $PSCmdlet.ShouldProcess($Name, "Turn off, remove the VM and delete $($files.Count) disk file(s)")) { return }
    if ([string]$vm.State -ne 'Off') { Stop-VM -Name $Name -TurnOff -Force }
    $folder = [string]$vm.Path
    Remove-VM -Name $Name -Force
    foreach ($f in $files) { Remove-Item -LiteralPath $f -Force -ErrorAction SilentlyContinue }
    if ($folder -and @($AllowedRoots | Where-Object { Test-HvUnder -Path $folder -Root $_ }).Count -and (Test-Path -LiteralPath $folder)) {
        Remove-Item -LiteralPath $folder -Recurse -Force -ErrorAction SilentlyContinue
    }
    [pscustomobject]@{ VM = $Name; DisksDeleted = $files.Count; Folder = $folder }
}

Export-ModuleMember -Function Read-HvLabConfig, Get-HvCollectorScript, Get-HvHostFacts, Test-HvHost, ConvertTo-HvMarkdown,
    Get-HvChainDepth, Get-HvVmPlan, New-HvLabVm, Get-HvCheckpointPlan, Wait-HvDiskMerge, Invoke-HvCheckpointCleanup, Remove-HvLabVm
