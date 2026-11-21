using namespace System.Management.Automation.Language

BeforeAll {
    $src = Join-Path $PSScriptRoot '../src'
    Import-Module (Join-Path $src 'NetLab/NetLab.psd1') -Force
    $script:Definition = Join-Path $src 'network.json'
    $script:Fixture = Join-Path $PSScriptRoot 'fixtures/net-snapshot.json'
    $script:Policy = (Get-Content -Raw $script:Definition | ConvertFrom-Json).Policy
    $script:Now = [datetime]::new(2026, 11, 20, 9, 0, 0, [DateTimeKind]::Utc)
    function Get-Snapshot { Get-Content -Raw $script:Fixture | ConvertFrom-Json }
    function Get-Check($Snapshot, [string] $Check) { @(Test-NetLabHealth -Snapshot $Snapshot -Policy $script:Policy -Now $script:Now | Where-Object Check -eq $Check) }
    function New-TempDefinition([scriptblock] $Change) {
        $d = Get-Content -Raw $script:Definition | ConvertFrom-Json
        & $Change $d
        $path = Join-Path ([IO.Path]::GetTempPath()) "net-def-$([guid]::NewGuid()).json"
        $d | ConvertTo-Json -Depth 10 | Set-Content -Path $path
        $path
    }

    # Stubs for RSAT / Hyper-V / Windows-only cmdlets. Mock copies the stub's parameters, so it declares them all.
    $stub = {
        [CmdletBinding()]
        param($ComputerName, $Name, $NetworkId, $ReplicationScope, $DynamicUpdate, $Aging, $NoRefreshInterval, $RefreshInterval,
            $ScavengingState, $ScavengingInterval, $ZoneName, $RRType, $IPv4Address, $PtrDomainName, $HostNameAlias, $RecordData,
            [switch] $Force, $DnsName, $IPAddress, $InterfaceAlias, $BindingState, $PartnerServer, $ScopeId, $LoadBalancePercent,
            $MaxClientLeadTime, $SharedSecret, $StartRange, $EndRange, $SubnetMask, $LeaseDuration, $State, $DnsServer, $DnsDomain,
            $ClientId, $Description, $SwitchName, $SwitchType, $VMName, $StaticMacAddress, [switch] $IncludeManagementTools)
    }
    foreach ($c in 'Get-DnsServerZone', 'Add-DnsServerPrimaryZone', 'Get-DnsServerZoneAging', 'Set-DnsServerZoneAging', 'Get-DnsServerScavenging',
        'Set-DnsServerScavenging', 'Get-DnsServerResourceRecord', 'Add-DnsServerResourceRecordA', 'Add-DnsServerResourceRecordPtr',
        'Add-DnsServerResourceRecordCName', 'Remove-DnsServerResourceRecord', 'Get-DhcpServerInDC', 'Add-DhcpServerInDC', 'Get-DhcpServerv4Binding',
        'Set-DhcpServerv4Binding', 'Get-DhcpServerv4Failover', 'Add-DhcpServerv4Failover', 'Add-DhcpServerv4FailoverScope',
        'Invoke-DhcpServerv4FailoverReplication', 'Get-DhcpServerv4Scope', 'Add-DhcpServerv4Scope', 'Get-DhcpServerv4ExclusionRange',
        'Add-DhcpServerv4ExclusionRange', 'Get-DhcpServerv4OptionValue', 'Set-DhcpServerv4OptionValue', 'Get-DhcpServerv4Reservation',
        'Add-DhcpServerv4Reservation', 'Get-DhcpServerv4ScopeStatistics', 'Get-VMSwitch', 'New-VMSwitch', 'Get-VMNetworkAdapter',
        'Add-VMNetworkAdapter', 'Remove-VMNetworkAdapter', 'Remove-VMSwitch', 'Get-WindowsFeature', 'Install-WindowsFeature', 'Restart-Service', 'netsh') {
        if (-not (Get-Command $c -ErrorAction SilentlyContinue)) { New-Item -Path "function:global:$c" -Value $stub | Out-Null }
    }
    $script:Week = [timespan]::FromDays(7)
}

