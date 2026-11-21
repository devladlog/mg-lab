# Demo shot list — DEVLADLOG Windows Server #4: DNS & DHCP Management

Everything in `src/`, `setup/` and `tests/` already ran in the build container: 42 Pester tests (DnsServer, DhcpServer,
Hyper-V and Windows-only cmdlets stubbed and mocked) and the offline report from the fictional snapshot
(`sample/report.md`). **Nothing has run against real servers yet**: every screen below needs the lab. Rewrite the
narration of each screen scene to what is actually on screen.

## Lab environment

Shared Hyper-V lab from `series/LAB.md` (NAT network `10.50.0.0/24`, domain `lab.contoso.com`, NetBIOS `CONTOSO`),
plus **one extra VM** and **one isolated Private switch**:

| Item | Spec | Role in this episode |
|---|---|---|
| CON-DC01 (existing) | 10.50.0.10, Server Core | DNS server for `lab.contoso.com`; gets the reverse zone `0.50.10.in-addr.arpa`, aging and scavenging |
| CON-SRV01 (existing) | 10.50.0.21, Server Core | DHCP server (primary). Second NIC `DHCPTest` on the Private switch, 172.16.50.2/24, MAC 00-15-5D-14-00-02 |
| CON-SRV02 (existing) | 10.50.0.22, Desktop Experience | DHCP failover partner + admin box (RSAT DNS/DHCP, recording). `DHCPTest` NIC 172.16.50.3/24, MAC 00-15-5D-14-00-03 |
| **CON-CLI01 (new)** | Windows Server 2025 Datacenter **Evaluation, Server Core**, 1 vCPU, 1 GB startup / 1.5 GB max dynamic RAM, 40 GB disk, Generation 2. NIC 1 on `MGLab-NAT` with **10.50.0.41** (static, like the other lab VMs), domain-joined to `lab.contoso.com`. No extra software | DHCP client. Second NIC `DHCPTest` on the Private switch, DHCP, fixed MAC **00-15-5D-14-00-41** (matches the reservation) |
| **Switch `MGLab-DHCPTest`** | Hyper-V **Private** switch (VM-to-VM only, no host vNIC, no NAT, no physical uplink), subnet 172.16.50.0/24, no gateway | The only network where the lab DHCP servers answer |

