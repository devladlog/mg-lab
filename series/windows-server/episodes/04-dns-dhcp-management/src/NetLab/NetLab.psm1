<#
  DEVLADLOG Windows Server #4 - NetLab
  DNS and DHCP for lab.contoso.com, from one definition file (network.json):

    * Invoke-NetLabDnsDeployment   reverse zone(s), A + PTR records, CNAMEs, zone aging and server scavenging.
    * Invoke-NetLabDhcpDeployment  authorization in AD, interface bindings, scope, exclusions, options,
                                   reservations, failover, and replication to the partner after every scope change.
    * Export-NetLabSnapshot        zones, records, aging, scavenging, scopes, leases statistics, reservations,
                                   options and failover state of every server, in one JSON file.
    * Test-NetLabHealth            pure checks on that snapshot (DNS, DHCP, and the two together).

  Windows PowerShell 5.1 and PowerShell 7. The DnsServer and DhcpServer modules come with RSAT (RSAT-DNS-Server,
  RSAT-DHCP) or the roles; the tests stub and mock them.
#>

$script:SeverityOrder = @{ High = 0; Medium = 1; Low = 2; Info = 3 }
# Names in a forward zone that aren't hosts (DC locator and application partition records).
$script:NonHostNames = '@', 'DomainDnsZones', 'ForestDnsZones'

# ---------------------------------------------------------------------------------------------------------------
# Pure helpers: IPv4 math, reverse zone names, definition
# ---------------------------------------------------------------------------------------------------------------
function ConvertTo-NetLabUInt32 {
    [CmdletBinding()] [OutputType([uint32])]
    param([Parameter(Mandatory)][string] $IPAddress)
    $o = $IPAddress.Trim().Split('.')
    if ($o.Count -ne 4) { throw "'$IPAddress' is not an IPv4 address." }
    $n = [uint32]0
    foreach ($x in $o) {
        $b = 0
        if (-not [int]::TryParse($x, [ref]$b) -or $b -lt 0 -or $b -gt 255) { throw "'$IPAddress' is not an IPv4 address." }
        $n = [uint32]($n * 256 + $b)
    }
    $n
}

function Test-NetLabIpInRange {
    [CmdletBinding()] [OutputType([bool])]
    param([Parameter(Mandatory)][string] $IPAddress, [Parameter(Mandatory)][string] $Start, [Parameter(Mandatory)][string] $End)
    $ip = ConvertTo-NetLabUInt32 $IPAddress
    ($ip -ge (ConvertTo-NetLabUInt32 $Start)) -and ($ip -le (ConvertTo-NetLabUInt32 $End))
}

function ConvertTo-NetLabReverseZoneName {
    <#
      '10.50.0.0/24' -> '0.50.10.in-addr.arpa'. Only octet boundaries (/8, /16, /24): that's what a classic
      in-addr.arpa zone covers. We compute the name ourselves and look the zone up by it.
    #>
    [CmdletBinding()] [OutputType([string])]
    param([Parameter(Mandatory)][string] $NetworkId)
    $parts = $NetworkId.Split('/')
    if ($parts.Count -ne 2) { throw "NetworkId '$NetworkId' must look like 10.50.0.0/24." }
    $prefix = [int]$parts[1]
    if ($prefix -notin 8, 16, 24) { throw "Prefix /$prefix is not on an octet boundary (use /8, /16 or /24)." }
    [void](ConvertTo-NetLabUInt32 $parts[0])
    $octets = @($parts[0].Split('.')[0..(($prefix / 8) - 1)])
    [array]::Reverse($octets)
    ($octets -join '.') + '.in-addr.arpa'
}

function Get-NetLabPtrName {
    <# Relative PTR owner name of an address inside a reverse zone: (10.50.0.60, 0.50.10.in-addr.arpa) -> '60'. $null if outside. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string] $IPAddress, [Parameter(Mandatory)][string] $ReverseZone)
    $zoneOctets = @($ReverseZone -replace '\.in-addr\.arpa\.?$', '' -split '\.')
    [array]::Reverse($zoneOctets)
    $ipOctets = $IPAddress.Split('.')
    for ($i = 0; $i -lt $zoneOctets.Count; $i++) { if ($ipOctets[$i] -ne $zoneOctets[$i]) { return $null } }
    $rest = @($ipOctets[$zoneOctets.Count..3])
    [array]::Reverse($rest)
    $rest -join '.'
}

function ConvertTo-NetLabFqdn {
    <# Lower-case, no trailing dot; relative names get the zone appended ('@' = the zone itself). #>
    param([string] $Name, [string] $Zone)
    $n = ([string]$Name).TrimEnd('.').ToLowerInvariant()
    if ($n -eq '@') { return $Zone.ToLowerInvariant() }
    if ($Zone -and -not $n.EndsWith('.' + $Zone.ToLowerInvariant()) -and $n -ne $Zone.ToLowerInvariant()) { return "$n.$($Zone.ToLowerInvariant())" }
    $n
}