Describe 'IPv4 and reverse zone helpers' {
    It '<Net> -> <Zone>' -ForEach @(
        @{ Net = '10.20.0.0/24'; Zone = '0.20.10.in-addr.arpa' }
        @{ Net = '172.16.0.0/16'; Zone = '16.172.in-addr.arpa' }
        @{ Net = '10.0.0.0/8'; Zone = '10.in-addr.arpa' }
    ) { ConvertTo-NetLabReverseZoneName $Net | Should -Be $Zone }
    It 'refuses prefixes that are not on an octet boundary' { { ConvertTo-NetLabReverseZoneName '10.20.0.0/20' } | Should -Throw '*octet boundary*' }
    It 'finds the PTR owner name inside a zone, and nothing outside it' {
        Get-NetLabPtrName -IPAddress '10.20.0.60' -ReverseZone '0.20.10.in-addr.arpa' | Should -Be '60'
        Get-NetLabPtrName -IPAddress '172.16.50.41' -ReverseZone '16.172.in-addr.arpa' | Should -Be '41.50'
        Get-NetLabPtrName -IPAddress '10.30.0.5' -ReverseZone '0.20.10.in-addr.arpa' | Should -BeNullOrEmpty
    }
    It 'compares addresses numerically, not as text' {
        Test-NetLabIpInRange '172.16.50.100' '172.16.50.21' '172.16.50.254' | Should -BeTrue
        Test-NetLabIpInRange '172.16.50.3' '172.16.50.21' '172.16.50.254' | Should -BeFalse
        { ConvertTo-NetLabUInt32 '10.20.0.256' } | Should -Throw '*not an IPv4 address*'
    }
}

Describe 'Read-NetLabDefinition' {
    It 'accepts the lab definition' { (Read-NetLabDefinition -Path $script:Definition).Dhcp.Failover.Partner | Should -Be 'CON-SRV02' }
    It 'refuses a reservation inside an exclusion range' {
        $p = New-TempDefinition { param($d) $d.Dhcp.Scopes[0].Reservations[0].IPAddress = '172.16.50.10' }
        { Read-NetLabDefinition -Path $p } | Should -Throw '*inside exclusion*'
        Remove-Item $p
    }
    It 'refuses a failover partner that is not a DHCP server here, and non-octet reverse zones' {
        $p = New-TempDefinition { param($d) $d.Dhcp.Failover.Partner = 'CON-SRV09'; $d.Dns.ReverseZones[0].NetworkId = '10.20.0.0/23' }
        { Read-NetLabDefinition -Path $p } | Should -Throw '*CON-SRV09*'
        { Read-NetLabDefinition -Path $p } | Should -Throw '*octet boundary*'
        Remove-Item $p
    }
}

