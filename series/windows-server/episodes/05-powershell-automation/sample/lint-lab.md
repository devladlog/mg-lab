# JEA lint: Contoso.AppOps

High: 0 | Medium: 0 | Low: 0 | Info: 0 | Accepted: 1

## What each group gets (after merging roles)

| Group | Roles | Commands |
|---|---|---|
| CONTOSO\GG-AppOps-Readers | AppOpsReader | Get-Service (any parameters)<br>Get-OpsHealth (any parameters) |
| CONTOSO\GG-AppOps-Operators | AppOpsReader, AppOpsOperator | Get-Service (any parameters)<br>Restart-Service -Name W3SVC/WAS<br>Get-OpsHealth (any parameters)<br>Clear-OpsLogFolder (any parameters) |

## Findings

| Severity | Scope | Check | Message |
|---|---|---|---|
| Accepted | session | VirtualAccountIsAdmin | The virtual account is a member of the local Administrators group (no RunAsVirtualAccountGroups). Accepted: Restarting W3SVC/WAS needs local admin rights; the role only exposes two constrained commands and two functions. |