function Read-NetLabDefinition {
    <# Loads network.json and refuses inconsistent input before anything touches a server. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string] $Path)
    $def = Get-Content -Raw -Path $Path | ConvertFrom-Json
    $errors = New-Object System.Collections.Generic.List[string]
    foreach ($z in @($def.Dns.ReverseZones)) {
        try { [void](ConvertTo-NetLabReverseZoneName $z.NetworkId) } catch { $errors.Add($_.Exception.Message) }
    }
    foreach ($r in @($def.Dns.Records)) {
        if ($r.Type -eq 'A') {
            try { [void](ConvertTo-NetLabUInt32 $r.Address) } catch { $errors.Add("$($r.Name): $($_.Exception.Message)") }
        }
        elseif ($r.Type -ne 'CNAME') { $errors.Add("$($r.Name): only A and CNAME records are managed here, not '$($r.Type)'.") }
    }
    foreach ($s in @($def.Dhcp.Scopes)) {
        if ((ConvertTo-NetLabUInt32 $s.StartRange) -gt (ConvertTo-NetLabUInt32 $s.EndRange)) { $errors.Add("$($s.Name): StartRange is after EndRange.") }
        foreach ($x in @($s.Exclusions)) {
            if (-not (Test-NetLabIpInRange $x.Start $s.StartRange $s.EndRange) -or -not (Test-NetLabIpInRange $x.End $s.StartRange $s.EndRange)) {
                $errors.Add("$($s.Name): exclusion $($x.Start)-$($x.End) is outside the scope range.")
            }
        }
        foreach ($v in @($s.Reservations)) {
            if (-not (Test-NetLabIpInRange $v.IPAddress $s.StartRange $s.EndRange)) { $errors.Add("$($s.Name): reservation $($v.IPAddress) is outside the scope range.") }
            foreach ($x in @($s.Exclusions)) {
                if (Test-NetLabIpInRange $v.IPAddress $x.Start $x.End) { $errors.Add("$($s.Name): reservation $($v.IPAddress) is inside exclusion $($x.Start)-$($x.End).") }
            }
        }
    }
    if ($def.Dhcp.Failover -and @($def.Dhcp.Servers | Where-Object Name -eq $def.Dhcp.Failover.Partner).Count -eq 0) {
        $errors.Add("Failover partner '$($def.Dhcp.Failover.Partner)' is not in Dhcp.Servers.")
    }
    if ($errors.Count) { throw ("Definition '$Path' is invalid:`n - " + ($errors -join "`n - ")) }
    $def
}

function New-NetLabFinding {
    param([string] $Severity, [string] $Check, [string] $Target, [string] $Detail)
    [pscustomobject]@{ Severity = $Severity; Check = $Check; Target = $Target; Detail = $Detail }
}

function Get-NetLabUtc { param($Value) if ($null -eq $Value -or "$Value" -eq '') { return $null }; ([datetime]$Value).ToUniversalTime() }