Describe 'Health checks (fictional snapshot)' {
    It 'flags DHCP failover drift once per relationship, with the missing reservation' {
        $f = Get-Check (Get-Snapshot) 'FailoverDrift'
        $f.Count | Should -Be 1
        $f[0].Severity | Should -Be 'High'
        $f[0].Detail | Should -Match '172\.16\.50\.42=00-15-5d-14-00-42'
        $f[0].Detail | Should -Match 'Invoke-DhcpServerv4FailoverReplication'
    }
    It 'flags a static DNS record inside a DHCP pool once, and not reserved or excluded ones' {
        $f = Get-Check (Get-Snapshot) 'StaticInPool'
        $f.Count | Should -Be 1
        $f[0].Target | Should -Be 'camera01.lab.contoso.com'
    }
    It 'flags nonsecure dynamic updates on an AD-integrated zone as High' {
        (Get-Check (Get-Snapshot) 'InsecureDynamicUpdate').Target | Should -Be 'oldapps.lab.contoso.com'
    }
    It 'needs both: server scavenging and zone aging' {
        $s = Get-Snapshot
        (Get-Check $s 'ScavengingDisabled').Count | Should -Be 1
        (Get-Check $s 'ZoneAgingDisabled').Target | Should -Be 'oldapps.lab.contoso.com'
    }
    It 'flags no-refresh + refresh under 24 hours as High' {
        $s = Get-Snapshot
        ($s.Dns.Zones | Where-Object ZoneName -eq 'lab.contoso.com') | ForEach-Object { $_.NoRefreshHours = 8; $_.RefreshHours = 8 }
        (Get-Check $s 'AgingTooShort').Detail | Should -Match '16 h'
    }
    It 'finds missing and mismatched PTRs, a reverse zone gap and a dangling CNAME' {
        $s = Get-Snapshot
        (Get-Check $s 'MissingPtr').Target | Should -Be 'nas01.lab.contoso.com'
        (Get-Check $s 'PtrMismatch').Target | Should -Be '10.20.0.99'
        (Get-Check $s 'NoReverseZone').Target | Should -Be '172.16.50.0/24'
        (Get-Check $s 'CnameTargetMissing').Target | Should -Be 'wiki.lab.contoso.com'
    }
    It 'calls a dynamic record stale only after no-refresh + refresh, and never a static one' {
        $f = Get-Check (Get-Snapshot) 'StaleRecord'
        $f.Count | Should -Be 1
        $f[0].Target | Should -Be 'con-old01.lab.contoso.com'
    }
    It 'checks DHCP authorization, scope state, utilization and required options' {
        $s = Get-Snapshot
        $s.Dhcp.Authorized = @($s.Dhcp.Authorized | Where-Object DnsName -ne 'con-srv02.lab.contoso.com')
        (Get-Check $s 'NotAuthorized').Target | Should -Be 'CON-SRV02'
        (Get-Check $s 'ScopeInactive').Target | Should -Be 'CON-SRV01/172.16.60.0'
        @(Get-Check $s 'ScopeUtilization').Count | Should -Be 2
        (Get-Check $s 'MissingOption').Detail | Should -Match 'Option 15'
    }
    It 'flags a failover relationship that is not Normal' {
        $s = Get-Snapshot
        $s.Dhcp.Servers[1].Failover[0].State = 'CommunicationInterrupted'
        (Get-Check $s 'FailoverState').Target | Should -Be 'CON-SRV02/CON-SRV01-CON-SRV02'
    }
    It 'sorts worst first: 3 High, 9 Medium, 2 Low' {
        $all = @(Test-NetLabHealth -Snapshot (Get-Snapshot) -Policy $script:Policy -Now $script:Now)
        $all.Count | Should -Be 14
        @($all | Where-Object Severity -eq 'High').Count | Should -Be 3
        @($all | Where-Object Severity -eq 'Medium').Count | Should -Be 9
        $all[0].Severity | Should -Be 'High'
        $all[-1].Severity | Should -Be 'Low'
    }
}

