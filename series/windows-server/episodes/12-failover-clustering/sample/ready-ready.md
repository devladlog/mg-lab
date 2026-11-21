# Failover cluster readiness

| Node | OS build | Installation | Domain | Failover Clustering | Addresses | Reboot pending |
|---|---|---|---|---|---|---|
| CON-NODE01 | 26100.1742 | Server Core | lab.contoso.com | installed | 10.50.0.51/24 | no |
| CON-NODE02 | 26100.1742 | Server Core | lab.contoso.com | installed | 10.50.0.52/24 | no |

## Findings

| Severity | Target | Check | Message |
|---|---|---|---|
| Info | CON-CL01 | QuorumMath | 2 node(s) plus a file share witness: 3 votes, quorum needs 2, survives losing one node: yes. (Static count; Dynamic Quorum can do better.) |
| Info | CON-NODE01 | SingleNetwork | One network: cluster heartbeat and client traffic share it. Fine for a lab; Learn describes separate private networks for heartbeats in production. |
| Info | CON-NODE02 | SingleNetwork | One network: cluster heartbeat and client traffic share it. Fine for a lab; Learn describes separate private networks for heartbeats in production. |

