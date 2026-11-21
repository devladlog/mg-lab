using namespace System.Management.Automation.Language

BeforeAll {
    $script:Src = Join-Path $PSScriptRoot '../src'
    $script:Fixtures = Join-Path $PSScriptRoot 'fixtures'
    Import-Module (Join-Path $script:Src 'HvLab/HvLab.psd1') -Force
    $script:ConfigPath = Join-Path $script:Src 'hv-lab.json'
    $script:Config = Read-HvLabConfig -Path $script:ConfigPath
    $script:Now = [datetime]::new(2026, 11, 20, 9, 0, 0, [DateTimeKind]::Utc)
    function Get-Facts([string] $Name) { Get-Content -Raw (Join-Path $script:Fixtures "$Name.json") | ConvertFrom-Json }
    function Get-Checks($Findings, [string] $Target) { @($Findings | Where-Object { $_.Target -eq $Target } | ForEach-Object Check) }
    $script:HostFacts = [pscustomobject]@{ VmPath = 'E:\MGLab\VMs'; VhdPath = 'E:\MGLab\VHDs' }

    # Hyper-V cmdlets do not exist on Linux: stubs (with the parameter names the module uses) so that Pester can mock them
    $script:StubBody = {
        [CmdletBinding()]
        param($Name, $VMName, $Path, $Generation, $SizeBytes, $ParentPath, $Differencing, $Dynamic, $MemoryStartupBytes, $VHDPath, $SwitchName,
            $Version, $ProcessorCount, $DynamicMemory, $MemoryMinimumBytes, $MemoryMaximumBytes, $CheckpointType, $AutomaticCheckpointsEnabled,
            $EnableSecureBoot, $SecureBootTemplate, [switch] $NewLocalKeyProtector, $ExposeVirtualizationExtensions, [switch] $TurnOff, [switch] $Force)
    }
    foreach ($n in 'Get-VM', 'New-VHD', 'New-VM', 'Set-VM', 'Set-VMFirmware', 'Set-VMKeyProtector', 'Enable-VMTPM', 'Set-VMProcessor',
        'Get-VMSnapshot', 'Remove-VMCheckpoint', 'Get-VMHardDiskDrive', 'Get-VHD', 'Stop-VM', 'Remove-VM') {
        Set-Item -Path "function:global:$n" -Value $script:StubBody
    }
}

AfterAll {
    foreach ($n in 'Get-VM', 'New-VHD', 'New-VM', 'Set-VM', 'Set-VMFirmware', 'Set-VMKeyProtector', 'Enable-VMTPM', 'Set-VMProcessor',
        'Get-VMSnapshot', 'Remove-VMCheckpoint', 'Get-VMHardDiskDrive', 'Get-VHD', 'Stop-VM', 'Remove-VM') {
        Remove-Item "function:global:$n" -ErrorAction SilentlyContinue
    }
}

Describe 'Read-HvLabConfig' {
    It 'reads the lab config' {
        $script:Config.TestVm.Name | Should -Be 'CON-HVT01'
        $script:Config.Policy.MaxCheckpoints | Should -Be 3
    }
    It 'rejects a wrong schema version and a missing section' {
        $f = Join-Path $TestDrive 'c.json'
        '{"SchemaVersion":2}' | Set-Content $f
        { Read-HvLabConfig -Path $f } | Should -Throw '*SchemaVersion*'
        '{"SchemaVersion":1,"Policy":{}}' | Set-Content $f
        { Read-HvLabConfig -Path $f } | Should -Throw "*missing 'TestVm'*"
    }
}

Describe 'Test-HvHost on the lab host' {
    BeforeAll { $script:Lab = @(Test-HvHost -Facts (Get-Facts 'host-facts-lab') -Config $script:Config -Now $script:Now) }
    It 'has no finding above Info' {
        @($script:Lab | Where-Object Severity -ne 'Info').Count | Should -Be 0
    }
    It 'reports the shared parent disk once, as Info' {
        $p = @($script:Lab | Where-Object Check -eq 'SharedParentDisk')
        $p.Count | Should -Be 1
        $p[0].Message | Should -BeLike '*CON-DC01*CON-SQL01*ws2025-core.vhdx*'
    }
}