Describe 'Invoke-NetLabDnsDeployment (DnsServer cmdlets mocked)' {
    BeforeEach {
        Mock Get-DnsServerZone -ModuleName NetLab { if ($Name -eq 'lab.contoso.com') { [pscustomobject]@{ ZoneName = $Name } } }
        Mock Get-DnsServerZoneAging -ModuleName NetLab { [pscustomobject]@{ AgingEnabled = $false; NoRefreshInterval = [timespan]::Zero; RefreshInterval = [timespan]::Zero } }
        Mock Get-DnsServerScavenging -ModuleName NetLab { [pscustomobject]@{ ScavengingState = $false; ScavengingInterval = $script:Week } }
        Mock Get-DnsServerResourceRecord -ModuleName NetLab { $null }
        foreach ($c in 'Add-DnsServerPrimaryZone', 'Set-DnsServerZoneAging', 'Set-DnsServerScavenging', 'Add-DnsServerResourceRecordA',
            'Add-DnsServerResourceRecordPtr', 'Add-DnsServerResourceRecordCName', 'Remove-DnsServerResourceRecord') { Mock $c -ModuleName NetLab { } }
    }
    It 'creates the reverse zone, turns on aging and scavenging, adds A, PTR and CNAME records' {
        Invoke-NetLabDnsDeployment -DefinitionPath $script:Definition | Out-Null
        Should -Invoke Add-DnsServerPrimaryZone -ModuleName NetLab -Times 1 -Exactly -ParameterFilter {
            $ComputerName -eq 'CON-DC01' -and $NetworkId -eq '10.20.0.0/24' -and $ReplicationScope -eq 'Domain' -and $DynamicUpdate -eq 'Secure'
        }
        Should -Invoke Set-DnsServerZoneAging -ModuleName NetLab -Times 2 -Exactly -ParameterFilter { $Aging -and $NoRefreshInterval -eq $script:Week -and $RefreshInterval -eq $script:Week }
        Should -Invoke Set-DnsServerScavenging -ModuleName NetLab -Times 1 -Exactly -ParameterFilter { $ScavengingState -eq $true }
        Should -Invoke Add-DnsServerResourceRecordA -ModuleName NetLab -Times 2 -Exactly
        Should -Invoke Add-DnsServerResourceRecordPtr -ModuleName NetLab -Times 1 -Exactly -ParameterFilter {
            $ZoneName -eq '0.20.10.in-addr.arpa' -and $Name -eq '60' -and $PtrDomainName -eq 'printer01.lab.contoso.com'
        }
        Should -Invoke Add-DnsServerResourceRecordCName -ModuleName NetLab -Times 2 -Exactly
    }
    It 'changes nothing with -WhatIf' {
        $log = @(Invoke-NetLabDnsDeployment -DefinitionPath $script:Definition -WhatIf)
        foreach ($c in 'Add-DnsServerPrimaryZone', 'Set-DnsServerZoneAging', 'Set-DnsServerScavenging', 'Add-DnsServerResourceRecordA', 'Add-DnsServerResourceRecordPtr') {
            Should -Invoke $c -ModuleName NetLab -Times 0 -Exactly
        }
        @($log | Where-Object Result -eq 'WhatIf').Count | Should -Be 10
    }
    It 'reports NoChange for everything when the server already matches' {
        Mock Get-DnsServerZone -ModuleName NetLab { [pscustomobject]@{ ZoneName = $Name } }
        Mock Get-DnsServerZoneAging -ModuleName NetLab { [pscustomobject]@{ AgingEnabled = $true; NoRefreshInterval = $script:Week; RefreshInterval = $script:Week } }
        Mock Get-DnsServerScavenging -ModuleName NetLab { [pscustomobject]@{ ScavengingState = $true; ScavengingInterval = $script:Week } }
        Mock Get-DnsServerResourceRecord -ModuleName NetLab {
            $map = @{ printer01 = '10.20.0.60'; nas01 = '10.20.0.61'; '60' = 'printer01.lab.contoso.com.'; '61' = 'nas01.lab.contoso.com.'
                intranet = 'con-srv02.lab.contoso.com.'; sql = 'con-sql01.lab.contoso.com.' }
            [pscustomobject]@{ RecordData = [pscustomobject]@{ IPv4Address = $map[$Name]; PtrDomainName = $map[$Name]; HostNameAlias = $map[$Name] } }
        }
        $log = @(Invoke-NetLabDnsDeployment -DefinitionPath $script:Definition)
        $log.Count | Should -Be 10
        @($log | Where-Object Result -ne 'NoChange').Count | Should -Be 0
    }
    It 'repairs an A record that points elsewhere, and its PTR' {
        Mock Get-DnsServerResourceRecord -ModuleName NetLab -ParameterFilter { $Name -eq 'printer01' } { [pscustomobject]@{ RecordData = [pscustomobject]@{ IPv4Address = '10.20.0.99' } } }
        Mock Get-DnsServerResourceRecord -ModuleName NetLab -ParameterFilter { $Name -eq '60' } { [pscustomobject]@{ RecordData = [pscustomobject]@{ PtrDomainName = 'oldprinter.lab.contoso.com.' } } }
        Invoke-NetLabDnsDeployment -DefinitionPath $script:Definition | Out-Null
        Should -Invoke Remove-DnsServerResourceRecord -ModuleName NetLab -Times 1 -Exactly -ParameterFilter { $RRType -eq 'A' -and $RecordData -eq '10.20.0.99' }
        Should -Invoke Remove-DnsServerResourceRecord -ModuleName NetLab -Times 1 -Exactly -ParameterFilter { $RRType -eq 'Ptr' -and $Name -eq '60' }
        Should -Invoke Add-DnsServerResourceRecordA -ModuleName NetLab -Times 1 -Exactly -ParameterFilter { $Name -eq 'printer01' -and $IPv4Address -eq '10.20.0.60' }
    }
    It 'stops if the forward zone does not exist' {
        Mock Get-DnsServerZone -ModuleName NetLab { $null }
        { Invoke-NetLabDnsDeployment -DefinitionPath $script:Definition } | Should -Throw "*Forward zone 'lab.contoso.com' not found*"
    }
}