# ---------------------------------------------------------------------------------------------------------------
# Checks (pure)
# ---------------------------------------------------------------------------------------------------------------
function Test-NetLabHealth {
    [CmdletBinding()]
    param([Parameter(Mandatory)] $Snapshot, [Parameter(Mandatory)] $Policy, [datetime] $Now = (Get-Date).ToUniversalTime())
    $out = New-Object System.Collections.ArrayList
    $dns = $Snapshot.Dns
    $forward = ([string]$dns.ForwardZone).ToLowerInvariant()

    # --- DNS: zones, aging, scavenging --------------------------------------------------------------------
    if (-not $dns.Scavenging.Enabled) {
        [void]$out.Add((New-NetLabFinding Medium 'ScavengingDisabled' $dns.Server 'Server scavenging is off: stale records are never deleted, even in zones with aging on.'))
    }
    foreach ($z in @($dns.Zones | Where-Object { $_.ZoneType -eq 'Primary' })) {
        if ($z.IsDsIntegrated -and $z.DynamicUpdate -eq 'NonsecureAndSecure') {
            [void]$out.Add((New-NetLabFinding High 'InsecureDynamicUpdate' $z.ZoneName 'AD-integrated zone accepts nonsecure updates: anyone can register or overwrite names. Set DynamicUpdate to Secure.'))
        }
        if ($z.DynamicUpdate -ne 'None') {
            if (-not $z.AgingEnabled) {
                [void]$out.Add((New-NetLabFinding Medium 'ZoneAgingDisabled' $z.ZoneName 'Dynamic zone without aging: scavenging skips it.'))
            }
            elseif (([double]$z.NoRefreshHours + [double]$z.RefreshHours) -lt 24) {
                [void]$out.Add((New-NetLabFinding High 'AgingTooShort' $z.ZoneName "No-refresh + refresh = $([double]$z.NoRefreshHours + [double]$z.RefreshHours) h. Below 24 h records of live hosts get scavenged (hosts with static IPs re-register every 24 hours)."))
            }
        }
    }

    # --- DNS: records ----------------------------------------------------------------------------------------
    $reverseZones = @($dns.Zones | Where-Object IsReverseLookupZone | ForEach-Object ZoneName)
    $records = @($dns.Records)
    $aByName = @{}
    foreach ($r in @($records | Where-Object { $_.RecordType -eq 'A' -and $_.Zone -eq $dns.ForwardZone })) {
        $fqdn = ConvertTo-NetLabFqdn $r.HostName $forward
        if (-not $aByName.ContainsKey($fqdn)) { $aByName[$fqdn] = New-Object System.Collections.ArrayList }
        [void]$aByName[$fqdn].Add([string]$r.Data)
    }
    $ptrs = @{}
    foreach ($p in @($records | Where-Object RecordType -eq 'PTR')) { $ptrs["$($p.Zone)|$($p.HostName)".ToLowerInvariant()] = ConvertTo-NetLabFqdn $p.Data '' }

    $noZone = @{}
    $agingByZone = @{}
    foreach ($z in @($dns.Zones)) { $agingByZone[[string]$z.ZoneName] = $z }
    foreach ($r in @($records | Where-Object { $_.RecordType -eq 'A' -and $_.Zone -eq $dns.ForwardZone -and $script:NonHostNames -notcontains $_.HostName })) {
        $fqdn = ConvertTo-NetLabFqdn $r.HostName $forward
        $zone = $null; $ptrName = $null
        foreach ($rz in $reverseZones) { $n = Get-NetLabPtrName $r.Data $rz; if ($n) { $zone = $rz; $ptrName = $n; break } }
        if (-not $zone) {
            $net = ($r.Data.Split('.')[0..2] -join '.') + '.0/24'
            if (-not $noZone.ContainsKey($net)) { $noZone[$net] = New-Object System.Collections.ArrayList }
            [void]$noZone[$net].Add($fqdn)
        }
        elseif (-not $ptrs.ContainsKey("$zone|$ptrName".ToLowerInvariant())) {
            [void]$out.Add((New-NetLabFinding Low 'MissingPtr' $fqdn "$($r.Data) has no PTR in $zone."))
        }
        $ts = Get-NetLabUtc $r.Timestamp
        $za = $agingByZone[[string]$dns.ForwardZone]
        if ($ts -and $za -and $za.AgingEnabled) {
            $staleAfter = $ts.AddHours([double]$za.NoRefreshHours + [double]$za.RefreshHours)
            if ($staleAfter -lt $Now) {
                [void]$out.Add((New-NetLabFinding Low 'StaleRecord' $fqdn "Dynamic record last refreshed $($ts.ToString('yyyy-MM-dd')): no refresh within no-refresh + refresh. The host is probably gone."))
            }
        }
    }
    foreach ($net in $noZone.Keys) {
        [void]$out.Add((New-NetLabFinding Medium 'NoReverseZone' $net "No reverse zone for $($noZone[$net].Count) A record(s): $(@($noZone[$net]) -join ', ')."))
    }
    foreach ($p in @($records | Where-Object RecordType -eq 'PTR')) {
        $target = ConvertTo-NetLabFqdn $p.Data ''
        if (-not $target.EndsWith(".$forward")) { continue }
        $octets = @(($p.Zone -replace '\.in-addr\.arpa\.?$', '').Split('.'))
        [array]::Reverse($octets)
        $hostPart = @($p.HostName.Split('.'))
        [array]::Reverse($hostPart)
        $ip = (@($octets) + @($hostPart)) -join '.'
        if (-not $aByName.ContainsKey($target) -or @($aByName[$target]) -notcontains $ip) {
            [void]$out.Add((New-NetLabFinding Medium 'PtrMismatch' $ip "PTR points to $target, which has no A record for $ip."))
        }
    }
    foreach ($c in @($records | Where-Object { $_.RecordType -eq 'CNAME' -and $_.Zone -eq $dns.ForwardZone })) {
        $target = ConvertTo-NetLabFqdn $c.Data ''
        if ($target.EndsWith(".$forward") -and -not $aByName.ContainsKey($target)) {
            [void]$out.Add((New-NetLabFinding Medium 'CnameTargetMissing' (ConvertTo-NetLabFqdn $c.HostName $forward) "Alias of $target, which has no A record."))
        }
    }

    # --- DHCP ------------------------------------------------------------------------------------------------
    $authorized = @($Snapshot.Dhcp.Authorized | ForEach-Object { ([string]$_.DnsName).ToLowerInvariant() })
    $servers = @($Snapshot.Dhcp.Servers)
    $byServer = @{}
    foreach ($s in $servers) { $byServer[([string]$s.Name).ToLowerInvariant()] = $s }
    $required = @($Policy.RequiredOptions | ForEach-Object { [int]$_ })
    $seenPairs = @{}

    foreach ($s in $servers) {
        if ($authorized -notcontains ([string]$s.DnsName).ToLowerInvariant()) {
            [void]$out.Add((New-NetLabFinding High 'NotAuthorized' $s.Name 'Not authorized in AD: a domain-member DHCP server that is not authorized does not lease addresses.'))
        }
        $failoverScopes = @($s.Failover | ForEach-Object { @($_.ScopeId) } | ForEach-Object { [string]$_ })
        foreach ($sc in @($s.Scopes)) {
            $id = "$($s.Name)/$($sc.ScopeId)"
            if ($sc.State -ne 'Active') { [void]$out.Add((New-NetLabFinding Medium 'ScopeInactive' $id 'Scope is not active: it leases nothing.')) }
            elseif ($failoverScopes -notcontains [string]$sc.ScopeId) {
                [void]$out.Add((New-NetLabFinding Low 'NoFailover' $id 'Active scope without a failover partner: one server down = no new leases.'))
            }
            $pct = [double]$sc.PercentageInUse
            if ($pct -ge [double]$Policy.UtilizationHighPercent) { [void]$out.Add((New-NetLabFinding High 'ScopeUtilization' $id "$pct% of the pool in use.")) }
            elseif ($pct -ge [double]$Policy.UtilizationWarnPercent) { [void]$out.Add((New-NetLabFinding Medium 'ScopeUtilization' $id "$pct% of the pool in use.")) }
            $have = @(@($sc.Options) + @($s.ServerOptions) | ForEach-Object { [int]$_.OptionId })
            foreach ($o in $required) {
                if ($have -notcontains $o) { [void]$out.Add((New-NetLabFinding Medium 'MissingOption' $id "Option $o is set neither on the scope nor on the server.")) }
            }
            # DNS x DHCP: static A records inside the pool, not excluded and not reserved
            foreach ($r in @($records | Where-Object { $_.RecordType -eq 'A' -and -not $_.Timestamp -and $_.Zone -eq $dns.ForwardZone })) {
                if (-not (Test-NetLabIpInRange $r.Data $sc.StartRange $sc.EndRange)) { continue }
                $excluded = @($sc.Exclusions | Where-Object { Test-NetLabIpInRange $r.Data $_.StartRange $_.EndRange }).Count -gt 0
                $reserved = @($sc.Reservations | Where-Object { [string]$_.IPAddress -eq [string]$r.Data }).Count -gt 0
                $staticKey = "$($r.HostName)|$($sc.ScopeId)"
                if (-not $excluded -and -not $reserved -and -not $seenPairs.ContainsKey($staticKey)) {
                    $seenPairs[$staticKey] = $true
                    [void]$out.Add((New-NetLabFinding High 'StaticInPool' (ConvertTo-NetLabFqdn $r.HostName $forward) "Static DNS record $($r.Data) is inside the pool of $id with no exclusion or reservation: DHCP can lease the same address to another client."))
                }
            }
        }
        foreach ($f in @($s.Failover)) {
            if ([string]$f.State -ne 'Normal') {
                [void]$out.Add((New-NetLabFinding High 'FailoverState' "$($s.Name)/$($f.Name)" "Failover state is $($f.State), not Normal."))
            }
            $partnerKey = ([string]$f.PartnerServer).Split('.')[0].ToLowerInvariant()
            $partner = $byServer[$partnerKey]
            if (-not $partner) { continue }
            foreach ($scopeId in @($f.ScopeId)) {
                $pairKey = (@(([string]$s.Name).ToLowerInvariant(), $partnerKey) | Sort-Object) -join '|'
                if ($seenPairs.ContainsKey("$pairKey|$scopeId")) { continue }
                $seenPairs["$pairKey|$scopeId"] = $true
                $mine = @($s.Scopes | Where-Object { [string]$_.ScopeId -eq [string]$scopeId })[0]
                $theirs = @($partner.Scopes | Where-Object { [string]$_.ScopeId -eq [string]$scopeId })[0]
                if (-not $mine -or -not $theirs) { continue }
                $sig = { param($scope)
                    $res = @($scope.Reservations | ForEach-Object { "$($_.IPAddress)=$(([string]$_.ClientId).ToLowerInvariant())" } | Sort-Object)
                    $opt = @($scope.Options | ForEach-Object { "$($_.OptionId)=$(@($_.Value) -join ',')" } | Sort-Object)
                    @{ Res = $res; Opt = $opt }
                }
                $a = & $sig $mine; $b = & $sig $theirs
                $diff = @()
                $rd = @(@($a.Res | Where-Object { @($b.Res) -notcontains $_ }) + @($b.Res | Where-Object { @($a.Res) -notcontains $_ }))
                $od = @(@($a.Opt | Where-Object { @($b.Opt) -notcontains $_ }) + @($b.Opt | Where-Object { @($a.Opt) -notcontains $_ }))
                if ($rd.Count) { $diff += "reservations differ ($($rd -join '; '))" }
                if ($od.Count) { $diff += "options differ ($($od -join '; '))" }
                if ($diff.Count) {
                    [void]$out.Add((New-NetLabFinding High 'FailoverDrift' "$scopeId ($($s.Name) vs $($partner.Name))" "$($diff -join ', '). Scope changes are not replicated automatically: Invoke-DhcpServerv4FailoverReplication from the server with the right settings."))
                }
            }
        }
    }
    $out | Sort-Object @{ e = { $script:SeverityOrder[$_.Severity] } }, Check, Target
}