Describe 'Test-HvHost on the problem host' {
    BeforeAll { $script:Bad = @(Test-HvHost -Facts (Get-Facts 'host-facts-bad') -Config $script:Config -Now $script:Now) }
    It 'finds 24 problems, 7 of them High' {
        $script:Bad.Count | Should -Be 24
        @($script:Bad | Where-Object Severity -eq 'High').Count | Should -Be 7
    }
    It 'flags a domain controller with a very old Standard checkpoint' {
        Get-Checks $script:Bad 'CON-DC01' | Should -Contain 'CheckpointVeryOld'
        Get-Checks $script:Bad 'CON-DC01' | Should -Contain 'StandardCheckpointOnDc'
    }
    It 'flags the VM at the 50 checkpoint limit and the broken chain' {
        Get-Checks $script:Bad 'SCRATCH-50' | Should -Contain 'CheckpointLimit'
        Get-Checks $script:Bad 'BROKEN-01' | Should -Contain 'BrokenDiskChain'
    }
    It 'flags nested virtualization on a too-old configuration version, and only notes Dynamic Memory' {
        ($script:Bad | Where-Object { $_.Target -eq 'LAB-NEST01' -and $_.Check -eq 'NestedNeedsVersion' }).Severity | Should -Be 'High'
        ($script:Bad | Where-Object { $_.Target -eq 'LAB-NEST01' -and $_.Check -eq 'NestedWithDynamicMemory' }).Severity | Should -Be 'Info'
    }
    It 'flags Production checkpoints without VSS and a replication problem' {
        Get-Checks $script:Bad 'BUILD-AGENT' | Should -Contain 'ProductionWithoutVss'
        Get-Checks $script:Bad 'REPL-SQL' | Should -Contain 'ReplicationUnhealthy'
    }
    It 'flags host overcommit' {
        Get-Checks $script:Bad 'HV-OLD01' | Should -Contain 'DiskOvercommit'
    }
    It 'sorts High first' {
        $script:Bad[0].Severity | Should -Be 'High'
        $script:Bad[-1].Severity | Should -Be 'Info'
    }
    It 'does not flag a configuration or domain controller rule when the policy lists no DCs' {
        $c = Get-Content -Raw $script:ConfigPath | ConvertFrom-Json
        $c.Policy.DomainControllers = @()
        $r = @(Test-HvHost -Facts (Get-Facts 'host-facts-bad') -Config $c -Now $script:Now)
        Get-Checks $r 'CON-DC01' | Should -Not -Contain 'StandardCheckpointOnDc'
    }
}

Describe 'ConvertTo-HvMarkdown' {
    It 'renders the host, the VM table and the findings' {
        $f = Get-Facts 'host-facts-bad'
        $md = ConvertTo-HvMarkdown -Facts $f -Findings @(Test-HvHost -Facts $f -Config $script:Config -Now $script:Now)
        $md | Should -BeLike '# Hyper-V audit: HV-OLD01*'
        $md | Should -BeLike '*| SCRATCH-50 |*'
        $md | Should -BeLike '*## Findings*'
    }
    It 'says so when there is nothing to report' {
        $f = Get-Facts 'host-facts-lab'
        (ConvertTo-HvMarkdown -Facts $f -Findings @()) | Should -BeLike '*# Hyper-V audit: LAB-LAPTOP*'
    }
}