Describe 'Invoke-NetLabDhcpDeployment (DhcpServer cmdlets mocked)' {
    BeforeEach {
        Mock Get-DhcpServerInDC -ModuleName NetLab { @() }
        Mock Get-DhcpServerv4Binding -ModuleName NetLab {
            @([pscustomobject]@{ InterfaceAlias = 'Ethernet'; BindingState = $true }, [pscustomobject]@{ InterfaceAlias = 'DHCPTest'; BindingState = $false })
        }
        Mock Get-DhcpServerv4Failover -ModuleName NetLab { $null }
        Mock Get-DhcpServerv4Scope -ModuleName NetLab { $null }
        Mock Get-DhcpServerv4ExclusionRange -ModuleName NetLab { @() }
        Mock Get-DhcpServerv4OptionValue -ModuleName NetLab { @() }
        Mock Get-DhcpServerv4Reservation -ModuleName NetLab { @() }
        foreach ($c in 'Add-DhcpServerInDC', 'Set-DhcpServerv4Binding', 'Add-DhcpServerv4Scope', 'Add-DhcpServerv4ExclusionRange', 'Set-DhcpServerv4OptionValue',
            'Add-DhcpServerv4Reservation', 'Add-DhcpServerv4Failover', 'Add-DhcpServerv4FailoverScope', 'Invoke-DhcpServerv4FailoverReplication') { Mock $c -ModuleName NetLab { } }
    }
    It 'authorizes both servers and binds them only to the isolated NIC' {
        Invoke-NetLabDhcpDeployment -DefinitionPath $script:Definition | Out-Null
        Should -Invoke Add-DhcpServerInDC -ModuleName NetLab -Times 2 -Exactly
        Should -Invoke Set-DhcpServerv4Binding -ModuleName NetLab -Times 2 -Exactly -ParameterFilter { $InterfaceAlias -eq 'Ethernet' -and $BindingState -eq $false }
        Should -Invoke Set-DhcpServerv4Binding -ModuleName NetLab -Times 2 -Exactly -ParameterFilter { $InterfaceAlias -eq 'DHCPTest' -and $BindingState -eq $true }
    }
    It 'builds the scope on the primary and creates load-balanced failover with the partner' {
        Invoke-NetLabDhcpDeployment -DefinitionPath $script:Definition | Out-Null
        Should -Invoke Add-DhcpServerv4Scope -ModuleName NetLab -Times 1 -Exactly -ParameterFilter {
            $ComputerName -eq 'CON-SRV01' -and $StartRange -eq '172.16.50.1' -and $State -eq 'Active' -and $LeaseDuration -eq [timespan]::FromDays(1)
        }
        Should -Invoke Add-DhcpServerv4ExclusionRange -ModuleName NetLab -Times 1 -Exactly -ParameterFilter { $EndRange -eq '172.16.50.20' }
        Should -Invoke Set-DhcpServerv4OptionValue -ModuleName NetLab -Times 1 -Exactly -ParameterFilter { $DnsServer -contains '10.20.0.10' -and $DnsDomain -eq 'lab.contoso.com' }
        Should -Invoke Add-DhcpServerv4Reservation -ModuleName NetLab -Times 1 -Exactly -ParameterFilter { $IPAddress -eq '172.16.50.41' -and $ClientId -eq '00-15-5d-14-00-41' }
        Should -Invoke Add-DhcpServerv4Failover -ModuleName NetLab -Times 1 -Exactly -ParameterFilter {
            $ComputerName -eq 'CON-SRV01' -and $PartnerServer -eq 'CON-SRV02' -and $ScopeId -eq '172.16.50.0' -and $LoadBalancePercent -eq 50 -and -not $SharedSecret
        }
        Should -Invoke Invoke-DhcpServerv4FailoverReplication -ModuleName NetLab -Times 0 -Exactly
    }
    It 'passes a failover shared secret only when given one' {
        $secret = ConvertTo-SecureString 'lab-only-secret' -AsPlainText -Force
        Invoke-NetLabDhcpDeployment -DefinitionPath $script:Definition -FailoverSecret $secret | Out-Null
        Should -Invoke Add-DhcpServerv4Failover -ModuleName NetLab -Times 1 -Exactly -ParameterFilter { $SharedSecret -eq 'lab-only-secret' -and $Force }
    }
    It 'changes nothing with -WhatIf' {
        $log = @(Invoke-NetLabDhcpDeployment -DefinitionPath $script:Definition -WhatIf)
        foreach ($c in 'Add-DhcpServerInDC', 'Set-DhcpServerv4Binding', 'Add-DhcpServerv4Scope', 'Add-DhcpServerv4Reservation', 'Add-DhcpServerv4Failover') {
            Should -Invoke $c -ModuleName NetLab -Times 0 -Exactly
        }
        @($log | Where-Object Result -ne 'WhatIf').Count | Should -Be 0
    }
    Context 'failover already in place' {
        BeforeEach {
            Mock Get-DhcpServerInDC -ModuleName NetLab { @([pscustomobject]@{ DnsName = 'con-srv01.lab.contoso.com' }, [pscustomobject]@{ DnsName = 'con-srv02.lab.contoso.com' }) }
            Mock Get-DhcpServerv4Binding -ModuleName NetLab { @([pscustomobject]@{ InterfaceAlias = 'Ethernet'; BindingState = $false }, [pscustomobject]@{ InterfaceAlias = 'DHCPTest'; BindingState = $true }) }
            Mock Get-DhcpServerv4Failover -ModuleName NetLab { [pscustomobject]@{ Name = 'CON-SRV01-CON-SRV02'; ScopeId = @('172.16.50.0') } }
            Mock Get-DhcpServerv4Scope -ModuleName NetLab { [pscustomobject]@{ ScopeId = '172.16.50.0' } }
            Mock Get-DhcpServerv4ExclusionRange -ModuleName NetLab { [pscustomobject]@{ StartRange = '172.16.50.1'; EndRange = '172.16.50.20' } }
            Mock Get-DhcpServerv4OptionValue -ModuleName NetLab { @([pscustomobject]@{ OptionId = 6; Value = @('10.20.0.10') }, [pscustomobject]@{ OptionId = 15; Value = @('lab.contoso.com') }) }
            Mock Get-DhcpServerv4Reservation -ModuleName NetLab { [pscustomobject]@{ IPAddress = '172.16.50.41'; ClientId = '00-15-5D-14-00-41' } }
        }
        It 'reports NoChange and does not replicate when nothing changed' {
            $log = @(Invoke-NetLabDhcpDeployment -DefinitionPath $script:Definition)
            @($log | Where-Object Result -ne 'NoChange').Count | Should -Be 0
            Should -Invoke Invoke-DhcpServerv4FailoverReplication -ModuleName NetLab -Times 0 -Exactly
        }
        It 'replicates to the partner after a scope change (the failover gotcha)' {
            $p = New-TempDefinition { param($d)
                $d.Dhcp.Scopes[0].Reservations += [pscustomobject]@{ Name = 'labprinter'; IPAddress = '172.16.50.42'; ClientId = '00-15-5d-14-00-42'; Description = 'lab printer' }
            }
            Invoke-NetLabDhcpDeployment -DefinitionPath $p | Out-Null
            Should -Invoke Add-DhcpServerv4Reservation -ModuleName NetLab -Times 1 -Exactly -ParameterFilter { $IPAddress -eq '172.16.50.42' }
            Should -Invoke Invoke-DhcpServerv4FailoverReplication -ModuleName NetLab -Times 1 -Exactly -ParameterFilter { $ComputerName -eq 'CON-SRV01' -and $ScopeId -eq '172.16.50.0' -and $Force }
            Remove-Item $p
        }
        It 'replicates on request with -Replicate (for changes made outside the file)' {
            Invoke-NetLabDhcpDeployment -DefinitionPath $script:Definition -Replicate | Out-Null
            Should -Invoke Invoke-DhcpServerv4FailoverReplication -ModuleName NetLab -Times 1 -Exactly
        }
    }
}

