# Remote Desktop Services check

Connection broker: `con-rds01.lab.contoso.com`

## Servers and role services

| Server | Role services |
|---|---|

## Session hosts

| Host | OS | Installation | Grace days left |
|---|---|---|---|
| CON-RDS01 | Microsoft Windows Server 2025 Datacenter Evaluation | Server | 120 |

## Findings

| Severity | Target | Check | Message |
|---|---|---|---|
| High | con-rds01.lab.contoso.com | NoDeployment | Get-RDServer returned no servers: there is no Remote Desktop deployment on this connection broker (yet). |
| Info | CON-RDS01 | OnGracePeriod | Running on the licensing grace period: 120 day(s) left (Learn: 120 days, no license server needed until it ends). |

## Sessions

No user sessions.