function ConvertTo-NetLabMarkdown {
    [CmdletBinding()] [OutputType([string])]
    param([Parameter(Mandatory)] $Snapshot, [Parameter(Mandatory)][AllowEmptyCollection()][object[]] $Finding)
    $count = { param($s) @($Finding | Where-Object Severity -eq $s).Count }
    $when = $Snapshot.ExportedAt
    if ($when -is [datetime]) { $when = $when.ToUniversalTime().ToString('yyyy-MM-dd HH:mm') + ' UTC' }
    $sb = New-Object System.Text.StringBuilder
    [void]$sb.AppendLine("# DNS and DHCP health report: $($Snapshot.Dns.ForwardZone)")
    [void]$sb.AppendLine('')
    [void]$sb.AppendLine("Snapshot: $when - DNS server $($Snapshot.Dns.Server), $(@($Snapshot.Dns.Zones).Count) zone(s), $(@($Snapshot.Dns.Records).Count) record(s); DHCP server(s) $(@($Snapshot.Dhcp.Servers | ForEach-Object Name) -join ', ').")
    [void]$sb.AppendLine('')
    [void]$sb.AppendLine("**High $(& $count 'High') / Medium $(& $count 'Medium') / Low $(& $count 'Low') / Info $(& $count 'Info')**")
    [void]$sb.AppendLine('')
    [void]$sb.AppendLine('| DHCP server | Scope | State | In use | Reservations | Failover |')
    [void]$sb.AppendLine('|---|---|---|---|---|---|')
    foreach ($s in @($Snapshot.Dhcp.Servers)) {
        foreach ($sc in @($s.Scopes)) {
            $f = @($s.Failover | Where-Object { @($_.ScopeId) -contains $sc.ScopeId } | ForEach-Object { "$($_.Name) ($($_.State))" }) -join ', '
            if (-not $f) { $f = '-' }
            [void]$sb.AppendLine("| $($s.Name) | $($sc.ScopeId) $($sc.Name) | $($sc.State) | $($sc.PercentageInUse)% | $(@($sc.Reservations).Count) | $f |")
        }
    }
    [void]$sb.AppendLine('')
    [void]$sb.AppendLine('| Severity | Check | Target | Detail |')
    [void]$sb.AppendLine('|---|---|---|---|')
    foreach ($x in $Finding) { [void]$sb.AppendLine("| $($x.Severity) | $($x.Check) | $($x.Target) | $($x.Detail) |") }
    $sb.ToString()
}