Describe 'Export-NetLabSnapshot (cmdlets mocked)' {
    It 'writes a snapshot the checks can read' {
        Mock Get-DnsServerZone -ModuleName NetLab {
            @([pscustomobject]@{ ZoneName = 'lab.contoso.com'; ZoneType = 'Primary'; IsDsIntegrated = $true; IsReverseLookupZone = $false; DynamicUpdate = 'Secure'; ReplicationScope = 'Domain'; IsAutoCreated = $false },
                [pscustomobject]@{ ZoneName = '0.20.10.in-addr.arpa'; ZoneType = 'Primary'; IsDsIntegrated = $true; IsReverseLookupZone = $true; DynamicUpdate = 'Secure'; ReplicationScope = 'Domain'; IsAutoCreated = $false },
                [pscustomobject]@{ ZoneName = '0.in-addr.arpa'; ZoneType = 'Primary'; IsDsIntegrated = $false; IsReverseLookupZone = $true; DynamicUpdate = 'None'; ReplicationScope = 'None'; IsAutoCreated = $true })
        }
        Mock Get-DnsServerZoneAging -ModuleName NetLab { [pscustomobject]@{ AgingEnabled = $true; NoRefreshInterval = $script:Week; RefreshInterval = $script:Week } }
        Mock Get-DnsServerScavenging -ModuleName NetLab { [pscustomobject]@{ ScavengingState = $true; ScavengingInterval = $script:Week } }
        Mock Get-DnsServerResourceRecord -ModuleName NetLab {
            if ($ZoneName -eq 'lab.contoso.com') {
                @([pscustomobject]@{ HostName = 'con-srv01'; RecordType = 'A'; Timestamp = [datetime]'2026-11-18T08:00:00Z'; RecordData = [pscustomobject]@{ IPv4Address = '10.20.0.21' } },
                    [pscustomobject]@{ HostName = '@'; RecordType = 'NS'; Timestamp = $null; RecordData = [pscustomobject]@{ NameServer = 'con-dc01.lab.contoso.com.' } })
            }
            else { @([pscustomobject]@{ HostName = '21'; RecordType = 'PTR'; Timestamp = $null; RecordData = [pscustomobject]@{ PtrDomainName = 'con-srv01.lab.contoso.com.' } }) }
        }
        Mock Get-DhcpServerv4Scope -ModuleName NetLab { @() }
        Mock Get-DhcpServerv4OptionValue -ModuleName NetLab { @([pscustomobject]@{ OptionId = 6; Value = @('10.20.0.10') }, [pscustomobject]@{ OptionId = 15; Value = @('lab.contoso.com') }) }
        Mock Get-DhcpServerv4Failover -ModuleName NetLab { @() }
        Mock Get-DhcpServerInDC -ModuleName NetLab { @([pscustomobject]@{ DnsName = 'con-srv01.lab.contoso.com'; IPAddress = '10.20.0.21' }, [pscustomobject]@{ DnsName = 'con-srv02.lab.contoso.com'; IPAddress = '10.20.0.22' }) }

        $path = Join-Path ([IO.Path]::GetTempPath()) "net-snap-$([guid]::NewGuid()).json"
        $s = Export-NetLabSnapshot -DefinitionPath $script:Definition -Path $path
        @($s.Dns.Zones).Count | Should -Be 2
        @($s.Dns.Records).Count | Should -Be 2
        $s.Dns.Zones[0].NoRefreshHours | Should -Be 168
        $reloaded = Get-Content -Raw $path | ConvertFrom-Json
        @(Test-NetLabHealth -Snapshot $reloaded -Policy $script:Policy -Now $script:Now).Count | Should -Be 0
        Remove-Item $path
    }
}

