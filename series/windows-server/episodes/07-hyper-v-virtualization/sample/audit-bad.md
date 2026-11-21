# Hyper-V audit: HV-OLD01

Collected 11/20/2026 08:55:00 | Microsoft Windows Server 2025 Standard (build 26100) | default VM configuration version 12.0

8 logical processors, 64 GB RAM. Default paths: VMs `C:\ProgramData\Microsoft\Windows\Hyper-V`, disks `C:\Users\Public\Documents\Hyper-V\Virtual hard disks`

| Volume | Size GB | Free GB |
|---|---|---|
| C:\ | 200 | 60 |
| E:\ | 1000 | 95 |

| VM | State | Gen | Version | vCPU | Start GB | Dynamic | Checkpoint type | Checkpoints | Disk chain | Secure Boot | TPM |
|---|---|---|---|---|---|---|---|---|---|---|---|
| CON-DC01 | Running | 2 | 12.0 | 2 | 2 | yes | Standard | 2 | 1 | on | no |
| LEGACY-APP | Running | 1 | 8.0 | 4 | 4 | no | Production | 0 | 1 | n/a | no |
| LAB-NEST01 | Running | 2 | 7.0 | 8 | 8 | yes | Production | 0 | 1 | on | no |
| BUILD-AGENT | Running | 2 | 12.0 | 8 | 16 | no | Production | 5 | 1 | off | no |
| REPL-SQL | Running | 2 | 12.0 | 8 | 24 | no | Production | 0 | 1 | on | no |
| SCRATCH-50 | Running | 2 | 12.0 | 8 | 4 | yes | Production | 50 | 1 | on | no |
| BROKEN-01 | Off | 2 | 12.0 | 2 | 2 | yes | Production | 0 | 2 | on | no |

## Findings

| Severity | Target | Check | Message |
|---|---|---|---|
| High | BROKEN-01 | BrokenDiskChain | Cannot read 'E:\gone\parent.vhdx': a parent disk was moved, deleted or is locked. Restore it before the VM is started. |
| High | CON-DC01 | CheckpointVeryOld | Checkpoint 'before-adprep' is 45 days old (policy: 30). Checkpoints are for hours or days, not a backup. |
| High | CON-DC01 | StandardCheckpointOnDc | Standard checkpoints can cause data consistency issues with systems that replicate data between nodes such as Active Directory (Learn). Use Production or turn checkpoints off for domain controllers. |
| High | HV-OLD01 | DiskOvercommit | Dynamic and differencing disks on E:\ can still grow by 714 GB but only 95 GB are free: if the guests fill their disks, the VMs pause with a critical error. |
| High | LAB-NEST01 | NestedNeedsVersion | Nested virtualization needs configuration version 8.0 or higher (Learn); this VM is 7.0. |
| High | REPL-SQL | ReplicationUnhealthy | Hyper-V Replica health is Critical (state Error). |
| High | SCRATCH-50 | CheckpointLimit | 50 checkpoints: Learn's maximum is 50, dependent on available storage. |
| Medium | BUILD-AGENT | CheckpointOld | Checkpoint 'c1' is 12 days old (policy: 7). |
| Medium | BUILD-AGENT | HeartbeatNotNormal | VM is Running but its heartbeat status is 'No Contact'. Running only means Hyper-V set resources aside (Learn); no heartbeat means no operating system reported in. |
| Medium | BUILD-AGENT | IntegrationServiceOff | The 'Shutdown' integration service is disabled. |
| Medium | BUILD-AGENT | ProductionWithoutVss | Production checkpoints use VSS (Learn) but the VSS integration service is disabled, so the guest probably cannot take one: type Production then creates a standard checkpoint, ProductionOnly fails. |
| Medium | BUILD-AGENT | SecureBootOff | Secure Boot is off on a generation 2 VM (it is on by default, Learn). Fine for a guest that cannot boot with it; otherwise turn it on. |
| Medium | BUILD-AGENT | TooManyCheckpoints | 5 checkpoints (policy: at most 3). Every one is a differencing disk in the chain. |
| Medium | HV-OLD01 | MemoryCommitted | Running VMs start with 58.0 GB of the host's 64 GB (policy: at most 85%); the host needs memory too. |
| Low | BUILD-AGENT | AutomaticCheckpoints | Automatic checkpoints are on: a checkpoint is created every time the VM starts (Learn). Turn off with Set-VM -AutomaticCheckpointsEnabled $false unless you want it. |
| Low | BUILD-AGENT | IntegrationServiceOff | The 'VSS' integration service is disabled. |
| Low | HV-OLD01 | DefaultPathOnSystemDrive | The default virtual machine configuration path (C:\ProgramData\Microsoft\Windows\Hyper-V) is on the system drive while E:\ exists: new VMs will fill C: first. |
| Low | HV-OLD01 | DefaultPathOnSystemDrive | The default virtual hard disk path (C:\Users\Public\Documents\Hyper-V\Virtual hard disks) is on the system drive while E:\ exists: new VMs will fill C: first. |
| Low | HV-OLD01 | VcpuRatio | 38 virtual processors run on 8 logical processors (our policy: at most 4 per logical processor; Hyper-V itself imposes no ratio). |
| Low | LAB-NEST01 | OldConfigurationVersion | Configuration version 7.0, this host's default is 12.0. Not available yet: GPU partitioning, Dynamic processor compatibility mode, Hibernation support, Guest virtualization-based security. Update-VMVersion is one-way: only after every host that may run it is upgraded. |
| Low | LEGACY-APP | Generation1 | Generation 1: no Secure Boot, no virtual TPM, boots from IDE. The generation cannot be changed after creation (Learn): rebuild as generation 2 when the guest allows it. |
| Low | LEGACY-APP | OldConfigurationVersion | Configuration version 8.0, this host's default is 12.0. Not available yet: GPU partitioning, Dynamic processor compatibility mode, Hibernation support. Update-VMVersion is one-way: only after every host that may run it is upgraded. |
| Info | LAB-NEST01 | NestedNetworking | Nested guests need either MAC address spoofing on this VM's adapter or a NAT switch inside the VM (Learn). |
| Info | LAB-NEST01 | NestedWithDynamicMemory | Dynamic Memory is on. Learn: enabling nested virtualization alone has no effect on it; once Hyper-V runs inside the VM, memory no longer fluctuates and can only be changed while the VM is off. |

