# Failover cluster readiness

| Node | OS build | Installation | Domain | Failover Clustering | Addresses | Reboot pending |
|---|---|---|---|---|---|---|
| CON-NODE01 | 26100.1700 | Server Core | WORKGROUP | no | 192.168.5.20/24 (DHCP) | yes |
| CON-NODE02 | 20348.2700 | Server | lab.contoso.com | installed | 10.50.0.52/24 | no |

## Findings

| Severity | Target | Check | Message |
|---|---|---|---|
| High | CON-CL01 | ClockSkew | Node clocks differ by 722 s; Kerberos tolerates 5 minutes by default (Learn). Fix time sync first. |
| High | CON-CL01 | NodesInDifferentDomains | The nodes are in different domains (Learn: all nodes must be in the same Active Directory domain). |
| High | CON-NODE01 | ClusterIpNotOnNodeNetwork | The cluster address 10.50.0.60 is not in any network this node has: New-Cluster takes a static address per network it uses (Learn). |
| High | CON-NODE01 | NoDnsServer | No DNS server configured. Learn: the servers in a cluster must use DNS for name resolution. |
| High | CON-NODE01 | NotDomainJoined | The node is not domain-joined. Learn: all nodes must be in the same Active Directory domain. |
| High | CON-NODE01 | RoleIpNotOnNodeNetwork | The role address 10.50.0.61 is not in any network this node has. |
| Medium | CON-CL01 | NodeBuildMismatch | Nodes run different Windows builds (26100.1700, 20348.2700). Expect this only during a rolling upgrade. |
| Medium | CON-CL01 | WitnessShareMissing | No node can see \\CON-SRV01\ClusterWitness yet (seen with the admin's rights; the cluster name object still needs its own access after New-Cluster). |
| Medium | CON-NODE01 | FeatureMissing | The Failover Clustering feature is not installed (Learn: install it on every node). |
| Medium | CON-NODE01 | NodeAlreadyClustered | The Cluster service is already running on this node: it may already belong to a cluster. |
| Medium | CON-NODE01 | PendingReboot | A restart is pending. Restart before creating the cluster. |
| Low | CON-CL01 | NodeEditionDiffers | Nodes run different editions. |
| Low | CON-NODE01 | NodeAddressDhcp | Adapter 'Ethernet' (192.168.5.20) uses DHCP. Our policy: static addresses on cluster nodes. |
| Info | CON-CL01 | NodeInstallTypeDiffers | Nodes mix Server Core and Desktop Experience. |
| Info | CON-CL01 | QuorumMath | 2 node(s) plus a file share witness: 3 votes, quorum needs 2, survives losing one node: yes. (Static count; Dynamic Quorum can do better.) |
| Info | CON-NODE01 | SingleNetwork | One network: cluster heartbeat and client traffic share it. Fine for a lab; Learn describes separate private networks for heartbeats in production. |
| Info | CON-NODE02 | SingleNetwork | One network: cluster heartbeat and client traffic share it. Fine for a lab; Learn describes separate private networks for heartbeats in production. |