Describe 'Setup scripts (Hyper-V and Windows cmdlets mocked)' {
    BeforeAll {
        $script:NetScript = Join-Path $PSScriptRoot '../setup/New-DhcpTestNetwork.ps1'
        $script:RoleScript = Join-Path $PSScriptRoot '../setup/Install-DhcpRole.ps1'
        $script:Cred = [pscredential]::new('CONTOSO\labadmin', (ConvertTo-SecureString 'x' -AsPlainText -Force))
    }
    BeforeEach {
        Mock Get-VMSwitch { $null }
        Mock New-VMSwitch { }
        Mock Get-VMNetworkAdapter { $null }
        Mock Add-VMNetworkAdapter { }
        Mock Remove-VMNetworkAdapter { }
        Mock Remove-VMSwitch { }
        Mock Invoke-Command { }
    }
    It 'creates a Private switch and one fixed-MAC NIC per VM, configured over PowerShell Direct' {
        & $script:NetScript -Credential $script:Cred
        Should -Invoke New-VMSwitch -Times 1 -Exactly -ParameterFilter { $SwitchType -eq 'Private' -and $Name -eq 'MGLab-DHCPTest' }
        Should -Invoke Add-VMNetworkAdapter -Times 3 -Exactly
        Should -Invoke Add-VMNetworkAdapter -Times 1 -Exactly -ParameterFilter { $VMName -eq 'CON-CLI01' -and $StaticMacAddress -eq '00155D140041' }
        Should -Invoke Invoke-Command -Times 3 -Exactly
    }
    It 'refuses to use a switch with that name that is not Private' {
        Mock Get-VMSwitch { [pscustomobject]@{ Name = 'MGLab-DHCPTest'; SwitchType = 'Internal' } }
        { & $script:NetScript -Credential $script:Cred } | Should -Throw '*only runs on a Private switch*'
        Should -Invoke Add-VMNetworkAdapter -Times 0 -Exactly
    }
    It 'changes nothing with -WhatIf, and -Remove takes it away' {
        & $script:NetScript -Credential $script:Cred -WhatIf
        Should -Invoke New-VMSwitch -Times 0 -Exactly
        Should -Invoke Invoke-Command -Times 0 -Exactly
        Mock Get-VMNetworkAdapter { [pscustomobject]@{ Name = 'DHCPTest' } }
        Mock Get-VMSwitch { [pscustomobject]@{ Name = 'MGLab-DHCPTest'; SwitchType = 'Private' } }
        & $script:NetScript -Credential $script:Cred -Remove
        Should -Invoke Remove-VMNetworkAdapter -Times 3 -Exactly
        Should -Invoke Remove-VMSwitch -Times 1 -Exactly
    }
    It 'turns the Hyper-V MAC into the guest adapter format' {
        '00155D140041' -replace '(..)(?!$)', '$1-' | Should -Be '00-15-5D-14-00-41'
    }
    It 'installs the DHCP role, creates the security groups, and clears the Server Manager alert' {
        Mock Get-WindowsFeature { [pscustomobject]@{ Name = 'DHCP'; Installed = $false } }
        Mock Install-WindowsFeature { }
        Mock netsh { }
        Mock Restart-Service { }
        Mock Set-ItemProperty { }
        & $script:RoleScript
        Should -Invoke Install-WindowsFeature -Times 1 -Exactly -ParameterFilter { $Name -eq 'DHCP' -and $IncludeManagementTools }
        Should -Invoke netsh -Times 1 -Exactly
        Should -Invoke Restart-Service -Times 1 -Exactly
        Should -Invoke Set-ItemProperty -Times 1 -Exactly -ParameterFilter { $Name -eq 'ConfigurationState' -and $Value -eq 2 }
    }
}