# ---------------------------------------------------------------------------------------------------------------
# Server side (DnsServer / DhcpServer modules)
# ---------------------------------------------------------------------------------------------------------------
function New-NetLabLog {
    param([string] $Server, [string] $Action, [string] $Target, [string] $Result)
    [pscustomobject]@{ Server = $Server; Action = $Action; Target = $Target; Result = $Result }
}

function Invoke-NetLabStep {
    <# One change: ShouldProcess, run, log. Returns the log line. #>
    param($Cmdlet, [string] $Server, [string] $Action, [string] $Target, [scriptblock] $Change, [string] $DoneResult = 'Done')
    if ($Cmdlet.ShouldProcess("$Server : $Target", $Action)) {
        & $Change | Out-Null
        New-NetLabLog $Server $Action $Target $DoneResult
    }
    else { New-NetLabLog $Server $Action $Target 'WhatIf' }
}

function Invoke-NetLabDnsDeployment {
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)][string] $DefinitionPath)
    $def = Read-NetLabDefinition -Path $DefinitionPath
    $d = $def.Dns
    $cn = [string]$d.Server
    if (-not (Get-DnsServerZone -ComputerName $cn -Name $d.ForwardZone -ErrorAction SilentlyContinue)) {
        throw "Forward zone '$($d.ForwardZone)' not found on $cn."
    }
    $noRefresh = [timespan]::FromDays([double]$d.Aging.NoRefreshDays)
    $refresh = [timespan]::FromDays([double]$d.Aging.RefreshDays)

    # Reverse zones (AD-integrated, secure updates)
    $zones = @([string]$d.ForwardZone)
    foreach ($rz in @($d.ReverseZones)) {
        $name = ConvertTo-NetLabReverseZoneName $rz.NetworkId
        $zones += $name
        if (Get-DnsServerZone -ComputerName $cn -Name $name -ErrorAction SilentlyContinue) { New-NetLabLog $cn 'ReverseZone' $name 'NoChange'; continue }
        Invoke-NetLabStep $PSCmdlet $cn 'ReverseZone' $name {
            Add-DnsServerPrimaryZone -ComputerName $cn -NetworkId $rz.NetworkId -ReplicationScope $rz.ReplicationScope -DynamicUpdate Secure
        }
    }

    # Aging on every managed zone, scavenging on the server: both are needed
    foreach ($z in $zones) {
        $aging = Get-DnsServerZoneAging -ComputerName $cn -Name $z -ErrorAction SilentlyContinue
        if (-not $aging -and $WhatIfPreference) { New-NetLabLog $cn 'ZoneAging' $z 'WhatIf'; continue }
        if ($aging -and $aging.AgingEnabled -and $aging.NoRefreshInterval -eq $noRefresh -and $aging.RefreshInterval -eq $refresh) { New-NetLabLog $cn 'ZoneAging' $z 'NoChange'; continue }
        Invoke-NetLabStep $PSCmdlet $cn 'ZoneAging' $z {
            Set-DnsServerZoneAging -ComputerName $cn -Name $z -Aging $true -NoRefreshInterval $noRefresh -RefreshInterval $refresh
        }
    }
    $interval = [timespan]::FromDays([double]$d.Scavenging.IntervalDays)
    $scav = Get-DnsServerScavenging -ComputerName $cn
    if ([bool]$scav.ScavengingState -eq [bool]$d.Scavenging.Enabled -and $scav.ScavengingInterval -eq $interval) { New-NetLabLog $cn 'Scavenging' $cn 'NoChange' }
    else {
        Invoke-NetLabStep $PSCmdlet $cn 'Scavenging' $cn {
            Set-DnsServerScavenging -ComputerName $cn -ScavengingState ([bool]$d.Scavenging.Enabled) -ScavengingInterval $interval
        }
    }

    # Records. Added without -AgeRecord: static (timestamp 0), never scavenged. Right for appliances and aliases.
    foreach ($r in @($d.Records)) {
        $fqdn = "$($r.Name).$($d.ForwardZone)".ToLowerInvariant()
        if ($r.Type -eq 'CNAME') {
            $cur = Get-DnsServerResourceRecord -ComputerName $cn -ZoneName $d.ForwardZone -Name $r.Name -RRType CName -ErrorAction SilentlyContinue
            $want = ([string]$r.Target).TrimEnd('.').ToLowerInvariant()
            if ($cur -and ([string]$cur.RecordData.HostNameAlias).TrimEnd('.').ToLowerInvariant() -eq $want) { New-NetLabLog $cn 'CNAME' $fqdn 'NoChange'; continue }
            if ($cur) {
                Invoke-NetLabStep $PSCmdlet $cn 'CNAME' $fqdn {
                    Remove-DnsServerResourceRecord -ComputerName $cn -ZoneName $d.ForwardZone -Name $r.Name -RRType CName -Force
                    Add-DnsServerResourceRecordCName -ComputerName $cn -ZoneName $d.ForwardZone -Name $r.Name -HostNameAlias $want
                } 'Updated'
            }
            else {
                Invoke-NetLabStep $PSCmdlet $cn 'CNAME' $fqdn { Add-DnsServerResourceRecordCName -ComputerName $cn -ZoneName $d.ForwardZone -Name $r.Name -HostNameAlias $want }
            }
            continue
        }
        $cur = @(Get-DnsServerResourceRecord -ComputerName $cn -ZoneName $d.ForwardZone -Name $r.Name -RRType A -ErrorAction SilentlyContinue)
        $ips = @($cur | ForEach-Object { [string]$_.RecordData.IPv4Address })
        if ($ips -contains [string]$r.Address -and $ips.Count -eq 1) { New-NetLabLog $cn 'A' $fqdn 'NoChange' }
        elseif ($ips.Count -eq 0) {
            Invoke-NetLabStep $PSCmdlet $cn 'A' $fqdn { Add-DnsServerResourceRecordA -ComputerName $cn -ZoneName $d.ForwardZone -Name $r.Name -IPv4Address $r.Address }
        }
        else {
            Invoke-NetLabStep $PSCmdlet $cn 'A' $fqdn {
                foreach ($old in ($ips | Where-Object { $_ -ne [string]$r.Address })) {
                    Remove-DnsServerResourceRecord -ComputerName $cn -ZoneName $d.ForwardZone -Name $r.Name -RRType A -RecordData $old -Force
                }
                if ($ips -notcontains [string]$r.Address) { Add-DnsServerResourceRecordA -ComputerName $cn -ZoneName $d.ForwardZone -Name $r.Name -IPv4Address $r.Address }
            } 'Updated'
        }
        if (-not $r.Ptr) { continue }
        $rzName = $null; $ptrName = $null
        foreach ($rz in @($d.ReverseZones)) {
            $zn = ConvertTo-NetLabReverseZoneName $rz.NetworkId
            $pn = Get-NetLabPtrName $r.Address $zn
            if ($pn) { $rzName = $zn; $ptrName = $pn; break }
        }
        if (-not $rzName) { New-NetLabLog $cn 'PTR' $r.Address 'NoReverseZone'; continue }
        $curPtr = Get-DnsServerResourceRecord -ComputerName $cn -ZoneName $rzName -Name $ptrName -RRType Ptr -ErrorAction SilentlyContinue
        if ($curPtr -and ([string]$curPtr.RecordData.PtrDomainName).TrimEnd('.').ToLowerInvariant() -eq $fqdn) { New-NetLabLog $cn 'PTR' $r.Address 'NoChange'; continue }
        Invoke-NetLabStep $PSCmdlet $cn 'PTR' $r.Address {
            if ($curPtr) { Remove-DnsServerResourceRecord -ComputerName $cn -ZoneName $rzName -Name $ptrName -RRType Ptr -Force }
            Add-DnsServerResourceRecordPtr -ComputerName $cn -ZoneName $rzName -Name $ptrName -PtrDomainName $fqdn
        }
    }
}

