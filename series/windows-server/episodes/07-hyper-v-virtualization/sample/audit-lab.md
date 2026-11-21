# Hyper-V audit: LAB-LAPTOP

Collected 11/20/2026 08:55:00 | Microsoft Windows 11 Pro (build 26100) | default VM configuration version 12.0

16 logical processors, 64 GB RAM. Default paths: VMs `E:\MGLab\VMs`, disks `E:\MGLab\VHDs`

| Volume | Size GB | Free GB |
|---|---|---|
| C:\ | 476 | 131 |
| E:\ | 1863 | 1402 |

| VM | State | Gen | Version | vCPU | Start GB | Dynamic | Checkpoint type | Checkpoints | Disk chain | Secure Boot | TPM |
|---|---|---|---|---|---|---|---|---|---|---|---|
| CON-DC01 | Running | 2 | 12.0 | 2 | 2 | yes | Production | 0 | 2 | on | no |
| CON-SRV01 | Running | 2 | 12.0 | 2 | 1 | yes | Production | 0 | 2 | on | no |
| CON-SRV02 | Running | 2 | 12.0 | 2 | 2 | yes | Production | 0 | 2 | on | no |
| CON-CLI01 | Running | 2 | 12.0 | 1 | 1 | yes | Production | 0 | 2 | on | no |
| CON-SQL01 | Off | 2 | 12.0 | 2 | 2 | yes | Production | 0 | 2 | on | no |

## Findings

| Severity | Target | Check | Message |
|---|---|---|---|
| Info | LAB-LAPTOP | SharedParentDisk | 4 VMs (CON-DC01, CON-SRV01, CON-CLI01, CON-SQL01) are differencing disks of E:\MGLab\base\ws2025-core.vhdx. Never write to, move or delete the parent: every child breaks. |