Describe 'Invoke-NetLabReport.ps1 (offline, end to end)' {
    It 'writes the markdown report and exits 1 with -FailOnHigh' {
        $out = Join-Path ([IO.Path]::GetTempPath()) "net-report-$([guid]::NewGuid()).md"
        $script = Join-Path $PSScriptRoot '../src/Invoke-NetLabReport.ps1'
        & pwsh -NoProfile -Command "& '$script' -FromSnapshot '$script:Fixture' -Now 2026-11-20T09:00:00Z -OutFile '$out' -FailOnHigh" | Out-Null
        $LASTEXITCODE | Should -Be 1
        $md = Get-Content -Raw $out
        $md | Should -Match 'DNS and DHCP health report: lab.contoso.com'
        $md | Should -Match 'High 3 / Medium 9 / Low 2 / Info 0'
        Remove-Item $out
    }
}

Describe 'Windows PowerShell 5.1 compatibility' {
    It '<File> has no PowerShell 7-only syntax' -ForEach @(
        @{ File = 'src/NetLab/NetLab.psm1' }, @{ File = 'src/Invoke-NetLabReport.ps1' }, @{ File = 'setup/New-DhcpTestNetwork.ps1' }, @{ File = 'setup/Install-DhcpRole.ps1' }
    ) {
        $errors = $null
        $ast = [Parser]::ParseFile((Join-Path $PSScriptRoot "../$File"), [ref]$null, [ref]$errors)
        @($errors).Count | Should -Be 0
        $bad = $ast.FindAll({
                param($n)
                $n -is [TernaryExpressionAst] -or $n -is [PipelineChainAst] -or
                ($n -is [BinaryExpressionAst] -and "$($n.Operator)" -eq 'QuestionQuestion') -or
                ($n -is [AssignmentStatementAst] -and "$($n.Operator)" -eq 'QuestionQuestionEquals') -or
                ($n -is [MemberExpressionAst] -and $n.NullConditional) -or ($n -is [IndexExpressionAst] -and $n.NullConditional)
            }, $true)
        @($bad).Count | Should -Be 0
    }
}