Describe 'Get-HvVmPlan' {
    It 'plans the lab VM in order: disk, VM, settings, firmware, key protector, TPM' {
        $plan = Get-HvVmPlan -Spec $script:Config.TestVm -HostFacts $script:HostFacts
        ($plan | ForEach-Object Cmdlet) | Should -Be @('New-VHD', 'New-VM', 'Set-VM', 'Set-VMFirmware', 'Set-VMKeyProtector', 'Enable-VMTPM')
        $plan[0].Parameters['Path'] | Should -Be 'E:\MGLab\VHDs\CON-HVT01.vhdx'
        $plan[0].Parameters['SizeBytes'] | Should -Be (20GB)
        $plan[1].Parameters['Generation'] | Should -Be 2
        $plan[2].Parameters['MemoryMinimumBytes'] | Should -Be (512MB)
        $plan[2].Parameters['CheckpointType'] | Should -Be 'Production'
        $plan[2].Parameters['AutomaticCheckpointsEnabled'] | Should -BeFalse
    }
    It 'uses a differencing disk when a parent is given' {
        $s = [pscustomobject]@{ Name = 'T1'; ParentVhd = 'E:\base\p.vhdx' }
        $plan = Get-HvVmPlan -Spec $s -HostFacts $script:HostFacts
        $plan[0].Parameters['Differencing'] | Should -BeTrue
        $plan[0].Parameters['ParentPath'] | Should -Be 'E:\base\p.vhdx'
    }
    It 'adds the nested step last' {
        $s = [pscustomobject]@{ Name = 'T2'; NestedVirtualization = $true; Version = '9.0' }
        $plan = Get-HvVmPlan -Spec $s -HostFacts $script:HostFacts
        $plan[-1].Cmdlet | Should -Be 'Set-VMProcessor'
        $plan[-1].Parameters['ExposeVirtualizationExtensions'] | Should -BeTrue
    }
    It 'leaves out firmware and TPM on generation 1' {
        $s = [pscustomobject]@{ Name = 'T3'; Generation = 1; SecureBoot = $false }
        $plan = Get-HvVmPlan -Spec $s -HostFacts $script:HostFacts
        ($plan | ForEach-Object Cmdlet) | Should -Be @('New-VHD', 'New-VM', 'Set-VM')
    }
    It 'rejects bad specs' {
        { Get-HvVmPlan -Spec ([pscustomobject]@{ Name = '1bad' }) -HostFacts $script:HostFacts } | Should -Throw '*1 to 15*'
        { Get-HvVmPlan -Spec ([pscustomobject]@{ Name = 'ok'; Generation = 3 }) -HostFacts $script:HostFacts } | Should -Throw '*Generation*'
        { Get-HvVmPlan -Spec ([pscustomobject]@{ Name = 'ok'; MemoryStartupMB = 256; MemoryMinimumMB = 512 }) -HostFacts $script:HostFacts } | Should -Throw '*minimum*'
        { Get-HvVmPlan -Spec ([pscustomobject]@{ Name = 'ok'; Generation = 1; Tpm = $true }) -HostFacts $script:HostFacts } | Should -Throw '*generation 2*'
        { Get-HvVmPlan -Spec ([pscustomobject]@{ Name = 'ok'; NestedVirtualization = $true; Version = '7.0' }) -HostFacts $script:HostFacts } | Should -Throw '*8.0*'
        { Get-HvVmPlan -Spec ([pscustomobject]@{ Name = 'ok'; CheckpointType = 'Fancy' }) -HostFacts $script:HostFacts } | Should -Throw '*CheckpointType*'
    }
}

