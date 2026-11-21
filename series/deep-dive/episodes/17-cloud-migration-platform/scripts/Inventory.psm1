# Turns raw Windows facts (CIM objects, Get-NetTCPConnection rows) into the inventory JSON that `python -m migplan` reads.
# The converters are pure functions so Pester can test them with plain objects; Get-LocalServerFacts is the only part that
# touches the machine (Windows only).
Set-StrictMode -Version Latest

function Get-HypervisorName {
    param([string]$Manufacturer, [string]$Model)
    if ($Manufacturer -like 'Microsoft*' -and $Model -like 'Virtual Machine*') { return 'Hyper-V' }
    if ($Manufacturer -like 'VMware*') { return 'VMware' }
    if ($Model -like '*KVM*' -or $Manufacturer -like 'QEMU*') { return 'KVM' }
    return ''
}

function ConvertTo-ServerRecord {
    <#
    .SYNOPSIS  One inventory server from CIM-shaped input. FirmwareType is the Get-ComputerInfo BiosFirmwareType value (Uefi or Bios).
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] $ComputerSystem,   # Win32_ComputerSystem: Name, DNSHostName, Domain, Manufacturer, Model, TotalPhysicalMemory
        [Parameter(Mandatory)] $OperatingSystem,  # Win32_OperatingSystem: Caption, Version, OSArchitecture
        [Parameter(Mandatory)] [array]$Processors, # Win32_Processor: NumberOfLogicalProcessors
        [array]$Disks = @(),                       # Win32_DiskDrive: Size (bytes)
        [array]$IPAddresses = @(),
        [string]$FirmwareType = '',
        $CpuUtilPct = $null,
        $MemUtilPct = $null,
        [string]$Role = 'unknown',
        [string]$Criticality = 'medium'
    )
    $cores = ($Processors | Measure-Object -Property NumberOfLogicalProcessors -Sum).Sum
    $hypervisor = Get-HypervisorName $ComputerSystem.Manufacturer $ComputerSystem.Model
    $fqdn = $ComputerSystem.DNSHostName
    if ($ComputerSystem.Domain -and $ComputerSystem.Domain -ne 'WORKGROUP') { $fqdn = "$($ComputerSystem.DNSHostName).$($ComputerSystem.Domain)" }
    $record = [ordered]@{
        name         = $ComputerSystem.Name.ToLowerInvariant()
        fqdn         = $fqdn.ToLowerInvariant()
        ips          = @($IPAddresses | Where-Object { $_ -and $_ -notlike '169.254.*' -and $_ -notlike '127.*' -and $_ -notmatch ':' })
        cores        = [int]$cores
        memoryMb     = [int][math]::Round($ComputerSystem.TotalPhysicalMemory / 1MB)
        osName       = ($OperatingSystem.Caption -replace '^Microsoft\s+', '').Trim()
        osVersion    = $OperatingSystem.Version
        osArch       = if ($OperatingSystem.OSArchitecture -like '64*') { 'x64' } else { 'x86' }
        serverType   = if ($hypervisor) { 'Virtual' } else { 'Physical' }
        hypervisor   = $hypervisor
        bootType     = switch ($FirmwareType) { 'Uefi' { 'UEFI' } 'Bios' { 'BIOS' } default { '' } }
        disksGb      = @($Disks | ForEach-Object { [math]::Round($_.Size / 1GB, 0) })
        role         = $Role
        criticality  = $Criticality
    }
    if ($null -ne $CpuUtilPct) { $record['cpuUtilPct'] = [math]::Round([double]$CpuUtilPct, 1) }
    if ($null -ne $MemUtilPct) { $record['memUtilPct'] = [math]::Round([double]$MemUtilPct, 1) }
    [pscustomobject]$record
}

function ConvertTo-ConnectionRecords {
    <#
    .SYNOPSIS  Established TCP rows -> connection records. Only outbound-looking rows are kept: remote port below the
               ephemeral range (49152 and up) and not a loopback or link-local address. A heuristic, not a flow log.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Source, [array]$Rows = @())
    $seen = @{}
    foreach ($r in $Rows) {
        if ($r.RemotePort -ge 49152) { continue }
        if ($r.RemoteAddress -like '127.*' -or $r.RemoteAddress -like '169.254.*' -or $r.RemoteAddress -match ':') { continue }
        $key = "$($r.RemoteAddress):$($r.RemotePort)"
        if ($seen.ContainsKey($key)) { continue }
        $seen[$key] = $true
        [pscustomobject][ordered]@{ source = $Source.ToLowerInvariant(); destinationIp = $r.RemoteAddress; port = [int]$r.RemotePort }
    }
}

function Get-LocalServerFacts {
    <# Windows only. Reads this machine and returns @{ server = <record>; connections = <records> }. #>
    [CmdletBinding()]
    param([string]$Role = 'unknown', [string]$Criticality = 'medium', [int]$Samples = 5)
    $cs = Get-CimInstance Win32_ComputerSystem
    $os = Get-CimInstance Win32_OperatingSystem
    $cpu = Get-CimInstance Win32_Processor
    $disks = Get-CimInstance Win32_DiskDrive
    $ips = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue).IPAddress
    $fw = (Get-ComputerInfo -Property BiosFirmwareType).BiosFirmwareType.ToString()
    $cpuPct = (Get-Counter '\Processor(_Total)\% Processor Time' -SampleInterval 1 -MaxSamples $Samples).CounterSamples.CookedValue |
        Measure-Object -Average | Select-Object -ExpandProperty Average
    $memPct = 100 * (1 - ($os.FreePhysicalMemory / $os.TotalVisibleMemorySize))
    $rows = Get-NetTCPConnection -State Established -ErrorAction SilentlyContinue
    @{
        server      = ConvertTo-ServerRecord -ComputerSystem $cs -OperatingSystem $os -Processors @($cpu) -Disks @($disks) -IPAddresses @($ips) `
                          -FirmwareType $fw -CpuUtilPct $cpuPct -MemUtilPct $memPct -Role $Role -Criticality $Criticality
        connections = @(ConvertTo-ConnectionRecords -Source $cs.Name -Rows @($rows))
    }
}

function ConvertTo-InventoryJson {
    [CmdletBinding()]
    param([Parameter(Mandatory)][array]$Facts, [string]$Source = 'collected with Get-ServerInventory.ps1')
    [ordered]@{
        source      = $Source
        servers     = @($Facts | ForEach-Object { $_.server })
        connections = @($Facts | ForEach-Object { $_.connections } | Where-Object { $_ })
    } | ConvertTo-Json -Depth 6
}

Export-ModuleMember -Function Get-HypervisorName, ConvertTo-ServerRecord, ConvertTo-ConnectionRecords, Get-LocalServerFacts, ConvertTo-InventoryJson
