# DEVLADLOG Windows Server #4 — DNS & DHCP Management: one file, an isolated network, failover that stays in sync

**NetLab** is a PowerShell module that builds DNS and DHCP for `lab.contoso.com` from one definition file and then
checks both against each other:

1. **`setup/New-DhcpTestNetwork.ps1`** (Hyper-V host) creates a **Private** switch `MGLab-DHCPTest` and gives
   CON-SRV01, CON-SRV02 and the client CON-CLI01 a second NIC on it with fixed MACs; inside the guests (PowerShell
   Direct) it renames the NIC, stops it registering in DNS and sets 172.16.50.2 / .3 on the servers. It refuses to
   continue if a switch with that name exists and isn't Private. `-Remove` undoes it.
   **`setup/Install-DhcpRole.ps1`** installs the DHCP role, creates the DHCP security groups, restarts the service and
   clears the Server Manager post-install alert (the steps from Learn's DHCP PowerShell deployment guide).
2. **`Invoke-NetLabDnsDeployment`** on CON-DC01: computes the reverse zone name (`10.50.0.0/24` →
   `0.20.10.in-addr.arpa`) and creates it AD-integrated with secure updates, sets aging on the managed zones,
   enables server scavenging, and adds the static A + PTR records and CNAMEs from the file; repairs drift.
3. **`Invoke-NetLabDhcpDeployment`**: authorizes both servers in AD, binds the DHCP service only to the `DHCPTest`
   NIC, builds the scope on the primary (exclusion range, options 6 and 15, a reservation for the client's MAC),
   creates a 50/50 load-balance failover relationship, and **replicates to the partner after any scope change**
   (or on demand with `-Replicate`).
4. **`Export-NetLabSnapshot` + `Test-NetLabHealth`** export zones, aging, scavenging, A/PTR/CNAME records and every
   DHCP server's scopes, exclusions, reservations, options, utilization and failover state, then check: nonsecure
   updates on AD zones, scavenging off, zone aging off, aging intervals under 24 h, missing/mismatched PTRs, missing
   reverse zone, dangling CNAMEs, stale dynamic records, DHCP not authorized, inactive scope, utilization, missing
   options, no failover, failover not Normal, **failover drift** between partners, and **static DNS records inside a
   DHCP pool** (no exclusion, no reservation).

| Path | What it is |
|---|---|
| [`src/NetLab/NetLab.psm1`](src/NetLab/NetLab.psm1) | The module (Windows PowerShell 5.1 and PowerShell 7) |
| [`src/network.json`](src/network.json) | DNS records, reverse zone, aging/scavenging, DHCP servers, scope, reservation, failover, report policy |
| [`src/Invoke-NetLabReport.ps1`](src/Invoke-NetLabReport.ps1) | Entry script: live (exports a snapshot) or `-FromSnapshot`; `-Now`, `-OutFile`, `-FailOnHigh` (exit 1) |
| [`setup/New-DhcpTestNetwork.ps1`](setup/New-DhcpTestNetwork.ps1) | Hyper-V host: Private switch + `DHCPTest` NICs (fixed MACs) + guest IP config; `-WhatIf`, `-Remove` |
| [`setup/Install-DhcpRole.ps1`](setup/Install-DhcpRole.ps1) | DHCP role + security groups + Server Manager flag, on each DHCP server |
| [`tests/NetLab.Tests.ps1`](tests/NetLab.Tests.ps1) | 42 Pester tests; DnsServer, DhcpServer, Hyper-V and Windows-only cmdlets are stubbed and mocked |
| [`tests/fixtures/net-snapshot.json`](tests/fixtures/net-snapshot.json) | Fictional snapshot (DNS + two DHCP servers) with one example of each problem |
| [`sample/report.md`](sample/report.md) | The report generated from the fixture |

## Run the tests (any OS, no servers)

```bash
cd series/windows-server/episodes/04-dns-dhcp-management
pwsh -NoProfile -Command 'Invoke-Pester ./tests'          # Tests Passed: 42, Failed: 0   (PowerShell 7.6.0, Pester 6.2.0)

cd src
pwsh -NoProfile -Command './Invoke-NetLabReport.ps1 -FromSnapshot ../tests/fixtures/net-snapshot.json -Now 2026-11-20T09:00:00Z -OutFile ../sample/report.md'
# lab.contoso.com: 14 finding(s), 3 high.
```

## Run it in the lab

```powershell
# Hyper-V host, elevated
.\setup\New-DhcpTestNetwork.ps1 -Credential (Get-Credential CONTOSO\Administrator)

# CON-SRV02, Windows PowerShell 5.1 as a lab domain admin, in the episode folder
Invoke-Command -ComputerName CON-SRV01, CON-SRV02 -FilePath .\setup\Install-DhcpRole.ps1
Install-WindowsFeature RSAT-DNS-Server
cd src; Import-Module .\NetLab\NetLab.psd1
Invoke-NetLabDnsDeployment  -DefinitionPath .\network.json -WhatIf
Invoke-NetLabDnsDeployment  -DefinitionPath .\network.json
Invoke-NetLabDhcpDeployment -DefinitionPath .\network.json
.\Invoke-NetLabReport.ps1 -SnapshotFile .\net-snapshot.json -OutFile .\net-report.md
```

See [demo.md](demo.md) for the lab environment (the extra VM CON-CLI01 at 10.50.0.41 and the Private switch), the six
steps/screens and tear-down.

## Design choices

- **DHCP never touches the lab NAT network.** The NAT switch has no DHCP and the lab VMs are static. The scope lives on
  a Hyper-V Private switch (no host, no NAT, no uplink) and the DHCP service is unbound from every other interface.
- **Compute names, then look them up.** The reverse zone name and PTR owner names come from pure functions with tests;
  Learn's own `Add-DnsServerPrimaryZone -NetworkID "10.1.0.0/24"` example says it creates `0.1.10.in-addr.arpa` while
  its sample output shows `1.10.in-addr.arpa`, so we don't trust the cmdlet's naming blindly.
- **Static on purpose.** Printer, NAS and aliases are added without `-AgeRecord`: timestamp zero, never scavenged.
  Hosts that register themselves stay dynamic and age normally.
- **Replicate after every change to a failover scope.** Failover copies the scope once, at creation; the deployment
  tracks whether it changed anything and then calls `Invoke-DhcpServerv4FailoverReplication` from the primary.
- **Cross-check DNS and DHCP.** One snapshot holds both, so a static A record inside a DHCP pool is caught.
- **Windows PowerShell 5.1 first**, like episode 3: a Pester test parses the module and both setup scripts and fails on
  PowerShell 7-only syntax.

## What we learned / gotchas

- **Failover changes are not replicated automatically.** Learn: "If changes are made to a failover-enabled scope, you
  must manually replicate these changes to the partner server", and replication overwrites the partner, so always run
  it from the server with the right settings. The report compares partners reservation by reservation and option by
  option (`FailoverDrift`, High).
- **Aging and scavenging are independent; you need both.** Scavenging is a server setting, aging a zone setting. A
  record is stale after timestamp + no-refresh + refresh (7 + 7 days by default) and is deleted on the next pass, so
  worst case ~21 days. Static records (timestamp 0) are never scavenged. Enabling aging on a zone gives one refresh
  interval of grace.
- **Under 24 hours you lose live records.** Learn's scavenging troubleshooting: hosts with static IPs re-register every
  24 hours; if no-refresh + refresh is below that, their records get scavenged (`AgingTooShort`, High).
- **Unauthorized DHCP servers in a domain don't lease** (Learn), so authorization is part of the deployment and the
  report checks it.
- **Clients must reach both failover partners** (directly or via relay), so both servers get a NIC on the isolated
  subnet, not just the primary.
- **Secure dynamic updates exist only for AD-integrated zones**, and an AD-integrated zone allows only secure updates by
  default; `NonsecureAndSecure` on such a zone is flagged High.
- **A real bug the tests caught:** we first turned the failover `SecureString` into text with
  `Marshal::PtrToStringAuto(SecureStringToBSTR(...))`. On Linux that returned only the first character (`'l'` instead
  of `'lab-only-secret'`): "Auto" means ANSI there, while a BSTR is UTF-16. The module now uses
  `PSCredential.GetNetworkCredential().Password`, which is correct everywhere.
- **Pester can't mock what doesn't exist**, including the native `netsh` on Linux: the tests create a stub for it, as for
  the RSAT and Hyper-V cmdlets (every parameter declared, or `-ParameterFilter` sees nothing).
- **PowerShell 7.6.0: `@()` around a `List[object]` of PSCustomObjects throws** "Argument types do not match" (found in
  episode 3); this module uses `ArrayList` from the start.

> **Not run yet (needs the lab, see [demo.md](demo.md)):** both deployments, the export and both setup scripts against
> real servers; only unit-tested with mocks and parsed. To confirm in the lab: the zone name `-NetworkId 10.50.0.0/24`
> creates; property names on `Get-DnsServerResourceRecord`, `Get-DhcpServerv4Failover` (`State`, `ScopeId`,
> `PartnerServer`) and `Get-DhcpServerv4ScopeStatistics` (`PercentageInUse`); the healthy failover `State` string
> (`Normal`); hot-adding the NICs to running VMs; whether the partner really lacks a hand-added reservation until
> replication on the recording day.

## References

- [Deploy DHCP using Windows PowerShell](https://learn.microsoft.com/windows-server/networking/technologies/dhcp/dhcp-deploy-wps) (role, security groups, authorization, Server Manager flag, exclusions, options, test-lab switch advice)
- [DHCP failover overview](https://learn.microsoft.com/windows-server/networking/technologies/dhcp/dhcp-failover) (manual replication, clients must reach both partners, synchronized lease databases) and [Replicate DHCP failover](https://learn.microsoft.com/windows-server/networking/technologies/dhcp/replicate-dhcp-failover)
- [Add-DhcpServerv4Failover](https://learn.microsoft.com/powershell/module/dhcpserver/add-dhcpserverv4failover), [Invoke-DhcpServerv4FailoverReplication](https://learn.microsoft.com/powershell/module/dhcpserver/invoke-dhcpserverv4failoverreplication), [Set-DhcpServerv4Binding](https://learn.microsoft.com/powershell/module/dhcpserver/set-dhcpserverv4binding), [Set-DhcpServerv4OptionValue](https://learn.microsoft.com/powershell/module/dhcpserver/set-dhcpserverv4optionvalue), [Remove-DhcpServerInDC](https://learn.microsoft.com/powershell/module/dhcpserver/remove-dhcpserverindc)
- [DNS aging and scavenging](https://learn.microsoft.com/windows-server/networking/dns/aging-scavenging) and [Configure DNS aging and scavenging](https://learn.microsoft.com/windows-server/networking/dns/configure-aging-scavenging) (both needed, 7 + 7 days, static records, `-AgeRecord`, grace period)
- [Troubleshoot DNS scavenging issues](https://learn.microsoft.com/troubleshoot/windows-server/networking/troubleshoot-dns-scavenging-issues) (static IPs register every 24 hours; intervals under 24 h lose records)
- [Dynamic update](https://learn.microsoft.com/windows-server/networking/dns/dynamic-update) (secure updates only for AD-integrated zones, secure-only by default)
- [Add-DnsServerPrimaryZone](https://learn.microsoft.com/powershell/module/dnsserver/add-dnsserverprimaryzone) (`-NetworkId`, `-ReplicationScope`), [Add-DnsServerResourceRecordPtr](https://learn.microsoft.com/powershell/module/dnsserver/add-dnsserverresourcerecordptr)
- [Add-VMNetworkAdapter](https://learn.microsoft.com/powershell/module/hyper-v/add-vmnetworkadapter) (`-StaticMacAddress`, `-SwitchName`) and [Set-VMNetworkAdapter](https://learn.microsoft.com/powershell/module/hyper-v/set-vmnetworkadapter)
- Blog: [DNS & DHCP Management — Complete Guide](https://www.devladlog.com/articles/windows-server/2025-10-01-dns-dhcp-management-complete-guide-2025/)