Describe 'New-HvLabVm' {
    BeforeEach {
        Mock -ModuleName HvLab Get-VM { $null }
        Mock -ModuleName HvLab Test-Path { $false }
        foreach ($c in 'New-VHD', 'New-VM', 'Set-VM', 'Set-VMFirmware', 'Set-VMKeyProtector', 'Enable-VMTPM', 'Set-VMProcessor') {
            Mock -ModuleName HvLab $c { }
        }
    }
    It 'runs every planned cmdlet once' {
        New-HvLabVm -Spec $script:Config.TestVm -HostFacts $script:HostFacts | Out-Null
        foreach ($c in 'New-VHD', 'New-VM', 'Set-VM', 'Set-VMFirmware', 'Set-VMKeyProtector', 'Enable-VMTPM') {
            Should -Invoke -ModuleName HvLab $c -Times 1 -Exactly
        }
        Should -Invoke -ModuleName HvLab Set-VMProcessor -Times 0 -Exactly
        Should -Invoke -ModuleName HvLab New-VM -Times 1 -Exactly -ParameterFilter { $Name -eq 'CON-HVT01' -and $Generation -eq 2 }
    }
    It 'changes nothing with -WhatIf' {
        New-HvLabVm -Spec $script:Config.TestVm -HostFacts $script:HostFacts -WhatIf | Out-Null
        Should -Invoke -ModuleName HvLab New-VHD -Times 0 -Exactly
        Should -Invoke -ModuleName HvLab New-VM -Times 0 -Exactly
    }
    It 'leaves an existing VM alone' {
        Mock -ModuleName HvLab Get-VM { [pscustomobject]@{ Name = 'CON-HVT01' } }
        New-HvLabVm -Spec $script:Config.TestVm -HostFacts $script:HostFacts -WarningAction SilentlyContinue | Out-Null
        Should -Invoke -ModuleName HvLab New-VM -Times 0 -Exactly
        Should -Invoke -ModuleName HvLab Set-VM -Times 0 -Exactly
    }
    It 'does not touch a disk that already exists' {
        Mock -ModuleName HvLab Test-Path { $true }
        New-HvLabVm -Spec $script:Config.TestVm -HostFacts $script:HostFacts -WarningAction SilentlyContinue | Out-Null
        Should -Invoke -ModuleName HvLab New-VHD -Times 0 -Exactly
    }
}

Describe 'Get-HvCheckpointPlan' {
    BeforeAll {
        $mk = { param($n, $days) [pscustomobject]@{ Name = $n; CreatedUtc = $script:Now.AddDays(-$days).ToString('o') } }
        $script:Vm = [pscustomobject]@{ Name = 'V'; Checkpoints = @((& $mk 'old' 40), (& $mk 'KEEP-base' 90), (& $mk 'mid' 10), (& $mk 'new' 1)) }
    }
    It 'removes old unprotected checkpoints, oldest first' {
        $p = @(Get-HvCheckpointPlan -Vm $script:Vm -KeepNewest 1 -MaxAgeDays 7 -Now $script:Now)
        ($p | ForEach-Object Checkpoint) | Should -Be @('KEEP-base', 'old', 'mid', 'new')
        ($p | Where-Object Action -eq 'Remove' | ForEach-Object Checkpoint) | Should -Be @('old', 'mid')
    }
    It 'never removes a protected name, even the oldest' {
        $p = @(Get-HvCheckpointPlan -Vm $script:Vm -KeepNewest 0 -MaxAgeDays 0 -Now $script:Now)
        ($p | Where-Object Checkpoint -eq 'KEEP-base').Action | Should -Be 'Keep'
    }
    It 'keeps what is younger than the age limit' {
        $p = @(Get-HvCheckpointPlan -Vm $script:Vm -KeepNewest 0 -MaxAgeDays 30 -Now $script:Now)
        ($p | Where-Object Checkpoint -eq 'mid').Action | Should -Be 'Keep'
        ($p | Where-Object Checkpoint -eq 'old').Action | Should -Be 'Remove'
    }
    It 'returns nothing for a VM without checkpoints' {
        @(Get-HvCheckpointPlan -Vm ([pscustomobject]@{ Name = 'E'; Checkpoints = @() }) -Now $script:Now).Count | Should -Be 0
    }
}

