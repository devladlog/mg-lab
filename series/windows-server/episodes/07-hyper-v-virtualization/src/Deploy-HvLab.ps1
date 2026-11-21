<#
.SYNOPSIS
Builds, exercises and removes the throwaway VM from hv-lab.json on THIS Hyper-V host (elevated, Hyper-V module installed).
.DESCRIPTION
 -Step Create       New-HvLabVm: disk, VM, memory, checkpoint type, Secure Boot, virtual TPM (use -WhatIf first)
 -Step Checkpoints  takes CheckpointDemo.Count checkpoints (demo-1 ..) plus one protected KEEP-baseline, shows the disk chain
 -Step Cleanup      Get-HvCheckpointPlan + Remove-VMCheckpoint + wait for the merge (use -WhatIf first)
 -Step Remove       turns the VM off and deletes it and its disks; only the VM named in TestVm, only under the host's default paths
#>
[CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'Medium')]
param(
    [Parameter(Mandatory)] [ValidateSet('Create', 'Checkpoints', 'Cleanup', 'Remove')] [string] $Step,
    [string] $ConfigPath = (Join-Path $PSScriptRoot 'hv-lab.json'),
    [switch] $Start
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'HvLab/HvLab.psd1') -Force
$config = Read-HvLabConfig -Path $ConfigPath
$vmh = Get-VMHost
$hostFacts = [pscustomobject]@{ VmPath = [string]$vmh.VirtualMachinePath; VhdPath = [string]$vmh.VirtualHardDiskPath }
$name = [string]$config.TestVm.Name
$demo = $config.CheckpointDemo

switch ($Step) {
    'Create' {
        New-HvLabVm -Spec $config.TestVm -HostFacts $hostFacts -WhatIf:$WhatIfPreference | Format-List Name, State, Generation, Version, ProcessorCount, DynamicMemoryEnabled, CheckpointType
    }
    'Checkpoints' {
        if ($Start -and (Get-VM -Name $name).State -ne 'Running') { Start-VM -Name $name }
        for ($i = 1; $i -le [int]$demo.Count; $i++) {
            if ($PSCmdlet.ShouldProcess($name, "Checkpoint-VM $($demo.NamePrefix)$i")) { Checkpoint-VM -Name $name -SnapshotName "$($demo.NamePrefix)$i" }
        }
        if ($PSCmdlet.ShouldProcess($name, "Checkpoint-VM $($demo.ProtectedPrefix)baseline")) { Checkpoint-VM -Name $name -SnapshotName "$($demo.ProtectedPrefix)baseline" }
        Get-VMSnapshot -VMName $name | Format-Table Name, SnapshotType, CreationTime, ParentSnapshotName
        Get-VMHardDiskDrive -VMName $name | ForEach-Object { Get-VHD -Path $_.Path } | Format-List Path, VhdType, ParentPath, FileSize, Size
    }
    'Cleanup' {
        Invoke-HvCheckpointCleanup -VmName $name -KeepNewest ([int]$demo.KeepNewest) -MaxAgeDays ([double]$demo.MaxAgeDays) -ProtectedPrefix ([string]$demo.ProtectedPrefix) -WhatIf:$WhatIfPreference -Confirm:$false |
            ForEach-Object { $_.Plan | Format-Table VM, Checkpoint, AgeDays, Action, Reason; $_.Merge }
    }
    'Remove' {
        Remove-HvLabVm -Name $name -AllowedNames @($name) -AllowedRoots @($hostFacts.VmPath, $hostFacts.VhdPath) -WhatIf:$WhatIfPreference -Confirm:$false
    }
}
