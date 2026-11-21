BeforeAll {
    Import-Module (Join-Path $PSScriptRoot '..' 'scripts' 'Inventory.psm1') -Force
    $script:facts = Get-Content -Raw (Join-Path $PSScriptRoot 'fixtures' 'facts.json') | ConvertFrom-Json
    function script:Convert([int]$i) {
        $f = $script:facts[$i]
        ConvertTo-ServerRecord -ComputerSystem $f.computerSystem -OperatingSystem $f.operatingSystem -Processors @($f.processors) `
            -Disks @($f.disks) -IPAddresses @($f.ipAddresses) -FirmwareType $f.firmwareType -CpuUtilPct $f.cpuUtilPct -MemUtilPct $f.memUtilPct
    }
}

Describe 'ConvertTo-ServerRecord' {
    It 'sums logical processors, converts memory to MB and disks to GB' {
        $r = Convert 0
        $r.cores | Should -Be 4
        $r.memoryMb | Should -Be 8192
        $r.disksGb | Should -Be @(127, 256)
    }
    It 'drops link-local, loopback and IPv6 addresses' {
        (Convert 0).ips | Should -Be @('10.50.0.51')
    }
    It 'strips the Microsoft prefix from the OS caption' {
        (Convert 0).osName | Should -Be 'Windows Server 2022 Standard'
    }
    It 'detects Hyper-V guests and physical hosts' {
        (Convert 0).hypervisor | Should -Be 'Hyper-V'
        (Convert 0).serverType | Should -Be 'Virtual'
        (Convert 1).serverType | Should -Be 'Physical'
        (Convert 1).hypervisor | Should -Be ''
    }
    It 'maps the firmware type to the import values' {
        (Convert 0).bootType | Should -Be 'UEFI'
        (Convert 1).bootType | Should -Be 'BIOS'
    }
    It 'builds the FQDN from the domain, and leaves workgroup machines short' {
        (Convert 0).fqdn | Should -Be 'con-app01.corp.contoso.com'
        (Convert 1).fqdn | Should -Be 'con-old01'
    }
    It 'omits utilisation when it was not measured' {
        (Convert 1).PSObject.Properties.Name | Should -Not -Contain 'cpuUtilPct'
        (Convert 0).cpuUtilPct | Should -Be 12.3
    }
}

Describe 'ConvertTo-ConnectionRecords' {
    It 'keeps unique non-ephemeral outbound rows only' {
        $c = @(ConvertTo-ConnectionRecords -Source 'CON-APP01' -Rows @($script:facts[0].tcpConnections))
        $c.Count | Should -Be 2
        ($c | Where-Object port -eq 1433).destinationIp | Should -Be '10.50.0.52'
        $c.source | Select-Object -Unique | Should -Be 'con-app01'
    }
}

Describe 'Get-ServerInventory.ps1 -FromFacts' {
    It 'writes JSON with servers and connections' {
        $out = Join-Path $TestDrive 'inv.json'
        & (Join-Path $PSScriptRoot '..' 'scripts' 'Get-ServerInventory.ps1') -FromFacts (Join-Path $PSScriptRoot 'fixtures' 'facts.json') -OutFile $out | Out-Null
        $j = Get-Content -Raw $out | ConvertFrom-Json
        $j.servers.Count | Should -Be 2
        $j.connections.Count | Should -Be 2
    }
}
