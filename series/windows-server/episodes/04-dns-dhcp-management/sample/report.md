# DNS and DHCP health report: lab.contoso.com

Snapshot: 2026-11-20 09:00 UTC - DNS server CON-DC01, 4 zone(s), 22 record(s); DHCP server(s) CON-SRV01, CON-SRV02.

**High 3 / Medium 9 / Low 2 / Info 0**

| DHCP server | Scope | State | In use | Reservations | Failover |
|---|---|---|---|---|---|
| CON-SRV01 | 172.16.50.0 DHCPTest (isolated private switch) | Active | 85% | 2 | CON-SRV01-CON-SRV02 (Normal) |
| CON-SRV01 | 172.16.60.0 Old test scope | Inactive | 0% | 0 | - |
| CON-SRV02 | 172.16.50.0 DHCPTest (isolated private switch) | Active | 85% | 1 | CON-SRV01-CON-SRV02 (Normal) |

| Severity | Check | Target | Detail |
|---|---|---|---|
| High | FailoverDrift | 172.16.50.0 (CON-SRV01 vs CON-SRV02) | reservations differ (172.16.50.42=00-15-5d-14-00-42). Scope changes are not replicated automatically: Invoke-DhcpServerv4FailoverReplication from the server with the right settings. |
| High | InsecureDynamicUpdate | oldapps.lab.contoso.com | AD-integrated zone accepts nonsecure updates: anyone can register or overwrite names. Set DynamicUpdate to Secure. |
| High | StaticInPool | camera01.lab.contoso.com | Static DNS record 172.16.50.30 is inside the pool of CON-SRV01/172.16.50.0 with no exclusion or reservation: DHCP can lease the same address to another client. |
| Medium | CnameTargetMissing | wiki.lab.contoso.com | Alias of con-wiki01.lab.contoso.com, which has no A record. |
| Medium | MissingOption | CON-SRV01/172.16.60.0 | Option 15 is set neither on the scope nor on the server. |
| Medium | NoReverseZone | 172.16.50.0/24 | No reverse zone for 1 A record(s): camera01.lab.contoso.com. |
| Medium | PtrMismatch | 10.50.0.99 | PTR points to con-gone01.lab.contoso.com, which has no A record for 10.50.0.99. |
| Medium | ScavengingDisabled | CON-DC01 | Server scavenging is off: stale records are never deleted, even in zones with aging on. |
| Medium | ScopeInactive | CON-SRV01/172.16.60.0 | Scope is not active: it leases nothing. |
| Medium | ScopeUtilization | CON-SRV01/172.16.50.0 | 85% of the pool in use. |
| Medium | ScopeUtilization | CON-SRV02/172.16.50.0 | 85% of the pool in use. |
| Medium | ZoneAgingDisabled | oldapps.lab.contoso.com | Dynamic zone without aging: scavenging skips it. |
| Low | MissingPtr | nas01.lab.contoso.com | 10.50.0.61 has no PTR in 0.50.10.in-addr.arpa. |
| Low | StaleRecord | con-old01.lab.contoso.com | Dynamic record last refreshed 2026-09-01: no refresh within no-refresh + refresh. The host is probably gone. |