function Invoke-NetLabDhcpDeployment {
    <#
      Authorize, bind, configure the scope on the primary, create the failover relationship, and replicate to the
      partner whenever the scope changed on a server that already had failover (Learn: changes to a failover-enabled
      scope must be replicated manually).
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)][string] $DefinitionPath, [securestring] $FailoverSecret, [switch] $Replicate)
    $def = Read-NetLabDefinition -Path $DefinitionPath
    $h = $def.Dhcp
    $authorized = @(Get-DhcpServerInDC | ForEach-Object { ([string]$_.DnsName).ToLowerInvariant() })

    foreach ($s in @($h.Servers)) {
        $cn = [string]$s.Name
        if ($authorized -contains ([string]$s.DnsName).ToLowerInvariant()) { New-NetLabLog $cn 'Authorize' $s.DnsName 'NoChange' }
        else { Invoke-NetLabStep $PSCmdlet $cn 'Authorize' $s.DnsName { Add-DhcpServerInDC -DnsName $s.DnsName -IPAddress $s.AuthorizeIPAddress } }
        foreach ($b in @(Get-DhcpServerv4Binding -ComputerName $cn)) {
            $want = ([string]$b.InterfaceAlias -eq [string]$s.BindInterface)
            if ([bool]$b.BindingState -eq $want) { New-NetLabLog $cn 'Binding' "$($b.InterfaceAlias)=$want" 'NoChange'; continue }
            Invoke-NetLabStep $PSCmdlet $cn 'Binding' "$($b.InterfaceAlias)=$want" { Set-DhcpServerv4Binding -ComputerName $cn -InterfaceAlias $b.InterfaceAlias -BindingState $want }
        }
    }

    $primary = if ($h.Failover) { [string]$h.Failover.Primary } else { [string]@($h.Servers)[0].Name }
    $failover = $null
    if ($h.Failover) { $failover = Get-DhcpServerv4Failover -ComputerName $primary -Name $h.Failover.Name -ErrorAction SilentlyContinue }

    foreach ($sc in @($h.Scopes)) {
        $changed = $false
        $id = [string]$sc.ScopeId
        $cur = Get-DhcpServerv4Scope -ComputerName $primary -ScopeId $id -ErrorAction SilentlyContinue
        if ($cur) { New-NetLabLog $primary 'Scope' $id 'NoChange' }
        else {
            $log = Invoke-NetLabStep $PSCmdlet $primary 'Scope' $id {
                Add-DhcpServerv4Scope -ComputerName $primary -Name $sc.Name -StartRange $sc.StartRange -EndRange $sc.EndRange -SubnetMask $sc.SubnetMask -LeaseDuration ([timespan]$sc.LeaseDuration) -State Active
            }
            $log; if ($log.Result -eq 'Done') { $changed = $true }
        }

        $haveEx = @(); if ($cur) { $haveEx = @(Get-DhcpServerv4ExclusionRange -ComputerName $primary -ScopeId $id | ForEach-Object { "$($_.StartRange)-$($_.EndRange)" }) }
        foreach ($x in @($sc.Exclusions)) {
            if ($haveEx -contains "$($x.Start)-$($x.End)") { New-NetLabLog $primary 'Exclusion' "$($x.Start)-$($x.End)" 'NoChange'; continue }
            $log = Invoke-NetLabStep $PSCmdlet $primary 'Exclusion' "$($x.Start)-$($x.End)" { Add-DhcpServerv4ExclusionRange -ComputerName $primary -ScopeId $id -StartRange $x.Start -EndRange $x.End }
            $log; if ($log.Result -eq 'Done') { $changed = $true }
        }

        $haveOpt = @{}; if ($cur) { foreach ($o in @(Get-DhcpServerv4OptionValue -ComputerName $primary -ScopeId $id)) { $haveOpt[[int]$o.OptionId] = (@($o.Value) -join ',') } }
        $wantDns = (@($sc.Options.DnsServer) -join ','); $wantDomain = [string]$sc.Options.DnsDomain
        if ($haveOpt[6] -eq $wantDns -and $haveOpt[15] -eq $wantDomain) { New-NetLabLog $primary 'Options' "6=$wantDns 15=$wantDomain" 'NoChange' }
        else {
            $log = Invoke-NetLabStep $PSCmdlet $primary 'Options' "6=$wantDns 15=$wantDomain" {
                Set-DhcpServerv4OptionValue -ComputerName $primary -ScopeId $id -DnsServer @($sc.Options.DnsServer) -DnsDomain $wantDomain
            }
            $log; if ($log.Result -eq 'Done') { $changed = $true }
        }

        $haveRes = @(); if ($cur) { $haveRes = @(Get-DhcpServerv4Reservation -ComputerName $primary -ScopeId $id) }
        foreach ($v in @($sc.Reservations)) {
            $match = @($haveRes | Where-Object { [string]$_.IPAddress -eq [string]$v.IPAddress -and ([string]$_.ClientId).ToLowerInvariant() -eq ([string]$v.ClientId).ToLowerInvariant() })
            if ($match.Count) { New-NetLabLog $primary 'Reservation' "$($v.IPAddress) $($v.ClientId)" 'NoChange'; continue }
            $log = Invoke-NetLabStep $PSCmdlet $primary 'Reservation' "$($v.IPAddress) $($v.ClientId)" {
                Add-DhcpServerv4Reservation -ComputerName $primary -ScopeId $id -IPAddress $v.IPAddress -ClientId $v.ClientId -Name $v.Name -Description $v.Description
            }
            $log; if ($log.Result -eq 'Done') { $changed = $true }
        }

        if (-not $h.Failover) { continue }
        $f = $h.Failover
        if (-not $failover) {
            $log = Invoke-NetLabStep $PSCmdlet $primary 'Failover' "$($f.Name) -> $($f.Partner) $id" {
                $p = @{ ComputerName = $primary; Name = $f.Name; PartnerServer = $f.Partner; ScopeId = $id; LoadBalancePercent = [uint32]$f.LoadBalancePercent; MaxClientLeadTime = [timespan]$f.MaxClientLeadTime }
                if ($FailoverSecret) {
                    # The cmdlet takes the secret as a plain string. NetworkCredential decodes it correctly on every
                    # platform (PtrToStringAuto on a BSTR returned only the first character on Linux in our tests).
                    $p.SharedSecret = (New-Object System.Management.Automation.PSCredential('failover', $FailoverSecret)).GetNetworkCredential().Password
                    $p.Force = $true
                }
                Add-DhcpServerv4Failover @p
            }
            $log
            if ($log.Result -eq 'Done') { $failover = [pscustomobject]@{ Name = $f.Name; ScopeId = @($id) } }
        }
        elseif (@($failover.ScopeId | ForEach-Object { [string]$_ }) -notcontains $id) {
            Invoke-NetLabStep $PSCmdlet $primary 'FailoverScope' "$($f.Name) + $id" { Add-DhcpServerv4FailoverScope -ComputerName $primary -Name $f.Name -ScopeId $id }
        }
        elseif ($changed -or $Replicate) {
            Invoke-NetLabStep $PSCmdlet $primary 'Replicate' "$($f.Name) $id" { Invoke-DhcpServerv4FailoverReplication -ComputerName $primary -ScopeId $id -Force }
        }
        else { New-NetLabLog $primary 'Replicate' "$($f.Name) $id" 'NoChange' }
    }
}