- Suggested `lab/hyperv/lab.config.psd1` entry for the lead session (this episode doesn't edit it):
  `@{ Name = 'CON-CLI01'; Role = 'Member'; Image = 'Core'; vCPU = 1; StartupGB = 1; MaxGB = 1.5; DiskGB = 40; IP = 41 }`.
  If `Start-MGLab.ps1` can't build it, create it by hand from the same evaluation media and join it to the domain.
- **Why a Private switch:** the NAT switch has no DHCP of its own and the lab VMs there are static; a test DHCP server
  must never answer on it. Two layers keep it that way: the DHCP servers' only scope is on 172.16.50.0/24, and
  `Invoke-NetLabDhcpDeployment` unbinds the DHCP service from every interface except `DHCPTest`. The Private switch
  has no path to the host or the home network.
- The DHCP option *DNS server = 10.50.0.10* points at the DC through the client's NAT NIC; the `DHCPTest` NICs are
  set not to register in DNS, so the zone keeps one record per host.
- Screens: CON-SRV02 VM console (VMConnect, 1600×900, font 18+) and, for the client, PowerShell Direct from the
  Hyper-V host (`Invoke-Command -VMName`), which works without any network.
- Cost: none (evaluation VMs, no cloud). RAM: the four VMs above, ~9.5 GB maximum together (CON-SQL01 can stay off).
- Account: "lab Administrator" (domain admin). Never typed on screen, never in files.

## Prerequisites (before recording, not filmed)

1. Copy this episode folder to the Hyper-V host and to `C:\lab\ep04` on CON-SRV02.
2. **Isolated network** — on the Hyper-V host, elevated:
   ```powershell
   $cred = Get-Credential CONTOSO\Administrator          # lab Administrator, for PowerShell Direct
   .\setup\New-DhcpTestNetwork.ps1 -Credential $cred -WhatIf
   .\setup\New-DhcpTestNetwork.ps1 -Credential $cred
   ```
   Expected output: `DHCPTest` with 172.16.50.2 and 172.16.50.3 on the servers, an APIPA (169.254.x.x) address on
   CON-CLI01 until DHCP is up. *Verify:* hot-adding a NIC to the running Gen2 VMs works; if not, stop the VM, re-run.
3. **DHCP role** — on CON-SRV02, Windows PowerShell as lab Administrator:
   ```powershell
   cd C:\lab\ep04
   Invoke-Command -ComputerName CON-SRV01, CON-SRV02 -FilePath .\setup\Install-DhcpRole.ps1
   Install-WindowsFeature RSAT-DNS-Server                # DNS cmdlets against CON-DC01 (RSAT-DHCP comes with the role)
   Import-Module .\src\NetLab\NetLab.psd1
   ```
4. Terminal: `function prompt { 'PS> ' }`.

## Screens to capture (match the `screen` scenes in script.yaml)

### 1. `screens/dns.jpg` — "DNS, applied twice" (**needs lab**)
```powershell
cd C:\lab\ep04\src
Invoke-NetLabDnsDeployment -DefinitionPath .\network.json | Format-Table Server, Action, Target, Result -AutoSize
Invoke-NetLabDnsDeployment -DefinitionPath .\network.json | Format-Table Server, Action, Target, Result -AutoSize
Invoke-Command -ComputerName CON-SRV01 { ipconfig /registerdns }
Start-Sleep 60
Resolve-DnsName 10.50.0.21 -Server CON-DC01
Resolve-DnsName printer01.lab.contoso.com -Server CON-DC01; Resolve-DnsName 10.50.0.60 -Server CON-DC01
```
Expected run 1: ReverseZone, ZoneAging ×2, Scavenging, A ×2, PTR ×2, CNAME ×2 = Done; run 2: 10 × NoChange.
- **Verify and note in README:** the zone name `Add-DnsServerPrimaryZone -NetworkId 10.50.0.0/24` really creates
  (Learn's example text and output disagree; we expect `0.50.10.in-addr.arpa`); that CON-SRV01 registers its PTR after
  `ipconfig /registerdns`; the property names `RecordData.IPv4Address` / `PtrDomainName` / `HostNameAlias`.

### 2. `screens/dhcp.jpg` — "Two servers, one scope" (**needs lab**)
```powershell
Invoke-NetLabDhcpDeployment -DefinitionPath .\network.json | Format-Table Server, Action, Target, Result -AutoSize
Get-DhcpServerv4Failover -ComputerName CON-SRV01 | Format-List Name, PartnerServer, Mode, LoadBalancePercent, State, ScopeId
Get-DhcpServerv4Failover -ComputerName CON-SRV02 | Format-List Name, PartnerServer, Mode, LoadBalancePercent, State, ScopeId
Get-DhcpServerv4Scope -ComputerName CON-SRV02
```
Expected: Authorize ×2, Binding (Ethernet=False and DHCPTest=True on each), Scope, Exclusion, Options, Reservation,
Failover = Done. Run it a second time off-camera: everything NoChange, no Replicate.
- **Verify:** the NAT adapter's alias in `Get-DhcpServerv4Binding` (the code doesn't care, it unbinds everything except
  `DHCPTest`); the exact `State` string of a healthy relationship (we check for `Normal`); that `Set-DhcpServerv4OptionValue
  -DnsServer 10.50.0.10` is accepted (CON-SRV01 reaches the DC over its NAT NIC).

### 3. `screens/lease.jpg` — "The client gets its reserved address" (**needs lab**)
On the Hyper-V host:
```powershell
Invoke-Command -VMName CON-CLI01 -Credential $cred { ipconfig /renew DHCPTest | Out-Null; ipconfig /all }
```
and on CON-SRV02:
```powershell
Get-DhcpServerv4Lease -ComputerName CON-SRV01 -ScopeId 172.16.50.0
Get-DhcpServerv4Lease -ComputerName CON-SRV02 -ScopeId 172.16.50.0
```
Capture the `DHCPTest` adapter (172.16.50.41, DHCP Server 172.16.50.2 or .3, DNS 10.50.0.10, suffix
`lab.contoso.com`) next to the two lease lists.

### 4. `screens/failover-drift.jpg` — "Gotcha: the partner never heard about it" (**needs lab**)
```powershell
Add-DhcpServerv4Reservation -ComputerName CON-SRV01 -ScopeId 172.16.50.0 -IPAddress 172.16.50.42 -ClientId 00-15-5d-14-00-42 -Name labprinter
Get-DhcpServerv4Reservation -ComputerName CON-SRV01 -ScopeId 172.16.50.0 | Format-Table IPAddress, ClientId, Name
Get-DhcpServerv4Reservation -ComputerName CON-SRV02 -ScopeId 172.16.50.0 | Format-Table IPAddress, ClientId, Name
.\Invoke-NetLabReport.ps1 -SnapshotFile .\net-snapshot.json | Select-String 'FailoverDrift', 'finding'
Invoke-DhcpServerv4FailoverReplication -ComputerName CON-SRV01 -ScopeId 172.16.50.0 -Force
Get-DhcpServerv4Reservation -ComputerName CON-SRV02 -ScopeId 172.16.50.0 | Format-Table IPAddress, ClientId, Name
```
Expected: 2 rows on CON-SRV01, 1 on CON-SRV02, `FailoverDrift` High, then 2 rows on both. If the partner already shows
the new reservation before replication, record that honestly and rewrite the scene (Learn says manual replication is
required; the behaviour on the recording day is what counts).

### 5. Plant one problem for the report (before shot 6, not recorded)
```powershell
Add-DnsServerResourceRecordA -ComputerName CON-DC01 -ZoneName lab.contoso.com -Name camera01 -IPv4Address 172.16.50.30
```

### 6. `screens/report.jpg` — "The lab network, checked" (**needs lab**)
```powershell
.\Invoke-NetLabReport.ps1 -SnapshotFile .\net-snapshot.json -OutFile .\net-report.md
```
Expected: `StaticInPool` High for camera01, `NoReverseZone` Medium for 172.16.50.0/24, no FailoverDrift. Note in README
anything else the real lab reports (likely `ZoneAgingDisabled` for `_msdcs.lab.contoso.com`, which the deployment
doesn't touch). Open `net-report.md` in a markdown preview.

## Masking
- Everything is fictional (`lab.contoso.com`, `CONTOSO`, 10.50.0.0/24, 172.16.50.0/24, MACs in the Hyper-V
  00-15-5D range set by the script). Keep it that way.
- Hide the Hyper-V host name, the host's Windows user profile path and any home-network adapter or IP that shows up in
  `ipconfig /all` on the host.

## Tear-down
On CON-SRV02:
```powershell
Remove-DnsServerResourceRecord -ComputerName CON-DC01 -ZoneName lab.contoso.com -Name camera01 -RRType A -Force
Remove-DhcpServerv4Failover -ComputerName CON-SRV01 -Name CON-SRV01-CON-SRV02      # confirm the prompt
Remove-DhcpServerInDC -DnsName con-srv01.lab.contoso.com -IPAddress 10.50.0.21
Remove-DhcpServerInDC -DnsName con-srv02.lab.contoso.com -IPAddress 10.50.0.22
Invoke-Command -ComputerName CON-SRV01, CON-SRV02 { Uninstall-WindowsFeature DHCP -IncludeManagementTools }
```
On the Hyper-V host: `.\setup\New-DhcpTestNetwork.ps1 -Credential $cred -Remove` (removes the three `DHCPTest` NICs and
the Private switch). Stop or delete CON-CLI01. The reverse zone, aging/scavenging settings and the printer/NAS/CNAME
records can stay: later episodes can use them. Delete `net-snapshot.json` / `net-report.md`.