Describe 'Wait-HvDiskMerge and Invoke-HvCheckpointCleanup' {
    BeforeEach {
        $global:HvT = @{ Depth = 4; Removed = @(); Calls = 0 }
        Mock -ModuleName HvLab Get-VMHardDiskDrive { [pscustomobject]@{ Path = 'E:\VHDs\v.avhdx' } }
        # a chain of $global:HvT.Depth files: path 'p<n>' has parent 'p<n-1>'
        Mock -ModuleName HvLab Get-VHD {
            $global:HvT.Calls++
            [pscustomobject]@{ ParentPath = $null }
        }
        Mock -ModuleName HvLab Get-HvLiveChainDepth { $d = $global:HvT.Depth; if ($global:HvT.Depth -gt $global:HvT.Target) { $global:HvT.Depth-- }; $d }
        Mock -ModuleName HvLab Get-VMSnapshot {
            foreach ($n in 'demo-1', 'demo-2', 'KEEP-baseline') { [pscustomobject]@{ Name = $n; CreationTime = [datetime]::UtcNow.AddMinutes(-5) } }
        }
        Mock -ModuleName HvLab Remove-VMCheckpoint { $global:HvT.Removed += $Name }
    }
    AfterEach { Remove-Variable HvT -Scope Global -ErrorAction SilentlyContinue }
    It 'Wait returns Merged once the chain is short enough' {
        $global:HvT.Target = 2
        $r = Wait-HvDiskMerge -VmName V -ExpectedDepth 2 -Sleep { param($s) }
        $r.Merged | Should -BeTrue
        $r.ChainDepth | Should -Be 2
        $r.WaitedSeconds | Should -Be 10
    }
    It 'Wait warns and returns Merged false on timeout, without deleting anything' {
        $global:HvT.Target = 4
        $r = Wait-HvDiskMerge -VmName V -ExpectedDepth 1 -TimeoutSeconds 10 -Sleep { param($s) } -WarningVariable w -WarningAction SilentlyContinue
        $r.Merged | Should -BeFalse
        "$w" | Should -BeLike '*Do not delete .avhdx files by hand*'
    }
    It 'Cleanup removes only the unprotected checkpoints and waits for the merge' {
        $global:HvT.Target = 1
        $r = Invoke-HvCheckpointCleanup -VmName V -KeepNewest 0 -MaxAgeDays 0 -Confirm:$false -Sleep { param($s) }
        $r.Removed | Should -Be 2
        $global:HvT.Removed | Should -Be @('demo-1', 'demo-2')
        $r.Merge.Merged | Should -BeTrue
        ($r.Plan | Where-Object Checkpoint -eq 'KEEP-baseline').Action | Should -Be 'Keep'
    }
    It 'Cleanup -WhatIf removes nothing and does not wait' {
        $global:HvT.Target = 1
        $r = Invoke-HvCheckpointCleanup -VmName V -KeepNewest 0 -MaxAgeDays 0 -WhatIf
        $global:HvT.Removed.Count | Should -Be 0
        $r.Merge | Should -BeNullOrEmpty
        Should -Invoke -ModuleName HvLab Remove-VMCheckpoint -Times 0 -Exactly
    }
}

