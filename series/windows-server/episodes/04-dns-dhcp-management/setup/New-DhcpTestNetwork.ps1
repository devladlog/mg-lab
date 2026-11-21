<#
.SYNOPSIS
  DEVLADLOG Windows Server #4 - isolated network for the DHCP demo (run on the Hyper-V host, elevated).
.DESCRIPTION
  The lab NAT switch (10.20.0.0/24) has no DHCP of its own, and a test DHCP server must never answer on it.
  This script creates a Hyper-V *Private* switch (VM-to-VM only: no host, no NAT, no physical network) and gives
  CON-SRV01, CON-SRV02 and CON-CLI01 a second NIC named DHCPTest on it, with fixed MACs. Inside the guests
  (PowerShell Direct, no network needed) it renames the NIC, stops it registering in DNS, and sets
  172.16.50.2 / .3 on the DHCP servers; CON-CLI01 stays a DHCP client on that NIC.
  -Remove takes it all away again.
.EXAMPLE
  ./New-DhcpTestNetwork.ps1 -Credential (Get-Credential CONTOSO\Administrator) -WhatIf
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [string] $SwitchName = 'MGLab-DHCPTest',
    [Parameter(Mandatory)][pscredential] $Credential,
    [switch] $Remove
)
$ErrorActionPreference = 'Stop'
$nics = @(
    @{ VM = 'CON-SRV01'; Mac = '00155D140002'; IP = '172.16.50.2' }
    @{ VM = 'CON-SRV02'; Mac = '00155D140003'; IP = '172.16.50.3' }
    @{ VM = 'CON-CLI01'; Mac = '00155D140041'; IP = $null }
)

if ($Remove) {
    foreach ($n in $nics) {
        if (Get-VMNetworkAdapter -VMName $n.VM -Name 'DHCPTest' -ErrorAction SilentlyContinue) {
            if ($PSCmdlet.ShouldProcess($n.VM, 'Remove-VMNetworkAdapter DHCPTest')) { Remove-VMNetworkAdapter -VMName $n.VM -Name 'DHCPTest' }
        }
    }
    if (Get-VMSwitch -Name $SwitchName -ErrorAction SilentlyContinue) {
        if ($PSCmdlet.ShouldProcess($SwitchName, 'Remove-VMSwitch')) { Remove-VMSwitch -Name $SwitchName -Force }
    }
    return
}

$switch = Get-VMSwitch -Name $SwitchName -ErrorAction SilentlyContinue
if ($switch -and [string]$switch.SwitchType -ne 'Private') {
    throw "Switch '$SwitchName' exists but is $($switch.SwitchType). The DHCP demo only runs on a Private switch."
}
if (-not $switch -and $PSCmdlet.ShouldProcess($SwitchName, 'New-VMSwitch -SwitchType Private')) {
    New-VMSwitch -Name $SwitchName -SwitchType Private | Out-Null
}

$guest = {
    param([string] $Mac, [string] $IP)
    $dashed = ($Mac -replace '(..)(?!$)', '$1-').ToUpperInvariant()
    $nic = Get-NetAdapter | Where-Object { $_.MacAddress -eq $dashed }
    if (-not $nic) { throw "No adapter with MAC $dashed in $env:COMPUTERNAME." }
    if ($nic.Name -ne 'DHCPTest') { Rename-NetAdapter -Name $nic.Name -NewName 'DHCPTest' }
    Set-DnsClient -InterfaceAlias 'DHCPTest' -RegisterThisConnectionsAddress $false
    if ($IP) {
        if (-not (Get-NetIPAddress -InterfaceAlias 'DHCPTest' -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object IPAddress -eq $IP)) {
            New-NetIPAddress -InterfaceAlias 'DHCPTest' -IPAddress $IP -PrefixLength 24 | Out-Null   # no gateway: isolated
        }
    }
    else { Set-NetIPInterface -InterfaceAlias 'DHCPTest' -Dhcp Enabled }
    Get-NetIPConfiguration -InterfaceAlias 'DHCPTest' | Select-Object InterfaceAlias, IPv4Address
}

foreach ($n in $nics) {
    if (-not (Get-VMNetworkAdapter -VMName $n.VM -Name 'DHCPTest' -ErrorAction SilentlyContinue)) {
        if ($PSCmdlet.ShouldProcess($n.VM, "Add-VMNetworkAdapter DHCPTest on $SwitchName, MAC $($n.Mac)")) {
            Add-VMNetworkAdapter -VMName $n.VM -Name 'DHCPTest' -SwitchName $SwitchName -StaticMacAddress $n.Mac
        }
    }
    if ($PSCmdlet.ShouldProcess($n.VM, 'Configure DHCPTest NIC in the guest (PowerShell Direct)')) {
        Invoke-Command -VMName $n.VM -Credential $Credential -ScriptBlock $guest -ArgumentList $n.Mac, $n.IP
    }
}
