# JEA lint: Contoso.AppOps

High: 6 | Medium: 5 | Low: 1 | Info: 0 | Accepted: 0

## What each group gets (after merging roles)

| Group | Roles | Commands |
|---|---|---|
| CONTOSO\GG-AppOps-Readers | AppOpsReader | Get-Service (any parameters)<br>Restart-Service (any parameters)<br>Get-* (any parameters)<br>Get-OpsHealth (any parameters) |
| CONTOSO\GG-AppOps-Operators | AppOpsReader, AppOpsOperator | Get-Service (any parameters)<br>Restart-Service (any parameters)<br>Get-* (any parameters)<br>Start-Process (any parameters)<br>Stop-Website -Name ~(?:Contoso)<br>Get-OpsHealth (any parameters)<br>Clear-OpsLogFolder (any parameters)<br>Reset-OpsCache (any parameters) |
| localhost\Helpdesk | AppOpsReader | Get-Service (any parameters)<br>Restart-Service (any parameters)<br>Get-* (any parameters)<br>Get-OpsHealth (any parameters) |

## Findings

| Severity | Scope | Check | Message |
|---|---|---|---|
| High | group CONTOSO\GG-AppOps-Operators | MergeWidening | Restart-Service loses its constraint from role AppOpsOperator: role 'AppOpsReader' allows Restart-Service with no parameter constraints, so all parameters are allowed. |
| High | group localhost\Helpdesk | BadPrincipal | Use the computer or domain name, not localhost, '.' or wildcards. |
| High | role AppOpsOperator | DangerousCommand | 'Start-Process' can be used to bypass JEA (Learn's list of potentially dangerous commands). |
| High | role AppOpsOperator | FunctionNotInModule | Visible function 'Reset-OpsCache' isn't defined in ContosoOps.psm1. |
| High | role AppOpsReader | ExternalCommandNotRooted | External command 'whoami.exe' must be a full path (C:\...). |
| High | role AppOpsReader | WildcardCommand | VisibleCmdlets 'Get-*' uses a wildcard: list each trusted command instead. |
| Medium | role AppOpsOperator | SetAndPattern | 'Stop-Website -Name' has ValidateSet and ValidatePattern: the pattern overrides the set. |
| Medium | role AppOpsOperator | UnconstrainedStateChange | 'Start-Process' changes state and has no parameter constraints. |
| Medium | role AppOpsReader | UnconstrainedStateChange | 'Restart-Service' changes state and has no parameter constraints. |
| Medium | session | NoTranscript | No TranscriptDirectory: you lose the record of who ran what. |
| Medium | session | VirtualAccountIsAdmin | The virtual account is a member of the local Administrators group (no RunAsVirtualAccountGroups). |
| Low | role AppOpsOperator | UnanchoredPattern | 'Stop-Website -Name' pattern 'Contoso' isn't anchored with ^...$, so it matches anywhere in the value. |