Describe 'Remove-HvLabVm' {
    BeforeEach {
        Mock -ModuleName HvLab Get-VM { [pscustomobject]@{ Name = 'CON-HVT01'; State = 'Running'; Path = 'E:\MGLab\VMs\CON-HVT01' } }
        Mock -ModuleName HvLab Get-VMHardDiskDrive { [pscustomobject]@{ Path = 'E:\MGLab\VHDs\CON-HVT01_x.avhdx' } }
        Mock -ModuleName HvLab Get-VHD {
            if ($Path -like '*.avhdx') { [pscustomobject]@{ ParentPath = 'E:\MGLab\VHDs\CON-HVT01.vhdx' } } else { [pscustomobject]@{ ParentPath = '' } }
        }
        Mock -ModuleName HvLab Stop-VM { }
        Mock -ModuleName HvLab Remove-VM { }
        Mock -ModuleName HvLab Remove-Item { }
        Mock -ModuleName HvLab Test-Path { $true }
    }
    It 'refuses a VM that is not on the allow list' {
        { Remove-HvLabVm -Name 'CON-DC01' -AllowedNames 'CON-HVT01' -AllowedRoots 'E:\MGLab' -Confirm:$false } | Should -Throw '*allow list*'
        Should -Invoke -ModuleName HvLab Remove-VM -Times 0 -Exactly
    }
    It 'refuses when a disk of the chain is outside the allowed roots' {
        { Remove-HvLabVm -Name 'CON-HVT01' -AllowedNames 'CON-HVT01' -AllowedRoots 'E:\Other' -Confirm:$false } | Should -Throw '*outside the allowed roots*'
        Should -Invoke -ModuleName HvLab Remove-Item -Times 0 -Exactly
    }
    It 'turns the VM off, removes it and deletes the whole chain and the folder' {
        $r = Remove-HvLabVm -Name 'CON-HVT01' -AllowedNames 'CON-HVT01' -AllowedRoots 'E:\MGLab' -Confirm:$false
        $r.DisksDeleted | Should -Be 2
        Should -Invoke -ModuleName HvLab Stop-VM -Times 1 -Exactly
        Should -Invoke -ModuleName HvLab Remove-VM -Times 1 -Exactly
        Should -Invoke -ModuleName HvLab Remove-Item -Times 3 -Exactly
    }
    It 'does nothing with -WhatIf' {
        Remove-HvLabVm -Name 'CON-HVT01' -AllowedNames 'CON-HVT01' -AllowedRoots 'E:\MGLab' -WhatIf | Out-Null
        Should -Invoke -ModuleName HvLab Remove-VM -Times 0 -Exactly
    }
    It 'treats a path that only starts with the root name as outside it' {
        Mock -ModuleName HvLab Get-VMHardDiskDrive { [pscustomobject]@{ Path = 'E:\MGLab-evil\x.vhdx' } }
        { Remove-HvLabVm -Name 'CON-HVT01' -AllowedNames 'CON-HVT01' -AllowedRoots 'E:\MGLab' -Confirm:$false } | Should -Throw '*outside*'
    }
}

Describe 'Collector script block' {
    BeforeAll {
        $script:Ast = [Parser]::ParseInput((Get-HvCollectorScript).ToString(), [ref]$null, [ref]$null)
    }
    It 'parses and is self-contained (calls no HvLab function)' {
        $cmds = @($script:Ast.FindAll({ param($n) $n -is [CommandAst] }, $true) | ForEach-Object { $_.GetCommandName() } | Where-Object { $_ })
        @($cmds | Where-Object { $_ -match '-Hv' }).Count | Should -Be 0
    }
    It 'is read-only: calls no Set-, New-, Remove-, Start-, Stop- or Checkpoint- cmdlet' {
        $cmds = @($script:Ast.FindAll({ param($n) $n -is [CommandAst] }, $true) | ForEach-Object { $_.GetCommandName() } | Where-Object { $_ })
        @($cmds | Where-Object { $_ -match '^(Set|New|Remove|Start|Stop|Checkpoint|Restore|Enable|Disable|Merge|Resize|Convert|Import|Export)-' -and $_ -ne 'New-Object' }).Count | Should -Be 0
    }
}

Describe 'Entry scripts' {
    It 'Invoke-HvAudit prints the summary line for a fixture' {
        $out = & (Join-Path $script:Src 'Invoke-HvAudit.ps1') -FromFacts (Join-Path $script:Fixtures 'host-facts-bad.json') -Now $script:Now
        ($out | Select-Object -Last 1) | Should -Be 'HV-OLD01: 7 VM(s), 24 finding(s), 7 high.'
    }
    It 'Deploy-HvLab and Invoke-HvAudit parse cleanly' {
        foreach ($f in 'Deploy-HvLab.ps1', 'Invoke-HvAudit.ps1') {
            $errs = $null
            [void][Parser]::ParseFile((Join-Path $script:Src $f), [ref]$null, [ref]$errs)
            $errs.Count | Should -Be 0
        }
    }
}