function Export-NetLabSnapshot {
    <# DNS (zones, aging, scavenging, A/PTR/CNAME records) and DHCP (every server) into one JSON file. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string] $DefinitionPath, [Parameter(Mandatory)][string] $Path)
    $def = Read-NetLabDefinition -Path $DefinitionPath
    $cn = [string]$def.Dns.Server
    $toUtc = { param($v) if ($null -eq $v) { $null } else { ([datetime]$v).ToUniversalTime().ToString('o') } }

    $zones = foreach ($z in @(Get-DnsServerZone -ComputerName $cn | Where-Object { -not $_.IsAutoCreated -and $_.ZoneName -ne 'TrustAnchors' })) {
        $aging = $null
        if ($z.ZoneType -eq 'Primary') { $aging = Get-DnsServerZoneAging -ComputerName $cn -Name $z.ZoneName -ErrorAction SilentlyContinue }
        [pscustomobject]@{
            ZoneName = [string]$z.ZoneName; ZoneType = [string]$z.ZoneType; IsDsIntegrated = [bool]$z.IsDsIntegrated
            IsReverseLookupZone = [bool]$z.IsReverseLookupZone; DynamicUpdate = [string]$z.DynamicUpdate; ReplicationScope = [string]$z.ReplicationScope
            AgingEnabled = [bool]$aging.AgingEnabled
            NoRefreshHours = if ($aging) { ([timespan]$aging.NoRefreshInterval).TotalHours } else { 0 }
            RefreshHours = if ($aging) { ([timespan]$aging.RefreshInterval).TotalHours } else { 0 }
        }
    }
    $wanted = @([string]$def.Dns.ForwardZone) + @($zones | Where-Object IsReverseLookupZone | ForEach-Object ZoneName)
    $records = foreach ($zn in $wanted) {
        foreach ($r in @(Get-DnsServerResourceRecord -ComputerName $cn -ZoneName $zn | Where-Object { $_.RecordType -in 'A', 'PTR', 'CNAME' })) {
            $data = switch ([string]$r.RecordType) {
                'A' { [string]$r.RecordData.IPv4Address }
                'PTR' { [string]$r.RecordData.PtrDomainName }
                'CNAME' { [string]$r.RecordData.HostNameAlias }
            }
            [pscustomobject]@{ Zone = $zn; HostName = [string]$r.HostName; RecordType = [string]$r.RecordType; Data = $data; Timestamp = (& $toUtc $r.Timestamp) }
        }
    }
    $scav = Get-DnsServerScavenging -ComputerName $cn

    $servers = foreach ($s in @($def.Dhcp.Servers)) {
        $sn = [string]$s.Name
        $scopes = foreach ($sc in @(Get-DhcpServerv4Scope -ComputerName $sn)) {
            $sid = [string]$sc.ScopeId
            $stats = Get-DhcpServerv4ScopeStatistics -ComputerName $sn -ScopeId $sid
            [pscustomobject]@{
                ScopeId = $sid; Name = [string]$sc.Name; StartRange = [string]$sc.StartRange; EndRange = [string]$sc.EndRange; State = [string]$sc.State
                PercentageInUse = [double]$stats.PercentageInUse
                Exclusions = @(Get-DhcpServerv4ExclusionRange -ComputerName $sn -ScopeId $sid | ForEach-Object { [pscustomobject]@{ StartRange = [string]$_.StartRange; EndRange = [string]$_.EndRange } })
                Reservations = @(Get-DhcpServerv4Reservation -ComputerName $sn -ScopeId $sid | ForEach-Object { [pscustomobject]@{ IPAddress = [string]$_.IPAddress; ClientId = [string]$_.ClientId; Name = [string]$_.Name } })
                Options = @(Get-DhcpServerv4OptionValue -ComputerName $sn -ScopeId $sid | ForEach-Object { [pscustomobject]@{ OptionId = [int]$_.OptionId; Value = @($_.Value | ForEach-Object { [string]$_ }) } })
            }
        }
        [pscustomobject]@{
            Name = $sn; DnsName = [string]$s.DnsName
            ServerOptions = @(Get-DhcpServerv4OptionValue -ComputerName $sn | ForEach-Object { [pscustomobject]@{ OptionId = [int]$_.OptionId; Value = @($_.Value | ForEach-Object { [string]$_ }) } })
            Scopes = @($scopes)
            Failover = @(Get-DhcpServerv4Failover -ComputerName $sn -ErrorAction SilentlyContinue | ForEach-Object {
                    [pscustomobject]@{ Name = [string]$_.Name; PartnerServer = [string]$_.PartnerServer; State = [string]$_.State; Mode = [string]$_.Mode; ScopeId = @($_.ScopeId | ForEach-Object { [string]$_ }) }
                })
        }
    }

    $snapshot = [pscustomobject]@{
        ExportedAt = (Get-Date).ToUniversalTime().ToString('o')
        Dns        = [pscustomobject]@{
            Server = $cn; ForwardZone = [string]$def.Dns.ForwardZone; Zones = @($zones); Records = @($records)
            Scavenging = [pscustomobject]@{ Enabled = [bool]$scav.ScavengingState; IntervalHours = ([timespan]$scav.ScavengingInterval).TotalHours }
        }
        Dhcp       = [pscustomobject]@{
            Authorized = @(Get-DhcpServerInDC | ForEach-Object { [pscustomobject]@{ DnsName = [string]$_.DnsName; IPAddress = [string]$_.IPAddress } })
            Servers    = @($servers)
        }
    }
    $snapshot | ConvertTo-Json -Depth 10 | Set-Content -Path $Path -Encoding UTF8
    $snapshot
}

Export-ModuleMember -Function ConvertTo-NetLabUInt32, Test-NetLabIpInRange, ConvertTo-NetLabReverseZoneName, Get-NetLabPtrName,
Read-NetLabDefinition, Test-NetLabHealth, ConvertTo-NetLabMarkdown, Invoke-NetLabDnsDeployment, Invoke-NetLabDhcpDeployment,
Export-NetLabSnapshot
